"""
Search Indexer — watermark-based PostgreSQL -> MeiliSearch synchronizer.

Architecture:
  1. On startup: configure MeiliSearch index (searchable, filterable, sortable attrs)
  2. Load watermark (last successful sync timestamp) from Redis
  3. Every poll_interval seconds:
     a. Query PG for vehicles WHERE last_updated_at > watermark
     b. Transform rows with ontological normalization (fuel/trans/color)
     c. Push in batches of batch_size via MeiliSearch REST API
     d. Advance watermark to MAX(last_updated_at) of synced rows
     e. Persist watermark to Redis

Watermark key: search_indexer:watermark (Redis string, ISO timestamp)

Normalization: all categorical fields pass through scrapers.common.normalizer
(single source of truth). No raw multilingual strings reach MeiliSearch.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone

import asyncpg
import httpx
from redis.asyncio import from_url as redis_from_url
from scrapers.common.normalizer import normalize_fuel, normalize_transmission, normalize_color

log = logging.getLogger("indexer")

_WATERMARK_KEY = "search_indexer:watermark"
_MEILI_INDEX = "vehicles"

# -- MeiliSearch Index Configuration ------------------------------------------

_INDEX_SETTINGS = {
    "searchableAttributes": [
        "brand", "model", "version", "dealer_name",
    ],
    "filterableAttributes": [
        "price", "year", "mileage", "fuel", "transmission",
        "is_sold", "country", "brand", "model",
    ],
    "sortableAttributes": [
        "price", "year", "updated_at",
    ],
    "displayedAttributes": ["*"],
    "pagination": {"maxTotalHits": 100000},
}

# -- Numeric Sanitizer --------------------------------------------------------


def _clean_int(val) -> int | None:
    """Force a value to a clean integer. Handles Decimal, float, and noisy strings."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    try:
        from decimal import Decimal
        if isinstance(val, Decimal):
            return int(val)
    except (ImportError, TypeError):
        pass
    s = str(val).strip()
    s = re.sub(r"[^0-9.,]", "", s)
    if re.match(r"^\d{1,3}(\.\d{3})+$", s):
        s = s.replace(".", "")
    elif "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        parts = s.split(",")
        if len(parts[-1]) == 3:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


# -- Row -> Document Transform ------------------------------------------------

def _row_to_doc(row: asyncpg.Record) -> dict:
    """
    Transform a PostgreSQL vehicle row into a flat, ontologically normalized
    MeiliSearch document. Categorical fields pass through the shared normalizer.
    Numeric fields are strict integers.
    """
    price = _clean_int(row["price_raw"])
    mileage = _clean_int(row["mileage_km"])
    year = _clean_int(row["year"])

    is_sold = row["listing_status"] == "SOLD"

    updated_at = row["last_updated_at"]
    updated_ts = int(updated_at.timestamp()) if updated_at else 0

    doc = {
        "id": row["vehicle_ulid"],
        "vehicle_ulid": row["vehicle_ulid"],
        "url": row["source_url"],
        "brand": (row["make"] or "").strip(),
        "model": (row["model"] or "").strip(),
        "version": (row["variant"] or "").strip(),
        "price": price,
        "year": year,
        "mileage": mileage,
        "fuel": normalize_fuel(row["fuel_type"]) or "",
        "transmission": normalize_transmission(row["transmission"]) or "",
        "color": normalize_color(row["color"]) or "",
        "country": (row["source_country"] or "").strip(),
        "dealer_name": (row["seller_name"] or "").strip(),
        "is_sold": is_sold,
        "listing_status": row["listing_status"] or "ACTIVE",
        "image_url": (row["thumbnail_url"] or row["thumb_url"] or "").strip(),
        "source_platform": (row["source_platform"] or "").strip(),
        "updated_at": updated_ts,
    }

    photos = row["photo_urls"]
    if photos:
        doc["photo_urls"] = list(photos[:5])

    return doc


# -- SQL Query ----------------------------------------------------------------

_FETCH_SQL = """
    SELECT
        vehicle_ulid, source_url, source_platform, source_country,
        make, model, variant, year, mileage_km, color,
        fuel_type, transmission, price_raw,
        seller_name, listing_status,
        thumbnail_url, thumb_url, photo_urls,
        last_updated_at
    FROM vehicles
    WHERE last_updated_at > $1
    ORDER BY last_updated_at ASC
    LIMIT $2
"""


class SearchIndexer:
    def __init__(
        self,
        db_url: str,
        redis_url: str,
        meili_url: str,
        meili_key: str,
        poll_interval: int = 60,
        batch_size: int = 1000,
    ):
        self._db_url = db_url
        self._redis_url = redis_url
        self._meili_url = meili_url.rstrip("/")
        self._meili_key = meili_key
        self._poll_interval = poll_interval
        self._batch_size = batch_size

    async def run(self) -> None:
        self._pg = await asyncpg.create_pool(self._db_url, min_size=2, max_size=4)
        self._rdb = redis_from_url(self._redis_url, decode_responses=True)
        self._http = httpx.AsyncClient(
            base_url=self._meili_url,
            headers={
                "Authorization": f"Bearer {self._meili_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

        log.info("indexer: started poll=%ds batch=%d meili=%s",
                 self._poll_interval, self._batch_size, self._meili_url)

        await self._ensure_index()
        watermark = await self._load_watermark()
        log.info("indexer: watermark=%s", watermark.isoformat())

        try:
            while True:
                synced, new_watermark = await self._sync_cycle(watermark)
                if synced > 0:
                    watermark = new_watermark
                    await self._save_watermark(watermark)
                    print(
                        f"[INDEXER] synced {synced} docs, watermark={watermark.isoformat()}",
                        flush=True,
                    )
                await asyncio.sleep(self._poll_interval)
        finally:
            await self._pg.close()
            await self._rdb.aclose()
            await self._http.aclose()

    async def _ensure_index(self) -> None:
        resp = await self._http.post("/indexes", json={
            "uid": _MEILI_INDEX,
            "primaryKey": "id",
        })
        if resp.status_code == 202:
            await self._wait_task(resp.json().get("taskUid"))
        resp = await self._http.patch(
            f"/indexes/{_MEILI_INDEX}/settings", json=_INDEX_SETTINGS,
        )
        if resp.status_code == 202:
            await self._wait_task(resp.json().get("taskUid"))
            log.info("indexer: index settings applied")

    async def _wait_task(self, task_uid: int | None, timeout: float = 60.0) -> None:
        if task_uid is None:
            return
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            resp = await self._http.get(f"/tasks/{task_uid}")
            if resp.status_code == 200:
                if resp.json().get("status") in ("succeeded", "failed"):
                    return
            await asyncio.sleep(0.5)

    async def _load_watermark(self) -> datetime:
        raw = await self._rdb.get(_WATERMARK_KEY)
        if raw:
            try:
                return datetime.fromisoformat(raw)
            except (ValueError, TypeError):
                pass
        return datetime(2000, 1, 1, tzinfo=timezone.utc)

    async def _save_watermark(self, ts: datetime) -> None:
        await self._rdb.set(_WATERMARK_KEY, ts.isoformat())

    async def _sync_cycle(self, watermark: datetime) -> tuple[int, datetime]:
        total_synced = 0
        current_watermark = watermark

        while True:
            rows = await self._pg.fetch(_FETCH_SQL, current_watermark, self._batch_size)
            if not rows:
                break

            docs = [_row_to_doc(row) for row in rows]

            resp = await self._http.post(
                f"/indexes/{_MEILI_INDEX}/documents",
                content=json.dumps(docs, default=str).encode(),
            )
            if resp.status_code == 202:
                log.info("indexer: pushed %d docs, task=%s",
                         len(docs), resp.json().get("taskUid"))
            else:
                log.error("indexer: push failed %d: %s",
                          resp.status_code, resp.text[:300])
                break

            total_synced += len(docs)
            last_updated = rows[-1]["last_updated_at"]
            if last_updated and last_updated > current_watermark:
                current_watermark = last_updated

            if len(rows) < self._batch_size:
                break

        return total_synced, current_watermark
