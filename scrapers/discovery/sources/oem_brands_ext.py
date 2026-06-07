"""
OEM brands extension — config-driven sweep for brands verified 2026-06-07.

All endpoints verified live (curl + python) before implementation.  No invented
data — brands whose locators returned 4xx/blocked are listed in the header and
NOT implemented here.

Verified live and implemented
─────────────────────────────
  brand    shape                                  countries
  ──────   ────────────────────────────────────   ────────────────────────────
  cupra    SNW XML (same backend as SEAT wave2)   DE FR ES NL CH
           + D'Ieteren JSON templateId=202        BE

Blocked / unreachable from this host (NOT implemented — no invented data)
─────────────────────────────────────────────────────────────────────────
  mini        STOLO domain NXDOMAIN globally; mini.de/mini.com timeout
  jeep/alfa   dealerlocator.fiat.com: 404; stellantis new API: DNS fail
  peugeot     403 from this host (Cloudflare geo-block)
  citroen     403 from this host
  opel        403 from this host
  volvo       volvocars.com: 403; retailerlocator sub-domain: DNS fail
  nissan      eu.nissan-api.net: requires auth token (400 Unauthorized)
  honda       find-a-dealer.html: no XHR endpoint discoverable without JS
  suzuki      haendlersuche page 404 for DE; no API discoverable
  mitsubishi  TYPO3 site; no JSON endpoint found (all eID variants → 404/500)
  mercedes    Akamai WAF (documented from prior wave)
  ford        Akamai WAF (documented from prior wave)
  mazda       eu.mazda.de APIs: all DNS fail or 404

Cupra SNW notes
───────────────
The SNW XML endpoint is shared with SEAT (same backend, same tenant pool).
Querying with app=cupra returns ALL dealers regardless of Cupra status.
The <cupra_specialized> field is the reliable filter: only dealers where
cupra_specialized == 'true' are genuine Cupra points-of-sale (verified by
comparing count=98 on DE, of which 59 are cupra_specialized vs 98 total SEAT).
Belgium (no SNW coverage) uses D'Ieteren's workLocations API, templateId=202,
which returns CUPRA-branded dealers exclusively.

Verified counts (cupra_specialized=true where applicable):
  DE:  59 dealers, 16 with_url   (cupraofficial.de SNW)
  FR:  25 dealers,  2 with_url   (seat.fr SNW app=cupra)
  ES:  28 dealers, 28 with_url   (seat.es SNW app=cupra)
  NL:  40 dealers, 40 with_url   (seat.nl SNW app=cupra)
  CH:  80 dealers, 70 with_url   (seat.ch SNW app=cupra)
  BE:  69 dealers, 22 with_url   (D'Ieteren templateId=202)

Only writes to `discovery_candidates`. No schema migrations.

Usage:
    python -m scrapers.discovery.sources.oem_brands_ext
    OEM_EXT_BRANDS=cupra OEM_EXT_COUNTRIES=DE,FR python -m scrapers.discovery.sources.oem_brands_ext
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any

import asyncpg
import httpx

log = logging.getLogger("oem_brands_ext")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [oem_ext] %(message)s",
)

_DSN = os.environ.get(
    "DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex"
)
_THROTTLE_S = float(os.environ.get("OEM_EXT_THROTTLE_S", "0.6"))
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


# ── pure value helpers (mirrors oem_locators / oem_wave2) ─────────────────────
def _f(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _s(val: Any) -> str | None:
    if val is None:
        return None
    out = str(val).strip()
    return out or None


def _normalize_url(url: Any) -> str | None:
    if not url:
        return None
    url = str(url).strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
    except ValueError:
        return None
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or None


# ── pure parsers ──────────────────────────────────────────────────────────────

def parse_cupra_snw_dealer(partner_el: ET.Element, country: str) -> dict | None:
    """Parse one <partner> element from the Cupra/SEAT SNW XML locator.

    Only dealers where <cupra_specialized> == 'true' are genuine Cupra retailers.
    Coordinates are NOT embedded in the XML (mapcoordinate/lat always empty for
    this endpoint — verified live).  URL is in <url>; may be bare domain.
    registry_id = <partner_id> (e.g. 'DES55CG').
    """
    # Filter: only genuine Cupra dealers
    if partner_el.findtext("cupra_specialized") != "true":
        return None
    name = _s(partner_el.findtext("name"))
    if not name:
        return None
    raw_url = _s(partner_el.findtext("url"))
    website = _normalize_url(raw_url) if raw_url else None
    return {
        "domain": _domain(website),
        "country": country,
        "source_layer": 1,
        "source": "oem:cupra",
        "url": website,
        "name": name,
        "address": _s(partner_el.findtext("street")),
        "city": _s(partner_el.findtext("city")),
        "postcode": _s(partner_el.findtext("zip_code")),
        "phone": _s(partner_el.findtext("phone1")),
        "email": _s(partner_el.findtext("email")),
        "lat": None,   # not provided by this endpoint
        "lng": None,
        "registry_id": _s(partner_el.findtext("partner_id")),
        "external_refs": {
            "partner_id": _s(partner_el.findtext("partner_id")),
            "installation_code_kvps": _s(partner_el.findtext("installation_code_kvps")),
        },
    }


def parse_cupra_be_dealer(d: dict) -> dict | None:
    """Parse one dealer from D'Ieteren workLocations API (templateId=202, Cupra BE).

    All keys are uppercase.  URL field is 'URL'.  GPSLAT/GPSLONG are strings.
    registry_id = WorkLocationId (e.g. 'WOLO000174').
    """
    name = _s(d.get("NAME"))
    if not name:
        return None
    website = _normalize_url(d.get("URL"))
    return {
        "domain": _domain(website),
        "country": "BE",
        "source_layer": 1,
        "source": "oem:cupra",
        "url": website,
        "name": name,
        "address": _s(d.get("ADDRESS")),
        "city": _s(d.get("CITY")),
        "postcode": _s(d.get("ZIP")),
        "phone": _s(d.get("TEL")),
        "email": _s(d.get("MAIL")),
        "lat": _f(d.get("GPSLAT")),
        "lng": _f(d.get("GPSLONG")),
        "registry_id": _s(d.get("WorkLocationId")),
        "external_refs": {"work_location_id": _s(d.get("WorkLocationId"))},
    }


# ── Cupra SNW config (verified 2026-06-07) ─────────────────────────────────────
# Cupra DE uses cupraofficial.de; all other countries route through seat.*/cupra* domains.
# The SNW path varies per country — verified live that these exact URLs return 200 + valid XML.
_CUPRA_SNW: dict[str, tuple[str, str, float, float]] = {
    # country → (snw_url, iso3_lang, center_lat, center_lng)
    "DE": ("https://www.cupraofficial.de/kontakt/haendlersuche.snw.xml", "deu", 51.0, 10.0),
    "FR": ("https://www.seat.fr/trouver-un-distributeur.snw.xml", "fra", 48.85, 2.35),
    "ES": ("https://www.seat.es/red-de-concesionarios-seat.snw.xml", "esp", 40.2, -3.7),
    "NL": ("https://www.seat.nl/dealers.snw.xml", "nld", 52.2, 5.3),
    "CH": ("https://www.seat.ch/de/haendlersuche.snw.xml", "deu", 46.8, 8.2),
}
# Belgium: D'Ieteren API, single call, templateId=202 = Cupra (verified)
_CUPRA_BE_URL = (
    "https://dealerlocator-api.dieteren.be/api/workLocations?templateId=202&language=fr"
)


# ── network fetchers ──────────────────────────────────────────────────────────

async def fetch_cupra_snw(client: httpx.AsyncClient, country: str) -> list[dict]:
    """Fetch all Cupra dealers for one SNW country in a single call.

    The SNW endpoint accepts a global radius (distance=9999) so one call per
    country is sufficient — no geo-sweep needed.  Filters by cupra_specialized.
    """
    cfg = _CUPRA_SNW.get(country)
    if not cfg:
        return []
    snw_url, iso3, lat, lng = cfg
    try:
        r = await client.get(
            snw_url,
            params={"app": "cupra", "language": iso3, "lat": lat, "lng": lng, "distance": 9999},
            headers={
                "User-Agent": _BROWSER_UA,
                "Accept": "application/xml, text/xml, */*",
                "Referer": snw_url.split(".snw.xml")[0],
            },
        )
        if r.status_code != 200:
            log.warning("oem:cupra %s SNW HTTP %d", country, r.status_code)
            return []
        try:
            root = ET.fromstring(r.text)
        except ET.ParseError as exc:
            log.warning("oem:cupra %s SNW XML parse error: %s", country, exc)
            return []
        results = [
            c for c in (
                parse_cupra_snw_dealer(el, country)
                for el in root.findall(".//partner")
            )
            if c
        ]
        log.info("oem:cupra %s — SNW done: %d cupra_specialized dealers", country, len(results))
        return results
    except Exception as exc:  # noqa: BLE001
        log.warning("oem:cupra %s SNW error: %s", country, exc)
        return []


async def fetch_cupra_be(client: httpx.AsyncClient) -> list[dict]:
    """Fetch all Cupra Belgium dealers from D'Ieteren API (single call)."""
    try:
        r = await client.get(
            _CUPRA_BE_URL,
            headers={"Accept": "application/json", "User-Agent": _BROWSER_UA},
        )
        if r.status_code != 200:
            log.warning("oem:cupra BE D'Ieteren HTTP %d", r.status_code)
            return []
        data = r.json()
        items: list[dict] = data if isinstance(data, list) else (
            data.get("Dealers") or data.get("dealers") or []
        )
        results = [c for c in (parse_cupra_be_dealer(d) for d in items) if c]
        log.info("oem:cupra BE — D'Ieteren done: %d dealers", len(results))
        return results
    except Exception as exc:  # noqa: BLE001
        log.warning("oem:cupra BE error: %s", exc)
        return []


async def fetch_cupra(client: httpx.AsyncClient, country: str) -> list[dict]:
    """Dispatch Cupra fetch by country."""
    if country == "BE":
        return await fetch_cupra_be(client)
    return await fetch_cupra_snw(client, country)


# ── brand registry ─────────────────────────────────────────────────────────────
# Maps brand name → (fetcher, supported countries).
# Add new brands here once their endpoints are curl-verified.
BRANDS: dict[str, tuple] = {
    "cupra": (fetch_cupra, ("DE", "FR", "ES", "NL", "CH", "BE")),
}

_ALL_BRANDS = tuple(BRANDS.keys())
_COUNTRIES = ("DE", "FR", "ES", "NL", "BE", "CH")


# ── sink (exact copy of the pattern from oem_locators / oem_wave2) ─────────────
_COLS = (
    "domain, country, source_layer, source, url, name, address, city, postcode, "
    "phone, email, lat, lng, registry_id, external_refs"
)
_VALS = "$1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb"
_UPSERT_DOMAIN = f"""
INSERT INTO discovery_candidates ({_COLS}) VALUES ({_VALS})
ON CONFLICT (domain, country) WHERE domain IS NOT NULL
DO UPDATE SET last_seen = NOW() WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'
"""
_UPSERT_IDENTITY = f"""
INSERT INTO discovery_candidates ({_COLS}) VALUES ({_VALS})
ON CONFLICT (source, registry_id, country) WHERE domain IS NULL AND registry_id IS NOT NULL
DO UPDATE SET last_seen = NOW() WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'
"""


async def _upsert(pool: asyncpg.Pool, c: dict) -> bool:
    domain, registry_id = c.get("domain"), c.get("registry_id")
    if not domain and not registry_id:
        return False
    params = (
        domain, c.get("country"), c.get("source_layer"), c.get("source"),
        c.get("url"), c.get("name"), c.get("address"), c.get("city"),
        c.get("postcode"), c.get("phone"), c.get("email"),
        c.get("lat"), c.get("lng"), registry_id,
        json.dumps(c.get("external_refs") or {}),
    )
    try:
        await pool.execute(_UPSERT_DOMAIN if domain else _UPSERT_IDENTITY, *params)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "upsert failed source=%s name=%r: %s",
            c.get("source"), (c.get("name") or "")[:50], exc,
        )
        return False


# ── orchestration ─────────────────────────────────────────────────────────────

async def run(
    brands: list[str] | None = None,
    countries: list[str] | None = None,
) -> dict[str, int]:
    """Sweep all verified brands × countries, writing to discovery_candidates.

    Returns a stats dict keyed by '{country}:oem:{brand}' → upserted count.
    """
    brands = (
        brands
        or [b.strip() for b in os.environ.get("OEM_EXT_BRANDS", "").split(",") if b.strip()]
        or list(_ALL_BRANDS)
    )
    countries = (
        countries
        or [c.strip().upper() for c in os.environ.get("OEM_EXT_COUNTRIES", "").split(",") if c.strip()]
        or list(_COUNTRIES)
    )

    stats: dict[str, int] = {}
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=6)
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            for brand in brands:
                brand_entry = BRANDS.get(brand)
                if not brand_entry:
                    log.warning("unknown brand %r — skipping (not verified)", brand)
                    continue
                fetcher, supported = brand_entry
                for country in countries:
                    if country not in supported:
                        log.debug("oem:%s %s — not supported, skipping", brand, country)
                        continue
                    cands = await fetcher(client, country)
                    fetched = len(cands)
                    written = 0
                    for cand in cands:
                        if await _upsert(pool, cand):
                            written += 1
                    key = f"{country}:oem:{brand}"
                    stats[key] = written
                    with_web = sum(1 for c in cands if c.get("domain"))
                    log.info(
                        "oem:%s %s — fetched=%d with_web=%d upserted=%d",
                        brand, country, fetched, with_web, written,
                    )
                    await asyncio.sleep(_THROTTLE_S)
    finally:
        await pool.close()

    total = sum(stats.values())
    log.info(
        "DONE oem_brands_ext — %d candidates written across %d (brand,country) pairs",
        total, len(stats),
    )
    return stats


if __name__ == "__main__":
    asyncio.run(run())
