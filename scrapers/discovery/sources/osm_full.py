"""
OSM Full — expanded tag set for motor-trade discovery.

Extends the original OSMSource query with additional tags that OSM uses for
vehicle-adjacent businesses. Each country is processed sequentially (RAM-safe:
response is parsed and discarded before the next country is fetched). Overpass
endpoints are rotated on failure.

NEW tags vs osm.py baseline:
  shop=vehicle         — general vehicle dealers (often cars, mixed fleet)
  shop=car_service     — service centres that may also sell
  craft=coachbuilder   — body shops / bespoke builders
  shop=trailer         — trailer dealers (often also caravans/light commercial)

Excluded after out-count check:
  shop=agrarian        — agricultural supply; virtually no car dealers
  amenity=vehicle_rental — overlaps amenity=car_rental; low new signal
  shop=atv / shop=boat — niche, high noise for 6-country coverage

Upsert contract (matches ch_agvs.py pattern):
  • domain IS NOT NULL  → ON CONFLICT (domain, country)  DO UPDATE last_seen
  • domain IS NULL      → ON CONFLICT (source, registry_id, country) DO UPDATE last_seen
  registry_id = "<type>/<osm_id>"  (e.g. "node/123456789")

Usage:
    python -m scrapers.discovery.sources.osm_full
    OSM_COUNTRIES=BE,NL python -m scrapers.discovery.sources.osm_full
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.parse
from typing import Generator

import asyncpg
import httpx

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://cardex:cardex_dev_only@localhost:5432/cardex",
)

_OVERPASS_ENDPOINTS: tuple[str, ...] = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)

_HEADERS = {
    "Accept": "application/json",
    # overpass-api.de blocks the default httpx UA via mod_security
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}

_COUNTRY_AREA_IDS: dict[str, int] = {
    "BE": 3_600_000_000 + 52_411,
    "NL": 3_600_000_000 + 47_796,
    "CH": 3_600_000_000 + 51_701,
    "ES": 3_600_000_000 + 1_311_341,
    "FR": 3_600_000_000 + 2_202_162,
    "DE": 3_600_000_000 + 51_477,
}

# Default run order: small/fast countries first, DE last (largest payload)
_DEFAULT_COUNTRIES = ("BE", "NL", "CH", "ES", "FR", "DE")

_SOURCE = "osm"
_SOURCE_LAYER = 4

# ---------------------------------------------------------------------------
# Overpass query — expanded tag set
# ---------------------------------------------------------------------------

# Each nwr[] line is a separate union member; Overpass deduplicates by element id.
# We keep ALL tags from the original osm.py baseline and add the new ones.
_QUERY_TEMPLATE = """
[out:json][timeout:600];
area({area_id})->.searchArea;
(
  nwr["shop"="car"](area.searchArea);
  nwr["shop"="car_dealer"](area.searchArea);
  nwr["trade"="cars"](area.searchArea);
  nwr["shop"="second_hand"]["car"](area.searchArea);
  nwr["shop"="car_repair"](area.searchArea);
  nwr["shop"="car_parts"](area.searchArea);
  nwr["shop"="tyres"](area.searchArea);
  nwr["shop"="motorcycle"](area.searchArea);
  nwr["shop"="truck"](area.searchArea);
  nwr["shop"="caravan"](area.searchArea);
  nwr["craft"="car_repair"](area.searchArea);
  nwr["office"="car_dealer"](area.searchArea);
  nwr["amenity"="car_rental"](area.searchArea);
  nwr["shop"="vehicle"](area.searchArea);
  nwr["shop"="car_service"](area.searchArea);
  nwr["craft"="coachbuilder"](area.searchArea);
  nwr["shop"="trailer"](area.searchArea);
);
out body center qt;
""".strip()

# ---------------------------------------------------------------------------
# SQL — mirrors ch_agvs.py upsert pattern exactly
# ---------------------------------------------------------------------------

_COLS = (
    "domain, country, source_layer, source, url, name, address, city, "
    "postcode, phone, email, lat, lng, registry_id, external_refs"
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

# ---------------------------------------------------------------------------
# Pure helpers (testable without I/O)
# ---------------------------------------------------------------------------

def normalize_url(url) -> str | None:
    if not url:
        return None
    url = str(url).strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def extract_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return None
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or None


def build_address(tags: dict) -> str | None:
    parts = [
        tags.get("addr:street"),
        tags.get("addr:housenumber"),
        tags.get("addr:postcode"),
        tags.get("addr:city"),
    ]
    parts = [p for p in parts if p]
    return ", ".join(parts) if parts else None


def element_to_candidate(el: dict, country: str) -> dict | None:
    """
    Map one Overpass element to a discovery_candidates row dict.

    Returns None when the element lacks a usable name or coordinates —
    those rows cannot be deduped or geocoded and are not worth storing.
    """
    tags = el.get("tags") or {}
    name = (
        tags.get("name")
        or tags.get("brand")
        or tags.get("operator")
        or ""
    ).strip()
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

    website = normalize_url(
        tags.get("website")
        or tags.get("url")
        or tags.get("contact:website")
    )
    domain = extract_domain(website)
    osm_id = f"{el.get('type')}/{el.get('id')}"

    return {
        "domain":        domain,
        "country":       country,
        "source_layer":  _SOURCE_LAYER,
        "source":        _SOURCE,
        "url":           website,
        "name":          name,
        "address":       build_address(tags),
        "city":          tags.get("addr:city"),
        "postcode":      tags.get("addr:postcode"),
        "phone":         (
            tags.get("phone")
            or tags.get("contact:phone")
            or tags.get("contact:mobile")
        ),
        "email":         tags.get("email") or tags.get("contact:email"),
        "lat":           float(lat),
        "lng":           float(lng),
        "registry_id":   osm_id,
        "external_refs": {
            "brand":         tags.get("brand"),
            "operator":      tags.get("operator"),
            "opening_hours": tags.get("opening_hours"),
            "osm_tags":      {
                k: v for k, v in tags.items()
                if k in ("shop", "craft", "trade", "office", "amenity")
            },
        },
    }


def parse_elements(data: dict, country: str) -> Generator[dict, None, None]:
    """
    Yield candidate dicts from a raw Overpass JSON response.
    Filters out elements with no name or no coordinates.
    """
    for el in data.get("elements") or []:
        cand = element_to_candidate(el, country)
        if cand:
            yield cand


# ---------------------------------------------------------------------------
# Overpass fetch (async, with endpoint rotation)
# ---------------------------------------------------------------------------

async def fetch_country(
    client: httpx.AsyncClient,
    country: str,
    area_id: int,
) -> dict | None:
    """
    Fetch raw Overpass JSON for one country. Returns None on total failure.
    Rotates endpoints and logs each attempt.
    """
    query = _QUERY_TEMPLATE.format(area_id=area_id)

    for endpoint in _OVERPASS_ENDPOINTS:
        try:
            log.debug("osm_full: trying %s for %s", endpoint, country)
            resp = await client.post(
                endpoint,
                data={"data": query},
                headers=_HEADERS,
                timeout=660.0,
            )
            if resp.status_code != 200:
                log.warning(
                    "osm_full: %s HTTP %d for %s — trying next endpoint",
                    endpoint, resp.status_code, country,
                )
                continue
            # Parse immediately so the raw bytes can be GC'd
            return resp.json()
        except Exception as exc:
            log.warning("osm_full: %s failed for %s: %s", endpoint, country, exc)
            continue

    log.error("osm_full: all endpoints failed for %s", country)
    return None


# ---------------------------------------------------------------------------
# DB upsert
# ---------------------------------------------------------------------------

async def upsert(pool: asyncpg.Pool, c: dict) -> bool:
    domain, registry_id = c.get("domain"), c.get("registry_id")
    if not domain and not registry_id:
        return False
    params = (
        domain, c["country"], c["source_layer"], c["source"],
        c.get("url"), c.get("name"), c.get("address"), c.get("city"),
        c.get("postcode"), c.get("phone"), c.get("email"),
        c.get("lat"), c.get("lng"),
        registry_id, json.dumps(c.get("external_refs") or {}),
    )
    sql = _UPSERT_DOMAIN if domain else _UPSERT_IDENTITY
    try:
        await pool.execute(sql, *params)
        return True
    except Exception as exc:
        log.warning(
            "osm_full: upsert failed name=%r: %s",
            (c.get("name") or "")[:60], exc,
        )
        return False


# ---------------------------------------------------------------------------
# Main run — one country at a time (RAM-safe)
# ---------------------------------------------------------------------------

async def run(countries: tuple[str, ...] | None = None) -> dict[str, dict]:
    """
    Run the expanded OSM query for each country sequentially.

    Returns a dict of per-country stats:
        {country: {"elements": int, "candidates": int, "upserted": int}}
    """
    if countries is None:
        env = os.environ.get("OSM_COUNTRIES", "").strip()
        if env:
            countries = tuple(c.strip().upper() for c in env.split(",") if c.strip())
        else:
            countries = _DEFAULT_COUNTRIES

    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    stats: dict[str, dict] = {}

    try:
        for i, country in enumerate(countries):
            area_id = _COUNTRY_AREA_IDS.get(country)
            if not area_id:
                log.warning("osm_full: no area_id for %s — skipped", country)
                continue

            log.info("osm_full: [%d/%d] fetching %s …", i + 1, len(countries), country)

            async with httpx.AsyncClient(follow_redirects=True) as client:
                data = await fetch_country(client, country, area_id)
            # client closed → connection freed; data is a plain dict in RAM

            if data is None:
                stats[country] = {"elements": 0, "candidates": 0, "upserted": 0}
                continue

            n_elements = len(data.get("elements") or [])
            log.info("osm_full: %s — %d raw elements", country, n_elements)

            n_cand = 0
            n_upserted = 0
            for cand in parse_elements(data, country):
                n_cand += 1
                if await upsert(pool, cand):
                    n_upserted += 1
                if n_cand % 1000 == 0:
                    log.info(
                        "osm_full: %s progress candidates=%d upserted=%d",
                        country, n_cand, n_upserted,
                    )

            # Release the Overpass payload from memory before the next country
            del data

            stats[country] = {
                "elements":   n_elements,
                "candidates": n_cand,
                "upserted":   n_upserted,
            }
            log.info(
                "osm_full: %s DONE elements=%d candidates=%d upserted=%d",
                country, n_elements, n_cand, n_upserted,
            )

            # Polite throttle between countries
            if i < len(countries) - 1:
                await asyncio.sleep(5)

    finally:
        await pool.close()

    return stats


if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [osm_full] %(message)s",
    )

    async def _main() -> None:
        stats = await run()
        print("\n=== osm_full RESULTS ===")
        total_elem = total_cand = total_ups = 0
        for cc, s in stats.items():
            print(
                f"  {cc}: elements={s['elements']:>6}  "
                f"candidates={s['candidates']:>6}  "
                f"upserted={s['upserted']:>6}"
            )
            total_elem += s["elements"]
            total_cand += s["candidates"]
            total_ups  += s["upserted"]
        print(
            f"  TOTAL: elements={total_elem}  "
            f"candidates={total_cand}  upserted={total_ups}"
        )

    asyncio.run(_main())
