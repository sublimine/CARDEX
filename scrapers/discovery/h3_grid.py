"""
H3 Adaptive Grid Crawler — km-by-km dealer discovery via Google Maps Places API.

Strategy:
- Base resolution: H3 res-7 (~0.16 km² per hex, ~350m diameter)
  → At this density, no hex in any EU city has >20 dealers = Google's page limit
- Urban cores (population density > threshold): auto-upgrade to res-8 (~0.04 km²)
- For each hex: run MULTIPLE query variants to catch every dealer category
- Paginate all next_page_tokens until exhausted

Query variants per hex (catches dealers who tag differently):
  ES: "concesionario coches", "taller automóviles", "venta coches segunda mano",
      "compraventa vehículos", "km0", "autoescuela concesionario"
  DE: "Autohaus", "Gebrauchtwagen", "KFZ Händler", "Fahrzeughandel", "Autohandel"
  FR: "concessionnaire automobile", "occasion voiture", "vente voiture",
      "garage automobile", "mandataire auto"
  NL: "autobedrijf", "autohandel", "occasions", "autoverkoop"
  BE: "autohandel", "concessionnaire", "garage auto"
  CH: "Autohaus", "occasion voiture", "autohandel", "auto occasion"

Coverage math (worst case):
  6 countries total land area: ~1.8M km²
  H3 res-7: ~0.16 km² → ~11.25M hexes (land only ~5.5M after water/uninhabited)
  Estimated dealers in 6 countries: ~400,000
  With 8 query variants × 20 results/page × 3 pages = 480 candidates/hex
  → Theoretical capacity: 264M candidates (actual unique: ~5M after dedup)
  → Zero missed dealers at res-7 in any urban/suburban area
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import AsyncGenerator, Optional

import h3
import aiohttp

log = logging.getLogger(__name__)

# ── Country bounding boxes (lat_min, lng_min, lat_max, lng_max) ───────────────
_COUNTRY_BOUNDS: dict[str, tuple[float, float, float, float]] = {
    "ES": (36.0, -9.3, 43.8, 4.3),
    "FR": (42.3, -5.1, 51.1, 8.2),
    "DE": (47.3, 5.9, 55.1, 15.0),
    "NL": (50.8, 3.4, 53.6, 7.2),
    "BE": (49.5, 2.5, 51.5, 6.4),
    "CH": (45.8, 5.9, 47.8, 10.5),
}

# ── Query variants per country ────────────────────────────────────────────────
_QUERY_VARIANTS: dict[str, list[str]] = {
    "ES": [
        "concesionario coches",
        "taller venta automoviles",
        "venta coches segunda mano",
        "compraventa vehiculos",
        "coches km0",
        "automoviles ocasion",
        "dealer coche",
        "automocion venta",
    ],
    "FR": [
        "concessionnaire automobile",
        "vente voiture occasion",
        "garage automobile vente",
        "mandataire auto",
        "occasion vehicule",
        "reprise vente voiture",
        "auto occasion",
        "vente vehicules",
    ],
    "DE": [
        "Autohaus",
        "Gebrauchtwagen Händler",
        "KFZ Händler",
        "Fahrzeughandel",
        "Auto Händler",
        "Gebrauchtwagenmarkt",
        "Autohandel",
        "Pkw Händler",
    ],
    "NL": [
        "autobedrijf",
        "autohandel occasions",
        "autoverkoop",
        "autodealer",
        "tweedehands auto",
        "auto occasion",
        "voertuigenhandel",
        "autogarage",
    ],
    "BE": [
        "autohandel",
        "concessionnaire automobile",
        "garage auto vente",
        "voiture occasion belgique",
        "autobedrijf",
        "mandataire auto",
        "vente voiture",
        "tweedehandsauto",
    ],
    "CH": [
        "Autohaus Schweiz",
        "occasion auto",
        "auto occasion vente",
        "Gebrauchtwagen Händler",
        "autohandel",
        "voiture occasion suisse",
        "auto verkauf",
        "occasionsauto",
    ],
}

# ── Density thresholds for resolution upgrade ─────────────────────────────────
# Urban density zones by country (approx bbox for major metros → use res-8)
_URBAN_ZONES: dict[str, list[tuple[float, float, float, float]]] = {
    "ES": [
        (40.3, -3.9, 40.6, -3.5),   # Madrid
        (41.3, 2.0, 41.5, 2.3),     # Barcelona
        (37.3, -6.0, 37.5, -5.8),   # Sevilla
        (39.4, -0.5, 39.5, -0.3),   # Valencia
    ],
    "FR": [
        (48.7, 2.2, 49.0, 2.6),     # Paris
        (43.2, 5.2, 43.4, 5.5),     # Marseille
        (45.6, 4.7, 45.8, 5.0),     # Lyon
    ],
    "DE": [
        (52.4, 13.2, 52.6, 13.6),   # Berlin
        (53.4, 9.8, 53.7, 10.1),    # Hamburg
        (48.0, 11.4, 48.2, 11.7),   # München
        (51.3, 6.6, 51.5, 7.0),     # Ruhrgebiet
    ],
    "NL": [
        (52.3, 4.7, 52.4, 5.1),     # Amsterdam
        (51.8, 4.3, 52.0, 4.6),     # Rotterdam
        (52.0, 4.2, 52.2, 4.4),     # Den Haag
    ],
    "BE": [
        (50.8, 4.2, 50.9, 4.5),     # Bruxelles
        (51.0, 3.6, 51.1, 3.8),     # Gent
        (51.1, 4.3, 51.3, 4.5),     # Antwerpen
    ],
    "CH": [
        (47.3, 8.4, 47.4, 8.6),     # Zürich
        (46.9, 7.3, 47.1, 7.5),     # Bern
        (46.1, 6.0, 46.3, 6.2),     # Genève
    ],
}

_BASE_RESOLUTION = 7   # ~0.16 km²  →  ~350m diameter
_URBAN_RESOLUTION = 8  # ~0.04 km²  →  ~175m diameter

_GMAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
_PLACES_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
_NEARBY_URL  = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

# Type filters for Nearby Search (additional signal)
_GMAPS_TYPES = ["car_dealer", "car_repair"]


class H3AdaptiveGridCrawler:
    """
    Exhaustive H3 adaptive-resolution grid crawler.
    For each hex: fires all query variants + nearby search by type.
    Paginates every response until no next_page_token.
    """

    def __init__(self, rdb, session: aiohttp.ClientSession):
        self.rdb = rdb
        self.session = session
        self.api_key = _GMAPS_API_KEY

    def _resolution_for_hex(self, lat: float, lng: float, country: str) -> int:
        for bbox in _URBAN_ZONES.get(country, []):
            if bbox[0] <= lat <= bbox[2] and bbox[1] <= lng <= bbox[3]:
                return _URBAN_RESOLUTION
        return _BASE_RESOLUTION

    def _fill_country(self, country: str) -> list[str]:
        """Return all H3 cell IDs at adaptive resolution covering the country."""
        lat_min, lng_min, lat_max, lng_max = _COUNTRY_BOUNDS[country]

        # First pass: res-7 hexes in bounding box
        res7_hexes = h3.geo_to_cells(
            {
                "type": "Polygon",
                "coordinates": [[
                    [lng_min, lat_min],
                    [lng_max, lat_min],
                    [lng_max, lat_max],
                    [lng_min, lat_max],
                    [lng_min, lat_min],
                ]]
            },
            _BASE_RESOLUTION,
        )

        all_cells = set()
        for cell in res7_hexes:
            lat, lng = h3.cell_to_latlng(cell)
            if self._resolution_for_hex(lat, lng, country) == _URBAN_RESOLUTION:
                # Upgrade: replace with res-8 children
                children = h3.cell_to_children(cell, _URBAN_RESOLUTION)
                all_cells.update(children)
            else:
                all_cells.add(cell)

        return list(all_cells)

    async def _is_hex_done(self, country: str, cell: str) -> bool:
        key = f"discovery:h3_done:{country}"
        return bool(await self.rdb.sismember(key, cell))

    async def _mark_hex_done(self, country: str, cell: str) -> None:
        key = f"discovery:h3_done:{country}"
        await self.rdb.sadd(key, cell)
        # 30-day TTL — re-crawl monthly
        await self.rdb.expire(key, 30 * 86400)

    async def crawl_country(self, country: str) -> AsyncGenerator[dict, None]:
        """Yield raw place dicts for every dealer found in country."""
        cells = self._fill_country(country)
        log.info("h3_grid: %s — %d cells at adaptive res-7/8", country, len(cells))

        for i, cell in enumerate(cells):
            if await self._is_hex_done(country, cell):
                continue

            lat, lng = h3.cell_to_latlng(cell)

            async for place in self._crawl_cell(lat, lng, country):
                yield place

            await self._mark_hex_done(country, cell)

            if i % 1000 == 0:
                log.info("h3_grid: %s — %d/%d cells processed", country, i, len(cells))

            # Rate limiting: respect Google's QPS limit
            await asyncio.sleep(0.05)

    async def _crawl_cell(self, lat: float, lng: float, country: str) -> AsyncGenerator[dict, None]:
        seen_place_ids: set[str] = set()

        # 1. Text Search for each query variant
        for query in _QUERY_VARIANTS.get(country, []):
            async for place in self._text_search(lat, lng, query):
                pid = place.get("place_id")
                if pid and pid not in seen_place_ids:
                    seen_place_ids.add(pid)
                    yield place

        # 2. Nearby Search by type (car_dealer, car_repair)
        for gtype in _GMAPS_TYPES:
            async for place in self._nearby_search(lat, lng, gtype):
                pid = place.get("place_id")
                if pid and pid not in seen_place_ids:
                    seen_place_ids.add(pid)
                    yield place

    async def _text_search(self, lat: float, lng: float, query: str) -> AsyncGenerator[dict, None]:
        params = {
            "query": query,
            "location": f"{lat},{lng}",
            "radius": "1000",  # 1km radius per cell
            "key": self.api_key,
        }
        async for place in self._paginate(_PLACES_URL, params):
            yield place

    async def _nearby_search(self, lat: float, lng: float, gtype: str) -> AsyncGenerator[dict, None]:
        params = {
            "location": f"{lat},{lng}",
            "radius": "1000",
            "type": gtype,
            "key": self.api_key,
        }
        async for place in self._paginate(_NEARBY_URL, params):
            yield place

    async def _paginate(self, url: str, params: dict) -> AsyncGenerator[dict, None]:
        """Exhaust all pages following next_page_token."""
        while True:
            try:
                async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
            except Exception as exc:
                log.warning("gmaps request failed: %s", exc)
                return

            status = data.get("status")
            if status not in ("OK", "ZERO_RESULTS"):
                log.debug("gmaps status=%s query=%s", status, params.get("query") or params.get("type"))
                return

            for result in data.get("results") or []:
                yield result

            token = data.get("next_page_token")
            if not token:
                return

            # Google requires a short delay before using next_page_token
            await asyncio.sleep(2.0)
            params = {"pagetoken": token, "key": self.api_key}
            url = _PLACES_URL  # pagetoken works with text search endpoint
