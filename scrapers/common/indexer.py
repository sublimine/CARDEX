"""
CARDEX portal indexer â€” shared delta logic.

Mirrors sitemap_indexer.py invariants exactly:
  - INSERT new rows â†’ vehicle_index + vehicle_events (SEEN) + stream:enrich_pending
  - DELETE stale rows â†’ vehicle_index + vehicle_events (GONE)
  - ZERO UPDATE of non-mutated rows
  - ZERO Redis inventory state (only stream transport)
  - In-process set diff â€” no external locking, no SDIFFSTORE
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from typing import Sequence

import asyncpg
import redis.asyncio as aioredis

_DB_URL = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
_ENRICH_STREAM = "stream:enrich_pending"
_PG_BATCH = 500

log = logging.getLogger(__name__)


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:32]


async def make_pg(dsn: str | None = None) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn or _DB_URL, min_size=2, max_size=10)


async def make_redis(url: str | None = None) -> aioredis.Redis:
    return aioredis.from_url(url or _REDIS_URL, decode_responses=False)


async def ensure_schema(pg: asyncpg.Pool) -> None:
    async with pg.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS vehicle_index (
                url_hash       TEXT PRIMARY KEY,
                url_original   TEXT NOT NULL,
                source_domain  TEXT NOT NULL,
                country        CHAR(2) NOT NULL,
                sitemap_source TEXT NOT NULL DEFAULT '',
                titulo_modelo  TEXT,
                precio         NUMERIC(12,2),
                moneda         CHAR(3) DEFAULT 'EUR',
                kilometraje    INT,
                anio           SMALLINT,
                thumbnail_url  TEXT,
                last_seen      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_vi_dc ON vehicle_index (source_domain, country)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_vi_ls ON vehicle_index (last_seen)"
        )
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS vehicle_events (
                event_id       BIGSERIAL PRIMARY KEY,
                url_hash       TEXT NOT NULL,
                url_original   TEXT NOT NULL DEFAULT '',
                source_domain  TEXT NOT NULL DEFAULT '',
                country        CHAR(2) NOT NULL DEFAULT '',
                sitemap_source TEXT NOT NULL DEFAULT '',
                event_type     TEXT NOT NULL CHECK (event_type IN ('SEEN','ENRICHED','GONE')),
                titulo_modelo  TEXT,
                precio         NUMERIC(12,2),
                moneda         CHAR(3) DEFAULT 'EUR',
                kilometraje    INT,
                anio           SMALLINT,
                thumbnail_url  TEXT,
                ts             TIMESTAMPTZ NOT NULL DEFAULT NOW()
            ) WITH (fillfactor=100, autovacuum_enabled=false)
        """)


async def delta(
    pg: asyncpg.Pool,
    rdb: aioredis.Redis,
    source_key: str,
    country: str,
    domain: str,
    urls: Sequence[str],
) -> dict[str, int]:
    """
    In-process set diff against PG source of truth.

    Phase 1: build cycle set locally (hash computation, no external service).
    Phase 2: load existing hashes from PG via index-only scan.
    Phase 3: set diff in Python.
    Phase 4a: INSERT new â†’ vehicle_index + vehicle_events(SEEN) + enrich stream.
    Phase 4b: DELETE stale â†’ vehicle_index + vehicle_events(GONE).
    Phase 4c: existing non-mutated rows â€” ZERO TOUCH.
    """
    stats = {"new": 0, "gone": 0}

    hash_to_url: dict[str, str] = {}
    for u in urls:
        # Deep-link guard: reject root domain URLs (no meaningful path)
        from urllib.parse import urlparse
        parsed = urlparse(u)
        if not parsed.path or parsed.path in ("/", ""):
            continue
        hash_to_url[url_hash(u)] = u
    cycle_set = set(hash_to_url)

    async with pg.acquire() as conn:
        rows = await conn.fetch(
            "SELECT url_hash FROM vehicle_index WHERE source_domain=$1 AND country=$2",
            domain, country,
        )
    pg_set = {r["url_hash"] for r in rows}

    new_hashes = cycle_set - pg_set
    stale_hashes = pg_set - cycle_set
    stats["new"] = len(new_hashes)
    stats["gone"] = len(stale_hashes)

    # 4a â€” INSERT new
    if new_hashes:
        new_list = list(new_hashes)
        for i in range(0, len(new_list), _PG_BATCH):
            batch = new_list[i : i + _PG_BATCH]
            records = [(h, hash_to_url[h], domain, country) for h in batch]
            async with pg.acquire() as conn:
                await conn.executemany(
                    "INSERT INTO vehicle_index (url_hash,url_original,source_domain,country,last_seen)"
                    " VALUES ($1,$2,$3,$4,NOW()) ON CONFLICT (url_hash) DO NOTHING",
                    records,
                )
                await conn.executemany(
                    "INSERT INTO vehicle_events (url_hash,url_original,source_domain,country,event_type)"
                    " VALUES ($1,$2,$3,$4,'SEEN')",
                    records,
                )
        pipe = rdb.pipeline(transaction=False)
        for h in new_list:
            pipe.xadd(
                _ENRICH_STREAM,
                {"h": h, "u": hash_to_url[h], "s": source_key, "c": country},
                maxlen=5_000_000,
            )
        await pipe.execute()

    # 4b â€” DELETE stale
    if stale_hashes:
        stale_list = list(stale_hashes)
        for i in range(0, len(stale_list), _PG_BATCH):
            batch = stale_list[i : i + _PG_BATCH]
            async with pg.acquire() as conn:
                await conn.execute(
                    "DELETE FROM vehicle_index WHERE url_hash = ANY($1::text[])", batch
                )
                await conn.executemany(
                    "INSERT INTO vehicle_events (url_hash,source_domain,country,event_type)"
                    " VALUES ($1,$2,$3,'GONE')",
                    [(h, domain, country) for h in batch],
                )

    return stats


async def run_portal(
    *,
    source: str,
    country: str,
    domain: str,
    fetch_all_urls,  # async callable() -> list[str]
) -> None:
    """
    Generic portal run loop.

    fetch_all_urls: async callable that returns the full list of listing deep-link
    URLs discovered across all pages/segments for this (source, country) pair.
    The delta is computed once against PG after all URLs are collected.
    """
    log.info("START source=%s country=%s", source, country)
    t0 = time.monotonic()

    pg = await make_pg()
    rdb = await make_redis()
    try:
        await ensure_schema(pg)
        urls = await fetch_all_urls()
        log.info("COLLECTED source=%s country=%s urls=%d", source, country, len(urls))
        stats = await delta(pg, rdb, source, country, domain, urls)
        elapsed = time.monotonic() - t0
        log.info(
            "DONE source=%s country=%s new=%d gone=%d elapsed=%.1fs",
            source, country, stats["new"], stats["gone"], elapsed,
        )
    finally:
        await rdb.aclose()
        await pg.close()
