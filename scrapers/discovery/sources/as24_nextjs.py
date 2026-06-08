"""
AutoScout24 dealer directory via internal JSON API + Next.js SSR profile pages.

The dealer LIST uses the internal Next.js API route at:
  GET https://www.autoscout24.de/dealer-search/api
  params: country=DE, pageIndex=N, size=50, sortBy=best

Each dealer PROFILE page (https://www.autoscout24.de/haendler/<slug>) embeds
dealerInfoPage.homepageUrl in __NEXT_DATA__ SSR JSON.

Confirmed countries: DE (19.7k dealers), BE (3.8k), FR (~7.5k), NL (~3.5k).
CH/ES/IT return via the same API — enable if needed.

Usage:
    python -m scrapers.discovery.sources.as24_nextjs
    AS24_COUNTRIES=DE,BE python -m scrapers.discovery.sources.as24_nextjs
    AS24_COUNTRIES=FR,NL python -m scrapers.discovery.sources.as24_nextjs
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import AsyncIterator
from urllib.parse import urlparse

import asyncpg
import httpx

log = logging.getLogger("as24_nextjs")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [as24_nextjs] %(message)s",
)

_DSN = os.environ.get(
    "DATABASE_URL",
    "postgres://cardex:cardex_dev_only@localhost:5432/cardex",
)

_API_URL = "https://www.autoscout24.de/dealer-search/api"
_API_SIZE = 50  # dealers per API page

# Country → (api_country code, profile URL base)
_COUNTRY_CONFIG: dict[str, dict] = {
    "DE": {
        "api_country": "DE",
        "profile_base": "https://www.autoscout24.de/haendler/",
        "country": "DE",
    },
    "BE": {
        "api_country": "BE",
        "profile_base": "https://www.autoscout24.be/nl/verkopers/",
        "country": "BE",
    },
    "FR": {
        "api_country": "FR",
        "profile_base": "https://www.autoscout24.fr/garages/",
        "country": "FR",
    },
    "NL": {
        "api_country": "NL",
        "profile_base": "https://www.autoscout24.nl/autobedrijven/",
        "country": "NL",
    },
    "IT": {
        "api_country": "IT",
        "profile_base": "https://www.autoscout24.it/concessionari/",
        "country": "IT",
    },
    "ES": {
        "api_country": "ES",
        "profile_base": "https://www.autoscout24.es/profesionales/",
        "country": "ES",
    },
    "AT": {
        "api_country": "AT",
        "profile_base": "https://www.autoscout24.at/haendler/",
        "country": "AT",
    },
    "LU": {
        "api_country": "LU",
        "profile_base": "https://www.autoscout24.lu/professional/",
        "country": "LU",
    },
}

_HEADERS_API = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, */*",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Referer": "https://www.autoscout24.de/haendler/",
}

_HEADERS_PROFILE = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S
)
_CONC_PROFILES = 3  # profile pages fetched concurrently per batch
_DELAY = 0.6        # seconds between API page requests
_PROFILE_SLEEP = 0.4  # sleep inside semaphore before each profile fetch
_RETRY_429_S = 12.0   # backoff when rate-limited


def _apex(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        netloc = urlparse(url).netloc.lower()
        netloc = re.sub(r":\d+$", "", netloc)
        netloc = netloc.lstrip("www.")
        if "." not in netloc or len(netloc) < 4:
            return None
        if "autoscout24" in netloc:
            return None
        return netloc
    except Exception:
        return None


async def _get_html(client: httpx.AsyncClient, url: str) -> str:
    for attempt in range(3):
        try:
            r = await client.get(url, headers=_HEADERS_PROFILE, timeout=20, follow_redirects=True)
            if r.status_code == 200:
                return r.text
            if r.status_code == 429:
                wait = _RETRY_429_S * (attempt + 1)
                log.debug("429 on %s, sleeping %.0fs", url, wait)
                await asyncio.sleep(wait)
                continue
        except Exception as exc:
            log.debug("fetch %s: %s", url, type(exc).__name__)
            break
    return ""


def _parse_next_data(html: str) -> dict:
    m = _NEXT_DATA_RE.search(html)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


async def _list_dealers_api(
    client: httpx.AsyncClient, api_country: str, page_index: int
) -> tuple[list[dict], int, int]:
    """Return (results, totalDealers, numberOfPages) from the dealer list API."""
    params = {
        "country": api_country,
        "pageIndex": page_index,
        "size": _API_SIZE,
        "sortBy": "best",
    }
    try:
        r = await client.get(
            _API_URL, params=params, headers=_HEADERS_API, timeout=15, follow_redirects=True
        )
        if r.status_code == 200:
            d = json.loads(r.content)
            return (
                d.get("results", []),
                d.get("totalDealers", 0),
                d.get("numberOfPages", 0),
            )
        log.debug("api %s p%d: status %d", api_country, page_index, r.status_code)
    except Exception as exc:
        log.debug("api %s p%d: %s", api_country, page_index, type(exc).__name__)
    return [], 0, 0


async def _get_homepage_url(
    client: httpx.AsyncClient, profile_base: str, slug: str
) -> str | None:
    """Return homepageUrl from dealer profile page via __NEXT_DATA__."""
    url = f"{profile_base}{slug}"
    html = await _get_html(client, url)
    if not html:
        return None
    d = _parse_next_data(html)
    dip = d.get("props", {}).get("pageProps", {}).get("dealerInfoPage", {})
    if not isinstance(dip, dict):
        return None
    return dip.get("homepageUrl") or None


def _parse_address(address_str: str) -> tuple[str | None, str | None, str | None]:
    """Parse 'Street Nr, PLZ City, CC' → (street, postcode, city)."""
    if not address_str:
        return None, None, None
    parts = [p.strip() for p in address_str.split(",")]
    street = parts[0] if parts else None
    city = postcode = None
    if len(parts) >= 2:
        city_pc = parts[-2].strip() if len(parts) >= 3 else parts[-1].strip()
        pc_city = city_pc.split(" ", 1)
        if len(pc_city) == 2 and pc_city[0].replace("-", "").isdigit():
            postcode = pc_city[0]
            city = pc_city[1]
    return street, postcode, city


async def discover_with_names(
    country: str, client: httpx.AsyncClient
) -> AsyncIterator[dict]:
    """Async generator yielding dealer candidates (with name/address/web) for a country."""
    cfg = _COUNTRY_CONFIG.get(country)
    if not cfg:
        log.warning("No config for country %s", country)
        return

    api_country = cfg["api_country"]
    profile_base = cfg["profile_base"]

    # Page 1 to discover totals
    dealers_page1, total_dealers, total_pages = await _list_dealers_api(
        client, api_country, 1
    )
    if not total_pages:
        log.error("%s: API returned 0 pages (country=%s)", country, api_country)
        return

    log.info(
        "%s: %d dealers across %d pages (size=%d)",
        country, total_dealers, total_pages, _API_SIZE,
    )

    seen_slugs: set[str] = set()
    total_yielded = 0

    async def process_batch(dealer_list: list[dict]) -> list[dict]:
        """Fetch profiles for a batch of dealers, return records with homepage."""
        sem = asyncio.Semaphore(_CONC_PROFILES)
        out: list[dict] = []

        async def fetch_one(dealer_info: dict) -> dict | None:
            slug = dealer_info.get("slug", "")
            if not slug or slug in seen_slugs:
                return None
            seen_slugs.add(slug)
            async with sem:
                await asyncio.sleep(_PROFILE_SLEEP)
                homepage = await _get_homepage_url(client, profile_base, slug)
            if not homepage:
                return None
            domain = _apex(homepage)
            if not domain:
                return None

            street, postcode, city = _parse_address(dealer_info.get("address", ""))
            return {
                "domain": domain,
                "country": country,
                "source_layer": 4,
                "source": "as24",
                "url": homepage,
                "name": dealer_info.get("companyName"),
                "address": street,
                "city": city,
                "postcode": postcode,
                "registry_id": None,
                "external_refs": {
                    "as24_slug": slug,
                    "as24_id": dealer_info.get("customerId"),
                    "resolved_via": "as24_profile",
                },
            }

        results_raw = await asyncio.gather(*[fetch_one(di) for di in dealer_list])
        out = [r for r in results_raw if r]
        return out

    # Process page 1
    for rec in await process_batch(dealers_page1):
        total_yielded += 1
        yield rec

    # Remaining pages
    for page_num in range(2, total_pages + 1):
        await asyncio.sleep(_DELAY)
        dl, _, _ = await _list_dealers_api(client, api_country, page_num)
        if not dl:
            log.debug("%s: page %d returned empty", country, page_num)
            continue
        for rec in await process_batch(dl):
            total_yielded += 1
            yield rec
        if page_num % 50 == 0:
            log.info(
                "%s: page %d/%d done, yielded=%d",
                country, page_num, total_pages, total_yielded,
            )


async def upsert(pool: asyncpg.Pool, cand: dict) -> bool:
    try:
        result = await pool.execute(
            """
            INSERT INTO discovery_candidates
              (domain, country, source_layer, source, url, name, address, city,
               postcode, phone, email, lat, lng, registry_id, external_refs)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb)
            ON CONFLICT (domain, country) WHERE domain IS NOT NULL
            DO NOTHING
            """,
            cand.get("domain"), cand.get("country"), cand.get("source_layer", 4),
            cand.get("source"), cand.get("url"),
            cand.get("name"), cand.get("address"), cand.get("city"),
            cand.get("postcode"), None, None,
            None, None, cand.get("registry_id"),
            json.dumps(cand.get("external_refs") or {}),
        )
        return "INSERT 0 1" in result
    except Exception as exc:
        log.debug("upsert %s: %s", cand.get("domain"), exc)
        return False


async def run() -> None:
    countries = os.environ.get("AS24_COUNTRIES", "DE,BE,FR,NL,IT,ES,AT,LU").split(",")
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    stats: dict[str, dict] = {}
    t0 = time.monotonic()

    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
        for country in countries:
            country = country.strip().upper()
            if country not in _COUNTRY_CONFIG:
                log.warning("Skipping unknown country %s", country)
                continue

            inserted = seen = 0
            async for cand in discover_with_names(country, client):
                seen += 1
                if await upsert(pool, cand):
                    inserted += 1
                if seen % 100 == 0:
                    elapsed = time.monotonic() - t0
                    log.info(
                        "%s: seen=%d inserted=%d elapsed=%.0fs",
                        country, seen, inserted, elapsed,
                    )
            stats[country] = {"seen": seen, "inserted": inserted}
            log.info("%s DONE: seen=%d inserted=%d", country, seen, inserted)

    await pool.close()
    total_inserted = sum(v["inserted"] for v in stats.values())
    elapsed = time.monotonic() - t0
    log.info("DONE: %s total=%d elapsed=%.0fs", stats, total_inserted, elapsed)
    print(f"\n=== AS24 NEXTJS RESULTS ===")
    for c, v in sorted(stats.items()):
        print(f"  {c}: seen={v['seen']} inserted={v['inserted']}")
    print(f"  TOTAL: +{total_inserted} in {elapsed:.0f}s")


if __name__ == "__main__":
    asyncio.run(run())
