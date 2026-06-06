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
from dataclasses import dataclass, field
from typing import Sequence
from urllib.parse import urlparse

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


@dataclass
class BatchResult:
    """Outcome of one streaming INSERT batch.

    `seen` holds *every* valid deep-link hash in the batch (new or pre-existing);
    the caller accumulates it across a cycle so stale detection at the end sees the
    complete cycle set. `new` counts the rows this batch genuinely inserted.
    """

    seen: set[str] = field(default_factory=set)
    new: int = 0


def _hash_urls(urls: Sequence[str]) -> dict[str, str]:
    """Map valid deep-link URLs to their hash. Drops root-domain URLs (no path)."""
    hash_to_url: dict[str, str] = {}
    for u in urls:
        parsed = urlparse(u)
        if not parsed.path or parsed.path in ("/", ""):
            continue
        hash_to_url[url_hash(u)] = u
    return hash_to_url


async def insert_batch(
    pg: asyncpg.Pool,
    rdb: aioredis.Redis,
    source_key: str,
    country: str,
    domain: str,
    urls: Sequence[str],
) -> BatchResult:
    """
    Streaming, INSERT-only persistence of one batch of deep links. NEVER deletes.

    Idempotent and safe to call repeatedly within a cycle: `INSERT ... ON CONFLICT
    DO NOTHING RETURNING url_hash` lets PG decide atomically which rows are genuinely
    new, so SEEN events and the enrich stream are emitted *exactly once* per URL even
    across re-runs or overlapping batches — without loading the portal's existing
    hash set into memory. This is the streaming counterpart of `delta`'s phase 4a; the
    stale DELETE (phase 4b) is deferred to `delete_stale`, run once at cycle end, so a
    partial flush can never GONE-mark listings simply not yet reached.
    """
    hash_to_url = _hash_urls(urls)
    if not hash_to_url:
        return BatchResult()

    items = list(hash_to_url.items())
    inserted: list[str] = []
    for i in range(0, len(items), _PG_BATCH):
        chunk = items[i : i + _PG_BATCH]
        hashes = [h for h, _ in chunk]
        originals = [u for _, u in chunk]
        async with pg.acquire() as conn:
            rows = await conn.fetch(
                "INSERT INTO vehicle_index (url_hash,url_original,source_domain,country,last_seen) "
                "SELECT h,u,$3,$4,NOW() FROM unnest($1::text[],$2::text[]) AS t(h,u) "
                "ON CONFLICT (url_hash) DO NOTHING RETURNING url_hash",
                hashes, originals, domain, country,
            )
            new_hashes = [r["url_hash"] for r in rows]
            if new_hashes:
                new_urls = [hash_to_url[h] for h in new_hashes]
                await conn.execute(
                    "INSERT INTO vehicle_events (url_hash,url_original,source_domain,country,event_type) "
                    "SELECT h,u,$3,$4,'SEEN' FROM unnest($1::text[],$2::text[]) AS t(h,u)",
                    new_hashes, new_urls, domain, country,
                )
        inserted.extend(new_hashes)

    if inserted:
        pipe = rdb.pipeline(transaction=False)
        for h in inserted:
            pipe.xadd(
                _ENRICH_STREAM,
                {"h": h, "u": hash_to_url[h], "s": source_key, "c": country},
                maxlen=5_000_000,
            )
        await pipe.execute()

    return BatchResult(seen=set(hash_to_url), new=len(inserted))


async def delete_stale(
    pg: asyncpg.Pool,
    country: str,
    domain: str,
    seen: set[str],
) -> int:
    """
    DELETE rows for (domain, country) whose hash is NOT in `seen` (GONE).

    MUST be called exactly once, at the end of a COMPLETE cycle, with the full set of
    hashes seen this cycle. Calling it on a partial cycle would wrongly GONE-mark live
    listings the scrape simply did not reach — which is why `BasePortalScraper.run`
    only invokes it when the harvest finished clean (no soft block, no truncation).
    """
    async with pg.acquire() as conn:
        rows = await conn.fetch(
            "SELECT url_hash FROM vehicle_index WHERE source_domain=$1 AND country=$2",
            domain, country,
        )
    stale_list = [r["url_hash"] for r in rows if r["url_hash"] not in seen]
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
    return len(stale_list)


class StreamingDeltaSink:
    """
    Per-portal URL sink that persists incrementally and reconciles once at the end.

    The coordinator hands this to `BasePortalScraper.run` as `on_urls`. Each call
    streams a batch straight to PG (INSERT-only) and accumulates the cycle's seen
    hashes — never the URL strings — so memory stays bounded regardless of inventory
    size. `finalize` runs the stale DELETE, but only when the scraper reports a
    complete, clean harvest (it calls `finalize` solely in that case), so a partial or
    soft-blocked cycle persists what it found and defers GONE reconciliation.
    """

    def __init__(
        self,
        pg: asyncpg.Pool,
        rdb: aioredis.Redis,
        *,
        source_key: str,
        country: str,
        domain: str,
    ) -> None:
        self._pg = pg
        self._rdb = rdb
        self._source_key = source_key
        self._country = country
        self._domain = domain
        self._seen: set[str] = set()
        self._new = 0

    async def __call__(self, urls: Sequence[str]) -> None:
        result = await insert_batch(
            self._pg, self._rdb, self._source_key, self._country, self._domain, urls
        )
        self._seen |= result.seen
        self._new += result.new

    async def finalize(self) -> dict[str, int]:
        gone = await delete_stale(self._pg, self._country, self._domain, self._seen)
        log.info(
            "finalize source=%s country=%s seen=%d new=%d gone=%d",
            self._domain, self._country, len(self._seen), self._new, gone,
        )
        return {"new": self._new, "gone": gone}


async def delta(
    pg: asyncpg.Pool,
    rdb: aioredis.Redis,
    source_key: str,
    country: str,
    domain: str,
    urls: Sequence[str],
) -> dict[str, int]:
    """
    Atomic full-cycle set diff against the PG source of truth (single-shot).

    INSERT new -> vehicle_index + vehicle_events(SEEN) + enrich stream; DELETE stale
    -> vehicle_index + vehicle_events(GONE); existing non-mutated rows are ZERO TOUCH.
    Reuses the streaming primitives so behaviour stays identical to the incremental
    path: it requires the COMPLETE url list (it deletes everything not present), so it
    is only valid when the caller has the whole cycle in hand. Memory-bounded callers
    should use `StreamingDeltaSink` instead.
    """
    result = await insert_batch(pg, rdb, source_key, country, domain, urls)
    gone = await delete_stale(pg, country, domain, result.seen)
    return {"new": result.new, "gone": gone}


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
