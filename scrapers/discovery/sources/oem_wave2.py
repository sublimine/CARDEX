"""
OEM Wave 2 — Renault, Dacia, SEAT dealer-locator geo-sweep.

Verified live 2026-06-07 from a residential IP (see AUDIT_SCRATCH/oem_wave2.md).

  brand     shape                              countries
  ───────   ────────────────────────────────   ────────────────────────────
  renault   POST /wired/commerce/v2/dealers/locator (array response)  DE/FR/ES/NL/BE/CH
  dacia     same endpoint, brand="DACIA"                              DE/FR/ES/NL/BE/CH
  seat      GET {page}.snw.xml (XML response) + D'Ieteren BE (JSON)  DE/FR/ES/NL/CH/BE

Geo-sweep: fixed grids of 14–20 cities per country; dealer dedup in-memory by
registry_id (birId_siteId for Renault/Dacia, partner_id/WorkLocationId for SEAT)
before every upsert call.

Only writes to `discovery_candidates`. No schema migrations.

Usage:
    python -m scrapers.discovery.sources.oem_wave2
    OEM_W2_BRANDS=renault,seat OEM_W2_COUNTRIES=DE,FR python -m scrapers.discovery.sources.oem_wave2
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

log = logging.getLogger("oem_wave2")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [oem_wave2] %(message)s",
)

_DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
_THROTTLE_S = float(os.environ.get("OEM_W2_THROTTLE_S", "0.6"))
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# ── geo-sweep city grids (lat, lng) ───────────────────────────────────────────
_GEO: dict[str, list[tuple[float, float]]] = {
    "DE": [
        (53.55, 10.00), (53.08,  8.80), (52.37,  9.73), (54.09, 12.14),
        (52.52, 13.40), (51.34, 12.37), (51.05, 13.74), (50.94,  6.96),
        (51.51,  7.46), (51.23,  6.78), (50.11,  8.68), (50.98, 11.03),
        (49.45, 11.08), (48.14, 11.58), (48.78,  9.18), (47.99,  7.85),
        (48.37, 10.90), (51.46,  7.01),
    ],
    "FR": [
        (48.85,  2.35), (43.30,  5.37), (45.75,  4.85), (43.60,  1.44),
        (43.71,  7.26), (47.22, -1.55), (48.57,  7.75), (43.61,  3.88),
        (44.84, -0.58), (50.63,  3.07), (48.11, -1.68), (49.26,  4.03),
        (45.19,  5.72), (45.78,  3.08), (47.39,  0.69), (48.39, -4.49),
        (49.44,  1.10), (49.18, -0.36), (47.32,  5.04), (45.83,  1.26),
    ],
    "ES": [
        (40.42, -3.70), (41.39,  2.17), (39.47, -0.37), (37.39, -5.99),
        (41.65, -0.89), (36.72, -4.42), (37.99, -1.13), (39.57,  2.65),
        (28.10,-15.41), (43.26, -2.93), (38.35, -0.49), (41.65, -4.72),
        (37.89, -4.78), (43.37, -8.40),
    ],
    "NL": [(52.37, 4.90), (51.44, 5.47), (53.22, 6.57)],
    "BE": [(50.85, 4.35), (50.63, 5.57)],
    "CH": [(47.38, 8.54), (46.20, 6.15), (46.95, 7.45)],
}

# SEAT: country → (page-URL-prefix, 3-letter ISO code for query param)
_SEAT_SNW: dict[str, tuple[str, str]] = {
    "DE": ("https://www.seat.de/kontakt/haendlersuche", "deu"),
    "FR": ("https://www.seat.fr/trouver-un-distributeur", "fra"),
    "ES": ("https://www.seat.es/red-de-concesionarios-seat", "esp"),
    "NL": ("https://www.seat.nl/dealers", "nld"),
    "CH": ("https://www.seat.ch/de/haendlersuche", "che"),
}
_SEAT_BE_URL = "https://dealerlocator-api.dieteren.be/api/workLocations?templateId=100&language=fr"

# Renault/Dacia: country → (host, language-code)
_RENAULT_DOMAINS: dict[str, tuple[str, str]] = {
    "DE": ("www.renault.de", "de"),
    "FR": ("www.renault.fr", "fr"),
    "ES": ("www.renault.es", "es"),
    "NL": ("www.renault.nl", "nl"),
    "BE": ("fr.renault.be", "fr"),
    "CH": ("de.renault.ch", "de"),
}
_DACIA_DOMAINS: dict[str, tuple[str, str]] = {
    "DE": ("www.dacia.de", "de"),
    "FR": ("www.dacia.fr", "fr"),
    "ES": ("www.dacia.es", "es"),
    "NL": ("www.dacia.nl", "nl"),
    "BE": ("fr.dacia.be", "fr"),
    "CH": ("de.dacia.ch", "de"),
}


# ── pure value helpers (mirrors oem_locators) ─────────────────────────────────
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
def parse_renault_dealer(d: dict, country: str, brand: str = "renault") -> dict | None:
    """Parse one dealer from the Renault/Dacia locator array response.

    The API returns a flat list. Each element has brand-keyed sub-object
    ('renault' or 'dacia') that may carry dwsLink (the dealer's own website).
    registry_id = birId + '_' + siteId.
    """
    name = _s(d.get("name"))
    if not name:
        return None
    bir_id = _s(d.get("birId"))
    site_id = _s(d.get("siteId"))
    registry_id = f"{bir_id}_{site_id}" if bir_id and site_id else _s(d.get("dealerId"))

    brand_block: dict = d.get(brand) or {}
    dws_link = _normalize_url(brand_block.get("dwsLink"))

    geo: dict = d.get("geolocalization") or {}
    return {
        "domain": _domain(dws_link),
        "country": country,
        "source_layer": 1,
        "source": f"oem:{brand}",
        "url": dws_link,
        "name": name,
        "address": _s(d.get("streetAddress")),
        "city": _s(d.get("locality")),
        "postcode": _s(d.get("postalCode")),
        "phone": _s((brand_block.get("telephone") or {}).get("value")),
        "email": None,
        "lat": _f(geo.get("lat")),
        "lng": _f(geo.get("lon")),
        "registry_id": registry_id,
        "external_refs": {"bir_id": bir_id, "site_id": site_id, "dealer_id": _s(d.get("dealerId"))},
    }


def parse_seat_xml_dealer(partner_el: ET.Element, country: str) -> dict | None:
    """Parse one <partner> element from the SEAT SNW XML locator.

    <url> may be bare domain (e.g. 'www.seat.es/concesionario') or full URL.
    registry_id = partner_id attribute/element.
    """
    name = _s(partner_el.findtext("name"))
    if not name:
        return None
    raw_url = _s(partner_el.findtext("url"))
    website = _normalize_url(raw_url)
    return {
        "domain": _domain(website),
        "country": country,
        "source_layer": 1,
        "source": "oem:seat",
        "url": website,
        "name": name,
        "address": _s(partner_el.findtext("street")),
        "city": _s(partner_el.findtext("city")),
        "postcode": _s(partner_el.findtext("zip_code")),
        "phone": _s(partner_el.findtext("phone1")),
        "email": _s(partner_el.findtext("email")),
        "lat": _f(partner_el.findtext("latitude")),
        "lng": _f(partner_el.findtext("longitude")),
        "registry_id": _s(partner_el.findtext("partner_id")),
        "external_refs": {"partner_id": _s(partner_el.findtext("partner_id"))},
    }


def parse_seat_be_dealer(d: dict) -> dict | None:
    """Parse one dealer from the D'Ieteren workLocations JSON (SEAT BE).

    Top-level keys are uppercase. URL field is 'URL'.
    registry_id = WorkLocationId.
    """
    name = _s(d.get("NAME"))
    if not name:
        return None
    website = _normalize_url(d.get("URL"))
    return {
        "domain": _domain(website),
        "country": "BE",
        "source_layer": 1,
        "source": "oem:seat",
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


# ── network fetchers ──────────────────────────────────────────────────────────
async def _fetch_renault_page(
    client: httpx.AsyncClient,
    host: str,
    brand_upper: str,
    lat: float,
    lng: float,
    country: str,
    lang: str,
) -> list[dict]:
    url = f"https://{host}/wired/commerce/v2/dealers/locator"
    body = {
        "brand": brand_upper,
        "location": {"lat": lat, "lon": lng, "country": country},
        "count": 100,
        "milesUnit": False,
        "language": lang,
    }
    try:
        r = await client.post(
            url,
            json=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Referer": f"https://{host}/",
                "Origin": f"https://{host}",
                "User-Agent": _BROWSER_UA,
            },
        )
        if r.status_code != 200:
            log.warning("%s %s POST %s HTTP %d", brand_upper, country, url, r.status_code)
            return []
        data = r.json()
        if not isinstance(data, list):
            log.warning("%s %s unexpected response type: %s", brand_upper, country, type(data).__name__)
            return []
        return data
    except Exception as exc:  # noqa: BLE001
        log.warning("%s %s fetch error: %s", brand_upper, country, exc)
        return []


async def fetch_renault_country(
    client: httpx.AsyncClient,
    country: str,
    brand: str = "renault",
) -> list[dict]:
    """Geo-sweep one country for Renault or Dacia, dedup by registry_id."""
    domains_map = _DACIA_DOMAINS if brand == "dacia" else _RENAULT_DOMAINS
    cfg = domains_map.get(country)
    if not cfg:
        return []
    host, lang = cfg
    brand_upper = brand.upper()
    centers = _GEO.get(country, [])
    seen_ids: set[str] = set()
    results: list[dict] = []

    for lat, lng in centers:
        raw_list = await _fetch_renault_page(client, host, brand_upper, lat, lng, country, lang)
        for d in raw_list:
            cand = parse_renault_dealer(d, country, brand)
            if not cand:
                continue
            rid = cand.get("registry_id") or ""
            if rid and rid in seen_ids:
                continue
            if rid:
                seen_ids.add(rid)
            results.append(cand)
        await asyncio.sleep(_THROTTLE_S)

    log.info("oem:%s %s — geo-sweep done: %d unique candidates", brand, country, len(results))
    return results


async def fetch_seat_country(
    client: httpx.AsyncClient,
    country: str,
) -> list[dict]:
    """Geo-sweep one country for SEAT (SNW XML). BE uses D'Ieteren JSON."""
    if country == "BE":
        return await _fetch_seat_be(client)

    cfg = _SEAT_SNW.get(country)
    if not cfg:
        return []
    page_url_base, iso3 = cfg
    snw_url = f"{page_url_base}.snw.xml"
    centers = _GEO.get(country, [])
    seen_ids: set[str] = set()
    results: list[dict] = []

    for lat, lng in centers:
        try:
            r = await client.get(
                snw_url,
                params={"app": "seat", "lat": lat, "lng": lng, "radius": 999, "country": iso3},
                headers={"User-Agent": _BROWSER_UA, "Accept": "application/xml, text/xml, */*"},
            )
            if r.status_code != 200:
                log.warning("oem:seat %s HTTP %d at (%.2f,%.2f)", country, r.status_code, lat, lng)
                await asyncio.sleep(_THROTTLE_S)
                continue
            try:
                root = ET.fromstring(r.text)
            except ET.ParseError as exc:
                log.warning("oem:seat %s XML parse error at (%.2f,%.2f): %s", country, lat, lng, exc)
                await asyncio.sleep(_THROTTLE_S)
                continue
            for partner_el in root.findall(".//partner"):
                cand = parse_seat_xml_dealer(partner_el, country)
                if not cand:
                    continue
                rid = cand.get("registry_id") or ""
                if rid and rid in seen_ids:
                    continue
                if rid:
                    seen_ids.add(rid)
                results.append(cand)
        except Exception as exc:  # noqa: BLE001
            log.warning("oem:seat %s error at (%.2f,%.2f): %s", country, lat, lng, exc)
        await asyncio.sleep(_THROTTLE_S)

    log.info("oem:seat %s — geo-sweep done: %d unique candidates", country, len(results))
    return results


async def _fetch_seat_be(client: httpx.AsyncClient) -> list[dict]:
    """Fetch all SEAT Belgium dealers from D'Ieteren API (single call)."""
    try:
        r = await client.get(
            _SEAT_BE_URL,
            headers={"Accept": "application/json", "User-Agent": _BROWSER_UA},
        )
        if r.status_code != 200:
            log.warning("oem:seat BE D'Ieteren HTTP %d", r.status_code)
            return []
        data = r.json()
        items: list[dict] = data.get("Dealers") or []
        results = [c for c in (parse_seat_be_dealer(d) for d in items) if c]
        log.info("oem:seat BE D'Ieteren — %d candidates", len(results))
        return results
    except Exception as exc:  # noqa: BLE001
        log.warning("oem:seat BE error: %s", exc)
        return []


# ── sink (mirrors oem_locators exactly) ────────────────────────────────────────
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
        domain, c.get("country"), c.get("source_layer"), c.get("source"), c.get("url"),
        c.get("name"), c.get("address"), c.get("city"), c.get("postcode"), c.get("phone"),
        c.get("email"), c.get("lat"), c.get("lng"), registry_id,
        json.dumps(c.get("external_refs") or {}),
    )
    try:
        await pool.execute(_UPSERT_DOMAIN if domain else _UPSERT_IDENTITY, *params)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("upsert failed source=%s name=%r: %s", c.get("source"), (c.get("name") or "")[:50], exc)
        return False


# ── orchestration ─────────────────────────────────────────────────────────────
_ALL_BRANDS = ("renault", "dacia", "seat")
_COUNTRIES = ("DE", "FR", "ES", "NL", "BE", "CH")


async def run(
    brands: list[str] | None = None,
    countries: list[str] | None = None,
) -> dict[str, int]:
    brands = (
        brands
        or [b.strip() for b in os.environ.get("OEM_W2_BRANDS", "").split(",") if b.strip()]
        or list(_ALL_BRANDS)
    )
    countries = (
        countries
        or [c.strip().upper() for c in os.environ.get("OEM_W2_COUNTRIES", "").split(",") if c.strip()]
        or list(_COUNTRIES)
    )

    stats: dict[str, int] = {}
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=6)
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            for brand in brands:
                for country in countries:
                    key = f"{country}:oem:{brand}"
                    if brand in ("renault", "dacia"):
                        cands = await fetch_renault_country(client, country, brand)
                    elif brand == "seat":
                        cands = await fetch_seat_country(client, country)
                    else:
                        log.warning("unknown brand %s — skipping", brand)
                        continue

                    fetched = len(cands)
                    written = 0
                    for cand in cands:
                        if await _upsert(pool, cand):
                            written += 1
                    stats[key] = written
                    with_web = sum(1 for c in cands if c.get("domain"))
                    log.info(
                        "oem:%s %s — fetched=%d with_web=%d upserted=%d",
                        brand, country, fetched, with_web, written,
                    )
    finally:
        await pool.close()

    total = sum(stats.values())
    log.info("DONE oem_wave2 — %d candidates written across %d (brand,country) pairs", total, len(stats))
    return stats


if __name__ == "__main__":
    asyncio.run(run())
