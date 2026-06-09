"""
AutoScout24 dealer-search — pan-EU dealer IDENTITY census from the AS24 directory API.

AS24 retired its old ``/haendler/`` SSR directory (what ``portal_aggregator`` scraped) for a
Next.js app whose dealer list is served by a clean JSON XHR endpoint:

    GET https://www.autoscout24.<tld>/dealer-search/api
        ?country=<CC>&pageIndex=<N>&size=<=100>&sortBy=best

Verified live 2026-06-09 (plain httpx, browser UA — NOT Cloudflare-gated, no captcha on the
list path): the ``country`` param filters server-side and the per-country totals are real
(NOT the SSR's geo-defaulted first-10, which mirrored DE for .be). Counts:

    DE 19766  FR 1999  ES 2936  NL 6019  BE 3843     (CH 0 — autoscout24.ch is a separate
                                                       platform; IT/AT exist but out of scope)

≈34.5k dealer identities across 5 of our 6 countries, proxy-free, one connector — the
multi-country anchor that breaks the FR/SIRENE discovery monoculture (GOAL#2). Each record
carries companyName + full address (street, postcode, city, CC) but NO website (the dealer's
own domain is resolved downstream by ``name_to_domain`` via crt.sh, then inventory is harvested
from that domain). So we emit IDENTITY candidates (``domain`` is NULL, ``registry_id`` =
AS24 customerId), exactly like ``nl_rdw``.

``pageIndex`` paginates (page 2 ≠ page 1, verified); ``size`` caps at 100 (250+ → HTTP 400).
The SSR ``?page``/``?pageIndex`` query params are IGNORED (always render page 1) — only the
XHR API honours pagination, so we hit the API directly.

Usage:
    python -m scrapers.discovery.sources.as24_dealers                 # full census (5 countries)
    AS24_LIMIT=200 python -m scrapers.discovery.sources.as24_dealers  # bounded sample per country
"""
from __future__ import annotations

import asyncio
import logging
import os
import re

import asyncpg
import httpx

log = logging.getLogger("as24_dealers")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [as24_dealers] %(message)s",
)

_DSN = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_SOURCE = "portal:autoscout24"
_SOURCE_LAYER = 2  # portal layer (mirrors portal_aggregator)

# Country -> AS24 TLD host. CH excluded: autoscout24.ch is a distinct platform (dealer-search
# 404 there) and country=CH on the API returns 0. The API's country param is authoritative.
_COUNTRY_HOST: dict[str, str] = {
    "DE": "www.autoscout24.de", "FR": "www.autoscout24.fr", "ES": "www.autoscout24.es",
    "NL": "www.autoscout24.nl", "BE": "www.autoscout24.be",
}
_COUNTRIES: tuple[str, ...] = tuple(_COUNTRY_HOST)

_PAGE_SIZE = 100          # API hard cap (size>=250 -> HTTP 400)
_PAGE_CAP = 5000          # safety bound on pages/country (>> any real numberOfPages)
_HDR = {
    "Accept": "application/json",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
}

# "Am Baumgarten 3+7, 91463 Dietersheim, DE" -> (street, postcode, city, cc)
_ADDR_RE = re.compile(r"^(.*),\s*(\d{4,5})\s+([^,]+?),\s*([A-Z]{2})\s*$")
# NL postcodes are "NNNN LL" (4 digits + 2 letters). Capturing the suffix generically
# would mis-split ES cities that open with a 2-letter uppercase word ("41710 LA MORERA"),
# so the letter suffix is claimed for the postcode ONLY for NL.
_ADDR_RE_NL = re.compile(r"^(.*),\s*(\d{4}\s*[A-Z]{2})\s+([^,]+?),\s*([A-Z]{2})\s*$")


def parse_address(addr: str | None, country: str | None = None) -> tuple[str | None, str | None, str | None]:
    """Split an AS24 address string into (street, postcode, city). Defensive: raw street on miss."""
    raw = (addr or "").strip()
    if not raw:
        return None, None, None
    m = (_ADDR_RE_NL.match(raw) if country == "NL" else None) or _ADDR_RE.match(raw)
    if not m:
        return raw or None, None, None
    street, postcode, city, _cc = m.groups()
    return (street.strip() or None, " ".join(postcode.split()) or None, city.strip() or None)


def parse_dealer(rec: dict, country: str) -> dict | None:
    """
    Map an AS24 dealer-search API record to a discovery candidate (pure).

    ``domain`` is None (the API exposes no website — identity row resolved later);
    ``registry_id`` is the AS24 ``customerId`` so re-runs dedup on (source, registry_id, country).
    """
    name = (rec.get("companyName") or "").strip() or None
    cid = rec.get("customerId")
    if not name or cid is None:
        return None
    street, postcode, city = parse_address(rec.get("address"), country)
    return {
        "domain": None,
        "country": country,
        "source_layer": _SOURCE_LAYER,
        "source": _SOURCE,
        "url": None,
        "name": name,
        "address": street,
        "city": city,
        "postcode": postcode,
        "phone": None,
        "email": None,
        "lat": None,
        "lng": None,
        "registry_id": str(cid),
        "external_refs": {
            "as24_customer_id": cid,
            "slug": rec.get("slug"),
            "rating": rec.get("rating"),
            "rating_count": rec.get("ratingCount"),
        },
    }


async def fetch_page(client: httpx.AsyncClient, country: str, page_index: int,
                     size: int = _PAGE_SIZE) -> tuple[list[dict], int]:
    """Fetch one dealer-search API page. Returns (results, totalDealers)."""
    host = _COUNTRY_HOST[country]
    url = f"https://{host}/dealer-search/api"
    r = await client.get(url, params={
        "country": country, "pageIndex": page_index, "size": size, "sortBy": "best",
    }, headers=_HDR)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        return [], 0
    results = data.get("results") or []
    total = data.get("totalDealers")
    return (results if isinstance(results, list) else []), (int(total) if isinstance(total, (int, float)) else 0)


class AS24DealerSource:
    """Orchestrator Source adapter: AS24 dealer-search API -> per-country dealer identity candidates.

    Paginates ``pageIndex`` (size 100) to ``ceil(total/size)`` and YIELDS candidates (the
    orchestrator's idempotent sink upserts them). Country-gated to the 5 served countries;
    a non-served country (e.g. CH) yields nothing. Uses the injected httpx client — the API is
    not Cloudflare-gated, so no curl_cffi is needed (verified 2026-06-09).
    """

    COUNTRIES = _COUNTRIES

    def __init__(self, client: httpx.AsyncClient, *, limit: int = 0, size: int = _PAGE_SIZE):
        self._client = client
        self._limit = limit          # >0 bounds dealers/country (validation); 0 = full census
        self._size = max(1, min(size, _PAGE_SIZE))  # API hard-caps at 100

    async def discover(self, country: str):
        if country not in _COUNTRY_HOST:
            return
        # Drain pages until one comes back empty or short (the last page). This is
        # robust to ``totalDealers`` drift — we never trust the declared count to
        # decide when to stop, only the data actually returned.
        emitted = 0
        for page_index in range(1, _PAGE_CAP + 1):
            results, _ = await fetch_page(self._client, country, page_index, self._size)
            if not results:
                break
            for rec in results:
                cand = parse_dealer(rec, country)
                if cand:
                    emitted += 1
                    yield cand
                    if self._limit and emitted >= self._limit:
                        return
            if len(results) < self._size:
                break  # short page = last page
            if page_index > 1:
                await asyncio.sleep(0.3)  # polite spacing between API pages


_UPSERT = """
INSERT INTO discovery_candidates
  (domain, country, source_layer, source, url, name, address, city, postcode,
   phone, email, lat, lng, registry_id, external_refs)
VALUES (NULL,$1,$2,$3,NULL,$4,$5,$6,$7,NULL,NULL,NULL,NULL,$8,$9::jsonb)
ON CONFLICT (source, registry_id, country) WHERE domain IS NULL AND registry_id IS NOT NULL
DO UPDATE SET last_seen = NOW()
WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'
"""


async def run(limit: int = 0, countries: list[str] | None = None) -> int:
    """Standalone: enumerate AS24 dealers and upsert as identity candidates. Returns count."""
    import json

    countries = countries or list(_COUNTRIES)
    inserted = 0
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    try:
        async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
            src = AS24DealerSource(client, limit=limit)
            for country in countries:
                got = 0
                async for cand in src.discover(country):
                    await pool.execute(
                        _UPSERT,
                        cand["country"], cand["source_layer"], cand["source"], cand["name"],
                        cand["address"], cand["city"], cand["postcode"], cand["registry_id"],
                        json.dumps(cand["external_refs"]),
                    )
                    inserted += 1
                    got += 1
                log.info("as24_dealers %s upserted=%d", country, got)
            log.info("DONE as24_dealers total_upserted=%d", inserted)
    finally:
        await pool.close()
    return inserted


if __name__ == "__main__":
    asyncio.run(run(limit=int(os.environ.get("AS24_LIMIT", "0"))))
