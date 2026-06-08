"""
OSM name-regex dealer discovery — geo-sweep with bbox grid.

Finds car dealers in OSM that are NOT tagged with shop=car / trade=cars /
craft=car_repair etc. (already covered by osm.py). Instead, this source
discovers them by matching the element NAME against dealer_terms per country.

Strategy
--------
1. Divide each country's bounding box into a regular grid of cells
   (~0.4° × 0.4° for small countries, ~0.5° × 0.5° for large ones).
2. Per cell: run an Overpass `nwr[name~"<term-alternation>",i](bbox)` query
   that returns ALL named elements inside the cell whose name contains any
   dealer term.
3. Apply a signal/noise filter: keep only elements where the name matches
   AND at least one of the following is true:
       a. the element has a website/url/contact:website tag, OR
       b. the element carries a car-related OSM tag
          (shop, craft, office, trade in a known-automotive set), OR
       c. the matching term is a "strong" unambiguous compound that never
          appears in restaurants/schools/etc.
          (autohaus, autohändler, concesionario, autobedrijf, garagebedrijf,
           concessionnaire, gebrauchtwagen, carrozzeria, autosalone,
           concessionaria, autofficina, autozentrum, autosalon, occasions,
           autodealer).
4. Skip elements already covered by the tag-based osm.py source (same OSM id
   with source='osm').  Actually, use ON CONFLICT DO NOTHING — the upsert key
   on (source, registry_id, country) handles this naturally because we use a
   different source name: 'osm_nametail'.  Domain conflicts collapse correctly.
5. Upsert using the exact ch_agvs pattern: heartbeat-only if already seen
   recently (< 1 hour), otherwise INSERT.

Overpass mirrors rotated round-robin; throttle 2 s between cells to stay
polite. Cell results are processed and freed immediately (RAM-safe).

Usage
-----
    python -m scrapers.discovery.sources.osm_nametail
    OSM_NT_COUNTRIES=BE,CH,NL python -m scrapers.discovery.sources.osm_nametail
    OSM_NT_DRY_RUN=1 ... (count matches, no DB writes)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.parse
from typing import Iterator

import asyncpg
import httpx

from scrapers.discovery.dealer_terms import DEALER_TERMS, _norm, terms_for

log = logging.getLogger("osm_nametail")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [osm_nametail] %(message)s",
)

_DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://cardex:cardex_dev_only@localhost:5432/cardex",
)
_SOURCE = "osm_nametail"
_SOURCE_LAYER = 4

_OVERPASS_ENDPOINTS: tuple[str, ...] = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    # maps.mail.ru returns 403 for non-Russian IPs — excluded intentionally
)
_OVERPASS_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}

# Country bounding boxes: (south, west, north, east)
# Used only to generate the grid cells; the actual Overpass query also
# intersects with the country's OSM area polygon to prevent cross-border leakage.
_COUNTRY_BBOX: dict[str, tuple[float, float, float, float]] = {
    "BE": (49.50, 2.54, 51.51, 6.41),
    "CH": (45.82, 5.96, 47.81, 10.49),
    "NL": (50.75, 3.36, 53.56, 7.23),
    "ES": (35.95, -9.34, 43.79, 4.33),
    "FR": (41.33, -5.14, 51.09, 9.56),
    "DE": (47.27, 5.87, 55.06, 15.04),
}

# Overpass area ids (3_600_000_000 + OSM relation id for the country boundary).
# Used to clip each bbox-cell query to elements actually inside the country.
_COUNTRY_AREA_IDS: dict[str, int] = {
    "BE": 3_600_000_000 + 52_411,
    "CH": 3_600_000_000 + 51_701,
    "NL": 3_600_000_000 + 47_796,
    "ES": 3_600_000_000 + 1_311_341,
    "FR": 3_600_000_000 + 2_202_162,
    "DE": 3_600_000_000 + 51_477,
}

# Grid cell sizes per country (degrees). Smaller countries → finer grid.
# A 0.4° cell at European latitudes ≈ 25×35 km, manageable for Overpass.
_CELL_DEG: dict[str, float] = {
    "BE": 0.3,
    "CH": 0.3,
    "NL": 0.3,
    "ES": 0.5,
    "FR": 0.5,
    "DE": 0.5,
}

# "Strong" terms: unambiguous enough that name-match alone is sufficient
# (no website or car-tag required).
_STRONG_TERMS: frozenset[str] = frozenset({
    "autohaus", "autohändler", "autohändler", "autozentrum", "autosalon",
    "gebrauchtwagen", "fahrzeughandel",
    "concesionario", "concesionaria",
    "concessionnaire",
    "autobedrijf", "garagebedrijf", "automobielbedrijf", "occasions", "autodealer",
    "carrozzeria", "autosalone", "concessionaria", "autofficina",
    "kfz",
})

# OSM shop/craft/office/trade values that indicate automotive context.
_AUTO_TAG_VALUES: frozenset[str] = frozenset({
    "car", "car_dealer", "car_repair", "car_parts", "second_hand",
    "tyres", "motorcycle", "truck", "caravan",
    "car_rental",
})

# Throttle between cell queries (seconds).
_THROTTLE_S: float = float(os.environ.get("OSM_NT_THROTTLE", "3.0"))

# Overpass query timeout (seconds) — small cells, short timeout.
_QUERY_TIMEOUT: int = 90

# Max retries per cell when all mirrors are failing (with exponential backoff).
_MAX_CELL_RETRIES: int = 3
# Base backoff in seconds for 429 / 504 responses.
_BACKOFF_429: float = 30.0
_BACKOFF_504: float = 15.0


# ---------------------------------------------------------------------------
# Grid generation
# ---------------------------------------------------------------------------

def _cells(country: str) -> Iterator[tuple[float, float, float, float]]:
    """Yield (south, west, north, east) bounding boxes for the country grid."""
    s, w, n, e = _COUNTRY_BBOX[country]
    step = _CELL_DEG.get(country, 0.4)
    lat = s
    while lat < n:
        lon = w
        lat_next = min(lat + step, n)
        while lon < e:
            lon_next = min(lon + step, e)
            yield (lat, lon, lat_next, lon_next)
            lon = lon_next
        lat = lat_next


def _cell_count(country: str) -> int:
    return sum(1 for _ in _cells(country))


# ---------------------------------------------------------------------------
# Overpass query
# ---------------------------------------------------------------------------

def _build_alternation(country: str) -> str:
    """Build a pipe-separated regex alternation of all dealer terms for the country."""
    all_terms = terms_for(country)
    # Escape regex specials in terms (parentheses in 'coches de ocasion' etc.)
    escaped = [t.replace("(", "\\(").replace(")", "\\)").replace(".", "\\.") for t in all_terms]
    return "|".join(escaped)


def _build_query(
    alternation: str,
    bbox: tuple[float, float, float, float],
    area_id: int | None = None,
) -> str:
    """Build Overpass QL query.

    When area_id is provided, elements must be inside BOTH the country area
    polygon AND the bbox cell — preventing cross-border leakage at the expense
    of a slightly larger query. Without area_id, only bbox is used (faster but
    may capture elements in neighboring countries near borders).
    """
    s, w, n, e = bbox
    bbox_str = f"{s},{w},{n},{e}"
    if area_id:
        return (
            f'[out:json][timeout:{_QUERY_TIMEOUT}];\n'
            f'area({area_id})->.country;\n'
            f'nwr[name~"{alternation}",i]({bbox_str})(area.country);\n'
            f'out body center qt;'
        )
    return (
        f'[out:json][timeout:{_QUERY_TIMEOUT}];\n'
        f'nwr[name~"{alternation}",i]({bbox_str});\n'
        f'out body center qt;'
    )


# ---------------------------------------------------------------------------
# Signal/noise filter
# ---------------------------------------------------------------------------

def _has_auto_tag(tags: dict) -> bool:
    for key in ("shop", "craft", "office", "trade", "amenity"):
        v = tags.get(key, "").lower()
        if v in _AUTO_TAG_VALUES:
            return True
    return False


def _has_website(tags: dict) -> bool:
    for key in ("website", "url", "contact:website", "contact:url"):
        if tags.get(key):
            return True
    return False


def _strong_term_hit(name: str, country: str) -> bool:
    norm_name = _norm(name)
    return any(_norm(t) in norm_name for t in _STRONG_TERMS if t in terms_for(country))


def _passes_filter(name: str, tags: dict, country: str) -> bool:
    """
    True if this element is likely a car dealer:
    - name contains a dealer term for this country (already checked by Overpass query)
    - AND (has website) OR (has automotive tag) OR (strong unambiguous term hit)
    """
    if _has_website(tags):
        return True
    if _has_auto_tag(tags):
        return True
    if _strong_term_hit(name, country):
        return True
    return False


# ---------------------------------------------------------------------------
# Candidate construction
# ---------------------------------------------------------------------------

def _normalize_url(u) -> str | None:
    if not u:
        return None
    u = str(u).strip()
    if not u:
        return None
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u.rstrip("/")


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return None
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or None


def _build_address(tags: dict) -> str | None:
    parts = [
        tags.get("addr:street"),
        tags.get("addr:housenumber"),
        tags.get("addr:postcode"),
        tags.get("addr:city"),
    ]
    parts = [p for p in parts if p]
    return ", ".join(parts) if parts else None


def _to_candidate(el: dict, country: str) -> dict | None:
    tags = el.get("tags") or {}
    name = (tags.get("name") or "").strip()
    if not name:
        return None

    if el.get("type") == "node":
        lat = el.get("lat")
        lng = el.get("lon")
    else:
        center = el.get("center") or {}
        lat = center.get("lat")
        lng = center.get("lon")

    if lat is None or lng is None:
        return None

    if not _passes_filter(name, tags, country):
        return None

    website = _normalize_url(
        tags.get("website") or tags.get("url")
        or tags.get("contact:website") or tags.get("contact:url")
    )
    domain = _domain(website)
    osm_id = f"{el.get('type')}/{el.get('id')}"

    return {
        "domain":        domain,
        "country":       country,
        "source_layer":  _SOURCE_LAYER,
        "source":        _SOURCE,
        "url":           website,
        "name":          name,
        "address":       _build_address(tags),
        "city":          tags.get("addr:city"),
        "postcode":      tags.get("addr:postcode"),
        "phone":         tags.get("phone") or tags.get("contact:phone"),
        "email":         tags.get("email") or tags.get("contact:email"),
        "lat":           float(lat),
        "lng":           float(lng),
        "registry_id":   osm_id,
        "external_refs": {
            "brand":         tags.get("brand"),
            "operator":      tags.get("operator"),
            "opening_hours": tags.get("opening_hours"),
            "osm_tags":      {k: v for k, v in tags.items() if k in (
                "shop", "craft", "office", "trade", "amenity"
            )},
        },
    }


# ---------------------------------------------------------------------------
# Overpass fetch (with mirror rotation and retry)
# ---------------------------------------------------------------------------

async def _fetch_cell(
    client: httpx.AsyncClient,
    query: str,
    bbox: tuple[float, float, float, float],
) -> list[dict]:
    """Fetch one Overpass cell, rotating mirrors with backoff on transient errors.

    Strategy:
    - Try each mirror in round-robin order.
    - On 429 (rate limit): wait _BACKOFF_429 s then retry same endpoint.
    - On 504 (timeout): wait _BACKOFF_504 s then try next mirror.
    - On 200: return immediately.
    - After _MAX_CELL_RETRIES full rounds of failures: return [] and log warning.
    """
    endpoints = list(_OVERPASS_ENDPOINTS)

    for attempt in range(_MAX_CELL_RETRIES):
        for endpoint in endpoints:
            try:
                resp = await client.post(
                    endpoint,
                    data={"data": query},
                    headers=_OVERPASS_HEADERS,
                    timeout=float(_QUERY_TIMEOUT + 15),
                )
                if resp.status_code == 200:
                    return resp.json().get("elements") or []
                elif resp.status_code == 429:
                    wait = _BACKOFF_429 * (attempt + 1)
                    log.info("overpass %s 429 — backing off %.0fs", endpoint, wait)
                    await asyncio.sleep(wait)
                    # Retry same endpoint after backoff
                    try:
                        resp2 = await client.post(
                            endpoint,
                            data={"data": query},
                            headers=_OVERPASS_HEADERS,
                            timeout=float(_QUERY_TIMEOUT + 15),
                        )
                        if resp2.status_code == 200:
                            return resp2.json().get("elements") or []
                    except Exception:
                        pass
                elif resp.status_code in (504, 502, 503):
                    log.debug("overpass %s HTTP %d — trying next mirror", endpoint, resp.status_code)
                    await asyncio.sleep(_BACKOFF_504)
                else:
                    log.debug("overpass %s HTTP %d for bbox %s", endpoint, resp.status_code, bbox)
            except httpx.TimeoutException:
                log.debug("overpass %s timeout for bbox %s", endpoint, bbox)
            except Exception as exc:
                log.debug("overpass %s error for bbox %s: %s", endpoint, bbox, exc)

        if attempt < _MAX_CELL_RETRIES - 1:
            backoff = _BACKOFF_429 * (attempt + 1)
            log.info("all mirrors failed bbox %s attempt %d/%d — waiting %.0fs", bbox, attempt + 1, _MAX_CELL_RETRIES, backoff)
            await asyncio.sleep(backoff)

    log.warning("all overpass mirrors exhausted for bbox %s — skipping cell", bbox)
    return []


# ---------------------------------------------------------------------------
# Upsert (ch_agvs pattern)
# ---------------------------------------------------------------------------

_COLS = (
    "domain, country, source_layer, source, url, name, address, city, postcode, "
    "phone, email, lat, lng, registry_id, external_refs"
)
_VALS = "$1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb"

_UPSERT_DOMAIN = f"""
INSERT INTO discovery_candidates ({_COLS}) VALUES ({_VALS})
ON CONFLICT (domain, country) WHERE domain IS NOT NULL
DO UPDATE SET last_seen = NOW()
WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'
"""
_UPSERT_IDENTITY = f"""
INSERT INTO discovery_candidates ({_COLS}) VALUES ({_VALS})
ON CONFLICT (source, registry_id, country) WHERE domain IS NULL AND registry_id IS NOT NULL
DO UPDATE SET last_seen = NOW()
WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'
"""


async def _upsert(pool: asyncpg.Pool, c: dict) -> bool:
    domain, registry_id = c.get("domain"), c.get("registry_id")
    if not domain and not registry_id:
        return False
    params = (
        domain, c["country"], c["source_layer"], c["source"],
        c.get("url"), c.get("name"), c.get("address"), c.get("city"),
        c.get("postcode"), c.get("phone"), c.get("email"),
        c.get("lat"), c.get("lng"), registry_id,
        json.dumps(c.get("external_refs") or {}),
    )
    try:
        await pool.execute(_UPSERT_DOMAIN if domain else _UPSERT_IDENTITY, *params)
        return True
    except Exception as exc:
        log.warning("upsert failed name=%r: %s", (c.get("name") or "")[:50], exc)
        return False


# ---------------------------------------------------------------------------
# Per-country sweep
# ---------------------------------------------------------------------------

async def sweep_country(
    country: str,
    pool: asyncpg.Pool,
    client: httpx.AsyncClient,
    dry_run: bool = False,
) -> dict:
    """Sweep a single country and return stats dict."""
    alternation = _build_alternation(country)
    if not alternation:
        log.warning("no dealer terms for country %s — skip", country)
        return {"country": country, "cells": 0, "name_match": 0, "after_filter": 0, "upserted": 0}

    all_cells = list(_cells(country))
    n_cells = len(all_cells)
    area_id = _COUNTRY_AREA_IDS.get(country)
    log.info("%s: %d cells, step=%.2f°, area_id=%s", country, n_cells, _CELL_DEG.get(country, 0.4), area_id)

    seen_osm_ids: set[str] = set()   # dedup within this sweep by OSM element id
    total_name_match = 0
    total_after_filter = 0
    total_upserted = 0

    for i, bbox in enumerate(all_cells, 1):
        query = _build_query(alternation, bbox, area_id=area_id)
        elements = await _fetch_cell(client, query, bbox)

        cell_match = 0
        cell_pass = 0
        cell_upserted = 0

        for el in elements:
            osm_id = f"{el.get('type')}/{el.get('id')}"
            if osm_id in seen_osm_ids:
                continue
            seen_osm_ids.add(osm_id)

            tags = el.get("tags") or {}
            name = (tags.get("name") or "").strip()
            if not name:
                continue

            cell_match += 1
            cand = _to_candidate(el, country)
            if cand is None:
                continue
            cell_pass += 1

            if not dry_run:
                if await _upsert(pool, cand):
                    cell_upserted += 1
            else:
                cell_upserted += 1   # count as would-upsert in dry run

        total_name_match += cell_match
        total_after_filter += cell_pass
        total_upserted += cell_upserted

        if i % 10 == 0 or i == n_cells:
            log.info(
                "%s cell %d/%d | match=%d pass=%d upserted=%d",
                country, i, n_cells, total_name_match, total_after_filter, total_upserted,
            )

        if i < n_cells:
            await asyncio.sleep(_THROTTLE_S)

    signal_ratio = (total_after_filter / total_name_match) if total_name_match else 0.0
    log.info(
        "%s DONE cells=%d name_match=%d after_filter=%d upserted=%d signal=%.2f",
        country, n_cells, total_name_match, total_after_filter, total_upserted, signal_ratio,
    )
    return {
        "country":      country,
        "cells":        n_cells,
        "name_match":   total_name_match,
        "after_filter": total_after_filter,
        "upserted":     total_upserted,
        "signal_ratio": round(signal_ratio, 3),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _countries_to_run() -> list[str]:
    env = os.environ.get("OSM_NT_COUNTRIES", "").strip()
    if env:
        return [c.strip().upper() for c in env.split(",") if c.strip()]
    # Default: small countries first for signal validation, then large
    return ["BE", "CH", "NL", "ES", "FR", "DE"]


async def run() -> list[dict]:
    dry_run = os.environ.get("OSM_NT_DRY_RUN", "").strip() in ("1", "true", "yes")
    countries = _countries_to_run()
    log.info("osm_nametail start countries=%s dry_run=%s", countries, dry_run)

    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    results: list[dict] = []

    # Snapshot with_web counts before run for delta reporting
    before: dict[str, int] = {}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT country, COUNT(domain) as with_web "
            "FROM discovery_candidates WHERE country = ANY($1) "
            "GROUP BY country",
            countries,
        )
        for r in rows:
            before[r["country"]] = r["with_web"]

    try:
        async with httpx.AsyncClient(timeout=float(_QUERY_TIMEOUT + 15), follow_redirects=True) as client:
            for country in countries:
                stats = await sweep_country(country, pool, client, dry_run=dry_run)
                results.append(stats)
    finally:
        # Snapshot with_web after run
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT country, COUNT(domain) as with_web "
                "FROM discovery_candidates WHERE country = ANY($1) "
                "GROUP BY country",
                countries,
            )
            after: dict[str, int] = {r["country"]: r["with_web"] for r in rows}

        await pool.close()

    # Annotate results with delta
    for r in results:
        c = r["country"]
        b = before.get(c, 0)
        a = after.get(c, 0)
        r["with_web_before"] = b
        r["with_web_after"]  = a
        r["delta_with_web"]  = a - b

    log.info("=== SUMMARY ===")
    for r in results:
        log.info(
            "%s cells=%d name_match=%d after_filter=%d upserted=%d "
            "signal=%.2f with_web_before=%d after=%d delta=%+d",
            r["country"], r["cells"], r["name_match"], r["after_filter"],
            r["upserted"], r["signal_ratio"],
            r["with_web_before"], r["with_web_after"], r["delta_with_web"],
        )
    return results


if __name__ == "__main__":
    asyncio.run(run())
