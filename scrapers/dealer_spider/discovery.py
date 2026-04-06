"""
Dealer Discovery Orchestrator — finds every car dealer in 6 European countries
via Google Places API and feeds them to the dealer spider.

Flow:
  1. Generate H3 cells (resolution 4, ~1770 km²) covering DE, ES, FR, NL, BE, CH
  2. For each cell center, query Google Places Nearby Search for car dealers
  3. Deduplicate against bloom:dealer_place_ids
  4. Upsert into PostgreSQL dealers table
  5. Publish dealers WITH websites to stream:dealer_discovered
  6. Track progress in Redis so restarts resume where they left off

Rate limiting:
  - Configurable QPS (default 10/s) with exponential backoff on 429
  - Progress checkpointed per-cell per-country
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from typing import Any

import asyncpg
import h3
import httpx
import structlog
from redis.asyncio import from_url as redis_from_url

log = structlog.get_logger()

# ── Configuration ────────────────────────────────────────────────────────────

_GOOGLE_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://cardex:cardex@localhost:5432/cardex"
)
_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
_COUNTRIES = [
    c.strip()
    for c in os.environ.get("DISCOVERY_COUNTRIES", "DE,ES,FR,NL,BE,CH").split(",")
    if c.strip()
]
_QPS = float(os.environ.get("DISCOVERY_QPS", "10"))

_STREAM_OUT = "stream:dealer_discovered"
_BLOOM_KEY = "bloom:dealer_place_ids"

_PLACES_NEARBY_URL = (
    "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
)

# H3 resolution 4 → ~1770 km² cells. Radius to cover a cell comfortably.
_H3_RESOLUTION = 4
_SEARCH_RADIUS_M = 25_000  # 25 km radius covers res-4 cell well

# Country-specific search queries to maximize recall across languages.
_SEARCH_QUERIES: dict[str, list[str]] = {
    "DE": ["Autohändler", "Autohaus", "car dealer"],
    "ES": ["concesionario de coches", "car dealer"],
    "FR": ["concessionnaire automobile", "garagiste", "car dealer"],
    "NL": ["autodealer", "autobedrijf", "car dealer"],
    "BE": ["autodealer", "concessionnaire automobile", "car dealer"],
    "CH": ["Autohändler", "concessionnaire automobile", "car dealer"],
}

# Bounding boxes: (lat_min, lat_max, lng_min, lng_max)
_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "DE": (47.27, 55.06, 5.87, 15.04),
    "ES": (36.00, 43.79, -9.30, 3.33),
    "FR": (42.33, 51.09, -4.79, 8.23),
    "NL": (50.75, 53.47, 3.36, 7.21),
    "BE": (49.50, 51.50, 2.55, 6.40),
    "CH": (45.82, 47.81, 5.96, 10.49),
}


# ── H3 Grid Generation ──────────────────────────────────────────────────────


def _h3_cells_for_country(country: str) -> list[str]:
    """Generate all H3 resolution-4 cells covering a country's bounding box."""
    bbox = _BBOXES.get(country)
    if not bbox:
        log.warning("discovery.no_bbox", country=country)
        return []

    lat_min, lat_max, lng_min, lng_max = bbox

    # Build a GeoJSON polygon for the bounding box
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [lng_min, lat_min],
                [lng_max, lat_min],
                [lng_max, lat_max],
                [lng_min, lat_max],
                [lng_min, lat_min],
            ]
        ],
    }

    cells = h3.geo_to_cells(polygon, res=_H3_RESOLUTION)
    return list(cells)


# ── Rate Limiter ─────────────────────────────────────────────────────────────


class _TokenBucket:
    """Simple async token-bucket rate limiter."""

    def __init__(self, qps: float) -> None:
        self._interval = 1.0 / max(qps, 0.1)
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._last + self._interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


# ── Google Places Client ─────────────────────────────────────────────────────


class _PlacesClient:
    """Async Google Places API client with rate limiting and backoff."""

    def __init__(self, api_key: str, qps: float) -> None:
        self._api_key = api_key
        self._bucket = _TokenBucket(qps)
        self._client: httpx.AsyncClient | None = None
        self._backoff_until = 0.0

    async def __aenter__(self) -> "_PlacesClient":
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            http2=False,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()

    async def nearby_search(
        self,
        lat: float,
        lng: float,
        keyword: str,
        radius: int = _SEARCH_RADIUS_M,
        page_token: str | None = None,
    ) -> dict:
        """Execute a single Nearby Search request, respecting rate limits."""
        assert self._client is not None

        # Honour backoff
        now = time.monotonic()
        if self._backoff_until > now:
            await asyncio.sleep(self._backoff_until - now)

        await self._bucket.acquire()

        params: dict[str, Any] = {
            "key": self._api_key,
            "location": f"{lat},{lng}",
            "radius": radius,
            "keyword": keyword,
            "type": "car_dealer",
        }
        if page_token:
            # When using pagetoken, location/radius/keyword are ignored by the API
            # but we still send them for clarity. The token itself defines the query.
            params["pagetoken"] = page_token

        for attempt in range(5):
            resp = await self._client.get(_PLACES_NEARBY_URL, params=params)

            if resp.status_code == 429:
                backoff = min(2 ** (attempt + 1), 120)
                log.warning(
                    "discovery.places_429",
                    backoff=backoff,
                    attempt=attempt,
                )
                self._backoff_until = time.monotonic() + backoff
                await asyncio.sleep(backoff)
                continue

            if resp.status_code >= 500:
                backoff = min(2 ** attempt, 60)
                log.warning(
                    "discovery.places_5xx",
                    status=resp.status_code,
                    backoff=backoff,
                )
                await asyncio.sleep(backoff)
                continue

            resp.raise_for_status()
            data = resp.json()

            status = data.get("status", "")
            if status == "OVER_QUERY_LIMIT":
                backoff = min(2 ** (attempt + 1), 120)
                log.warning("discovery.over_query_limit", backoff=backoff)
                self._backoff_until = time.monotonic() + backoff
                await asyncio.sleep(backoff)
                continue

            if status in ("REQUEST_DENIED", "INVALID_REQUEST"):
                log.error(
                    "discovery.places_error",
                    status=status,
                    error=data.get("error_message", ""),
                )
                return {"results": [], "status": status}

            return data

        log.error("discovery.places_exhausted_retries", lat=lat, lng=lng)
        return {"results": [], "status": "RETRY_EXHAUSTED"}

    async def nearby_search_all_pages(
        self,
        lat: float,
        lng: float,
        keyword: str,
        radius: int = _SEARCH_RADIUS_M,
    ) -> list[dict]:
        """Fetch all pages of a Nearby Search (up to 60 results / 3 pages)."""
        all_results: list[dict] = []
        page_token: str | None = None

        for page in range(3):  # Google returns max 3 pages
            data = await self.nearby_search(
                lat, lng, keyword, radius, page_token=page_token
            )
            results = data.get("results", [])
            all_results.extend(results)

            page_token = data.get("next_page_token")
            if not page_token:
                break

            # Google requires a short delay before next_page_token becomes valid
            await asyncio.sleep(2.0)

        return all_results


# ── Dealer Record Helpers ────────────────────────────────────────────────────


def _extract_dealer(place: dict, country: str) -> dict[str, Any]:
    """Extract a normalized dealer record from a Google Places result."""
    location = place.get("geometry", {}).get("location", {})
    lat = location.get("lat", 0.0)
    lng = location.get("lng", 0.0)

    # Compute H3 indices
    h3_res7 = h3.latlng_to_cell(lat, lng, 7) if lat and lng else None
    h3_res4 = h3.latlng_to_cell(lat, lng, 4) if lat and lng else None

    # Parse address components from vicinity / formatted_address
    address = place.get("vicinity") or place.get("formatted_address") or ""

    return {
        "place_id": place.get("place_id", ""),
        "name": place.get("name", ""),
        "country": country,
        "lat": lat,
        "lng": lng,
        "h3_res7": h3_res7,
        "h3_res4": h3_res4,
        "address": address,
        "website": None,  # Nearby Search doesn't return website; enriched later or via Place Details
        "phone": None,
        "google_rating": place.get("rating"),
        "google_review_count": place.get("user_ratings_total"),
        "types": place.get("types", []),
    }


# ── Database Operations ──────────────────────────────────────────────────────


async def _upsert_dealer(pg: asyncpg.Pool, dealer: dict[str, Any]) -> None:
    """Upsert a dealer record into PostgreSQL."""
    await pg.execute(
        """
        INSERT INTO dealers (
            place_id, name, country, lat, lng, h3_res7, h3_res4,
            address, website, phone,
            google_rating, google_review_count,
            source, spider_status,
            created_at, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7,
            $8, $9, $10,
            $11, $12,
            'GOOGLE_MAPS', 'PENDING',
            NOW(), NOW()
        )
        ON CONFLICT (COALESCE(place_id, ''), COALESCE(registry_id, ''), name, country)
        DO UPDATE SET
            lat                = COALESCE(EXCLUDED.lat, dealers.lat),
            lng                = COALESCE(EXCLUDED.lng, dealers.lng),
            h3_res7            = COALESCE(EXCLUDED.h3_res7, dealers.h3_res7),
            h3_res4            = COALESCE(EXCLUDED.h3_res4, dealers.h3_res4),
            address            = COALESCE(EXCLUDED.address, dealers.address),
            website            = COALESCE(EXCLUDED.website, dealers.website),
            phone              = COALESCE(EXCLUDED.phone, dealers.phone),
            google_rating      = COALESCE(EXCLUDED.google_rating, dealers.google_rating),
            google_review_count = COALESCE(EXCLUDED.google_review_count, dealers.google_review_count),
            discovery_sources  = ARRAY(
                SELECT DISTINCT unnest(dealers.discovery_sources || ARRAY['GOOGLE_MAPS'])
            ),
            updated_at         = NOW()
        """,
        dealer["place_id"],
        dealer["name"],
        dealer["country"],
        dealer["lat"],
        dealer["lng"],
        dealer["h3_res7"],
        dealer["h3_res4"],
        dealer["address"],
        dealer["website"],
        dealer["phone"],
        dealer["google_rating"],
        dealer["google_review_count"],
    )


async def _enrich_website(
    places_client: _PlacesClient, place_id: str
) -> str | None:
    """Fetch the website URL via Google Place Details (fields=website)."""
    assert places_client._client is not None
    await places_client._bucket.acquire()

    resp = await places_client._client.get(
        "https://maps.googleapis.com/maps/api/place/details/json",
        params={
            "key": _GOOGLE_API_KEY,
            "place_id": place_id,
            "fields": "website,formatted_phone_number",
        },
    )
    if resp.status_code != 200:
        return None

    data = resp.json()
    result = data.get("result", {})
    return result.get("website")


# ── Stream Publishing ────────────────────────────────────────────────────────


async def _publish_dealer(rdb: Any, dealer: dict[str, Any]) -> None:
    """Publish a dealer to stream:dealer_discovered for spider consumption."""
    await rdb.xadd(
        _STREAM_OUT,
        {
            "dealer_id": dealer["place_id"],
            "name": dealer["name"],
            "country": dealer["country"],
            "website": dealer["website"],
            "source": "GOOGLE_MAPS",
        },
    )


# ── Cell Processing ──────────────────────────────────────────────────────────


async def _process_cell(
    cell: str,
    country: str,
    places: _PlacesClient,
    pg: asyncpg.Pool,
    rdb: Any,
    stats: dict[str, int],
) -> None:
    """Search one H3 cell for dealers across all relevant queries."""
    lat, lng = h3.cell_to_latlng(cell)
    queries = _SEARCH_QUERIES.get(country, ["car dealer"])

    seen_place_ids: set[str] = set()

    for query in queries:
        try:
            results = await places.nearby_search_all_pages(lat, lng, query)
        except Exception as exc:
            log.warning(
                "discovery.cell_query_error",
                cell=cell,
                country=country,
                query=query,
                error=str(exc),
            )
            stats["errors"] += 1
            continue

        for place in results:
            place_id = place.get("place_id", "")
            if not place_id or place_id in seen_place_ids:
                continue
            seen_place_ids.add(place_id)

            # Bloom dedup: skip if already known globally
            is_known = await rdb.sismember(_BLOOM_KEY, place_id)
            if is_known:
                stats["skipped_bloom"] += 1
                continue

            dealer = _extract_dealer(place, country)

            # Enrich with website via Place Details
            try:
                website = await _enrich_website(places, place_id)
                if website:
                    dealer["website"] = website
            except Exception as exc:
                log.debug(
                    "discovery.enrich_failed",
                    place_id=place_id,
                    error=str(exc),
                )

            # Upsert to DB
            try:
                await _upsert_dealer(pg, dealer)
                stats["upserted"] += 1
            except Exception as exc:
                log.warning(
                    "discovery.upsert_error",
                    place_id=place_id,
                    name=dealer["name"],
                    error=str(exc),
                )
                stats["errors"] += 1
                continue

            # Add to bloom
            await rdb.sadd(_BLOOM_KEY, place_id)

            # Publish to stream if website exists
            if dealer["website"]:
                try:
                    await _publish_dealer(rdb, dealer)
                    stats["published"] += 1
                except Exception as exc:
                    log.warning(
                        "discovery.publish_error",
                        place_id=place_id,
                        error=str(exc),
                    )

    log.debug(
        "discovery.cell_done",
        cell=cell,
        country=country,
        found=len(seen_place_ids),
    )


# ── Country Processing ───────────────────────────────────────────────────────


async def _process_country(
    country: str,
    places: _PlacesClient,
    pg: asyncpg.Pool,
    rdb: Any,
    stop_event: asyncio.Event,
) -> dict[str, int]:
    """Process all H3 cells for a country, resuming from checkpoint."""
    progress_key = f"discovery:progress:{country}"
    cells = _h3_cells_for_country(country)
    total = len(cells)

    if total == 0:
        log.warning("discovery.no_cells", country=country)
        return {"total_cells": 0}

    # Load already-completed cells
    done_cells: set[str] = set()
    raw = await rdb.hgetall(progress_key)
    if raw:
        done_cells = {
            k if isinstance(k, str) else k.decode()
            for k in raw.keys()
        }

    remaining = [c for c in cells if c not in done_cells]

    stats: dict[str, int] = {
        "total_cells": total,
        "already_done": len(done_cells),
        "upserted": 0,
        "published": 0,
        "skipped_bloom": 0,
        "errors": 0,
    }

    log.info(
        "discovery.country_start",
        country=country,
        total_cells=total,
        remaining_cells=len(remaining),
        already_done=len(done_cells),
    )

    for i, cell in enumerate(remaining):
        if stop_event.is_set():
            log.info("discovery.country_interrupted", country=country, processed=i)
            break

        try:
            await _process_cell(cell, country, places, pg, rdb, stats)
        except Exception as exc:
            log.error(
                "discovery.cell_error",
                cell=cell,
                country=country,
                error=str(exc),
            )
            stats["errors"] += 1

        # Checkpoint
        await rdb.hset(progress_key, cell, "done")

        if (i + 1) % 50 == 0 or i == len(remaining) - 1:
            log.info(
                "discovery.country_progress",
                country=country,
                cells_done=len(done_cells) + i + 1,
                cells_total=total,
                pct=round((len(done_cells) + i + 1) / total * 100, 1),
                **stats,
            )

    log.info("discovery.country_done", country=country, **stats)
    return stats


# ── Main Entry Point ─────────────────────────────────────────────────────────


async def run() -> None:
    """Entry point — discover dealers across all configured countries."""
    if not _GOOGLE_API_KEY:
        log.error("discovery.missing_api_key", hint="Set GOOGLE_MAPS_API_KEY")
        raise SystemExit(1)

    log.info(
        "discovery.starting",
        countries=_COUNTRIES,
        qps=_QPS,
        h3_resolution=_H3_RESOLUTION,
        search_radius_m=_SEARCH_RADIUS_M,
    )

    rdb = redis_from_url(_REDIS_URL, decode_responses=True)
    pg = await asyncpg.create_pool(_DATABASE_URL, min_size=2, max_size=8)

    stop_event = asyncio.Event()

    def _handle_signal(*_: Any) -> None:
        log.info("discovery.shutdown_signal")
        stop_event.set()

    loop = asyncio.get_event_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, _handle_signal)
        loop.add_signal_handler(signal.SIGTERM, _handle_signal)
    except NotImplementedError:
        # Windows doesn't support add_signal_handler; use signal.signal fallback
        signal.signal(signal.SIGINT, lambda *_: stop_event.set())
        signal.signal(signal.SIGTERM, lambda *_: stop_event.set())

    grand_stats: dict[str, dict[str, int]] = {}

    async with _PlacesClient(_GOOGLE_API_KEY, _QPS) as places:
        for country in _COUNTRIES:
            if stop_event.is_set():
                log.info("discovery.stopped_before_country", country=country)
                break

            try:
                country_stats = await _process_country(
                    country, places, pg, rdb, stop_event,
                )
                grand_stats[country] = country_stats
            except Exception as exc:
                log.error(
                    "discovery.country_fatal",
                    country=country,
                    error=str(exc),
                )

    await pg.close()
    await rdb.aclose()

    log.info("discovery.complete", stats=grand_stats)
