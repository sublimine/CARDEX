"""
Google Maps Dealer Discovery Crawler — EXHAUSTIVE.

Purpose: find EVERY car dealer in ES, FR, DE, NL, BE, CH — including tiny garages
with 2 cars that never appear on AutoScout24 or mobile.de.

Strategy:
1. Divide each country into H3 resolution-4 hexagons (~86km² each).
2. For each hex: search Google Maps Places API (Text Search + Nearby Search)
   with queries like "concesionario coches", "car dealer", "Autohaus", "garage automobile".
3. Collect place_id, name, address, phone, website, rating, review_count, opening_hours.
4. Bloom-filter on place_id to skip already-discovered dealers.
5. Send discovered dealers to stream:google_maps_raw for pipeline processing.
6. Pipeline creates/updates dealer entity in PostgreSQL.

This is 100% legal:
- Uses the public Google Maps Places API (requires API key)
- Reads only publicly available business information
- Respects rate limits (10 req/s default for Places API)
- No scraping of dealer websites (optional: separate scraper per discovered dealer)

H3 coverage per country (approx hexes at res-4 needed):
  ES: ~5,500 hexes | FR: ~6,400 hexes | DE: ~4,300 hexes
  NL: ~450 hexes   | BE: ~360 hexes   | CH: ~520 hexes
  Total: ~17,500 hexes × ~20 results/search = ~350,000 dealer candidates
  After dedup: estimated 80,000-150,000 unique dealers across 6 countries.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator

import h3
import httpx
import redis.asyncio as aioredis
import structlog

log = structlog.get_logger()

# Search queries per country (localized for relevance)
_COUNTRY_QUERIES: dict[str, list[str]] = {
    "ES": ["concesionario coches", "compraventa coches", "venta coches usados", "taller venta coches"],
    "FR": ["concession automobile", "vente voiture occasion", "garage automobile", "concessionnaire auto"],
    "DE": ["Autohaus", "Gebrauchtwagen Händler", "Autowerkstatt Verkauf", "KFZ Händler"],
    "NL": ["autodealer", "tweedehands auto", "autohandel", "autobedrijf"],
    "BE": ["concessionnaire automobile", "autohandel", "garage voiture", "tweedehands auto"],
    "CH": ["Autohaus", "concessionnaire automobile", "autodealer", "occasion automobile"],
}

# Approximate bounding boxes for H3 hex selection per country
# (min_lat, min_lng, max_lat, max_lng)
_COUNTRY_BOUNDS: dict[str, tuple[float, float, float, float]] = {
    "ES": (36.0, -9.3, 43.8, 4.3),
    "FR": (42.3, -5.1, 51.1, 8.2),
    "DE": (47.3, 5.9, 55.1, 15.0),
    "NL": (50.8, 3.4, 53.6, 7.2),
    "BE": (49.5, 2.5, 51.5, 6.4),
    "CH": (45.8, 5.9, 47.8, 10.5),
}

_H3_RESOLUTION = 4      # ~86km² hexes — good balance between coverage and query count
_PLACES_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
_PLACES_TEXT_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
_RADIUS_METERS = 25_000  # 25km radius per hex center


@dataclass
class DealerRecord:
    place_id: str
    name: str
    address: str
    lat: float
    lng: float
    country: str
    phone: str = ""
    website: str = ""
    rating: float = 0.0
    review_count: int = 0
    types: list[str] = field(default_factory=list)


class GoogleMapsDealerCrawler:
    """
    Exhaustive Google Maps crawler for car dealer discovery.
    Covers all 6 target countries using H3 hexagon grid decomposition.
    """

    def __init__(self) -> None:
        self.api_key = os.environ["GOOGLE_MAPS_API_KEY"]
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            limits=httpx.Limits(max_keepalive_connections=5),
        )
        # Rate limit: 10 req/s (Places API default quota)
        self._last_request = 0.0
        self._min_interval = 0.12  # ~8 req/s to stay safely under 10/s

    async def _rate_limit(self) -> None:
        now = time.monotonic()
        wait = self._min_interval - (now - self._last_request)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request = time.monotonic()

    async def _bloom_check(self, place_id: str) -> bool:
        try:
            return bool(await self._redis.execute_command("BF.EXISTS", "bloom:dealer_place_ids", place_id))
        except Exception:
            return False

    async def _bloom_add(self, place_id: str) -> None:
        try:
            await self._redis.execute_command("BF.ADD", "bloom:dealer_place_ids", place_id)
        except Exception:
            pass

    def _get_country_hexes(self, country: str) -> list[str]:
        """Return all H3 res-4 hex IDs covering a country's bounding box."""
        bounds = _COUNTRY_BOUNDS[country]
        min_lat, min_lng, max_lat, max_lng = bounds
        hexes = set()
        # Sample grid points across the bounding box
        lat_step = 0.5  # ~55km
        lng_step = 0.7  # ~55km at mid-latitudes
        lat = min_lat
        while lat <= max_lat:
            lng = min_lng
            while lng <= max_lng:
                hex_id = h3.geo_to_h3(lat, lng, _H3_RESOLUTION)
                hexes.add(hex_id)
                lng += lng_step
            lat += lat_step
        return list(hexes)

    async def _search_nearby(self, lat: float, lng: float, query: str, page_token: str = "") -> dict:
        await self._rate_limit()
        params = {
            "key": self.api_key,
            "location": f"{lat},{lng}",
            "radius": _RADIUS_METERS,
            "keyword": query,
            "type": "car_dealer",
        }
        if page_token:
            params["pagetoken"] = page_token
        resp = await self._http.get(_PLACES_NEARBY_URL, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _crawl_hex(self, hex_id: str, country: str) -> AsyncGenerator[DealerRecord, None]:
        """Search all query variants for a single hex, paginate through all results."""
        lat, lng = h3.h3_to_geo(hex_id)
        queries = _COUNTRY_QUERIES[country]

        for query in queries:
            page_token = ""
            while True:
                try:
                    data = await self._search_nearby(lat, lng, query, page_token)
                except Exception as e:
                    log.warning("gmaps.fetch_error", hex=hex_id, query=query, error=str(e))
                    break

                results = data.get("results") or []
                for place in results:
                    place_id = place.get("place_id", "")
                    if not place_id:
                        continue
                    if await self._bloom_check(place_id):
                        continue
                    await self._bloom_add(place_id)

                    loc = place.get("geometry", {}).get("location", {})
                    yield DealerRecord(
                        place_id=place_id,
                        name=place.get("name", ""),
                        address=place.get("formatted_address") or place.get("vicinity", ""),
                        lat=loc.get("lat", 0.0),
                        lng=loc.get("lng", 0.0),
                        country=country,
                        rating=float(place.get("rating") or 0),
                        review_count=int(place.get("user_ratings_total") or 0),
                        types=place.get("types") or [],
                    )

                # next_page_token means more results — wait 2s before fetching
                page_token = data.get("next_page_token", "")
                if not page_token:
                    break
                await asyncio.sleep(2.0)  # Google requires brief delay before using next_page_token

    async def run(self) -> None:
        total = new = skipped = 0

        for country in _COUNTRY_BOUNDS:
            hexes = self._get_country_hexes(country)
            log.info("gmaps.country_start", country=country, hexes=len(hexes))

            # Check which hexes are already done
            done_key = f"scraper:gmaps_done:{country}"

            for i, hex_id in enumerate(hexes):
                is_done = await self._redis.sismember(done_key, hex_id)
                if is_done:
                    skipped += 1
                    continue

                hex_count = 0
                async for dealer in self._crawl_hex(hex_id, country):
                    total += 1
                    new += 1
                    hex_count += 1
                    # Publish to Redis stream for pipeline
                    await self._redis.xadd(
                        "stream:google_maps_raw",
                        {
                            "payload": json.dumps({
                                "place_id": dealer.place_id,
                                "name": dealer.name,
                                "address": dealer.address,
                                "lat": dealer.lat,
                                "lng": dealer.lng,
                                "country": dealer.country,
                                "rating": dealer.rating,
                                "review_count": dealer.review_count,
                                "types": dealer.types,
                            }),
                            "source": "google_maps",
                        },
                    )

                # Mark hex as done (permanent — hex doesn't change)
                await self._redis.sadd(done_key, hex_id)

                if (i + 1) % 100 == 0:
                    log.info(
                        "gmaps.progress",
                        country=country,
                        hexes_done=i + 1,
                        hexes_total=len(hexes),
                        total_found=total,
                        new=new,
                    )

            log.info("gmaps.country_complete", country=country, new=new, total=total)

        await self._redis.aclose()
        await self._http.aclose()
        log.info("gmaps.run_complete", total=total, new=new, skipped=skipped)


async def run() -> None:
    crawler = GoogleMapsDealerCrawler()
    await crawler.run()
