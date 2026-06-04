"""
Production DueSource + writeback for the scheduler.

Bridges the scheduler's pure decision layer (scheduler.py) to the PostgreSQL
portal_cadence table. Two responsibilities:

  1. `make_due_source(pg_pool)` -> a DueSource callable that reads portal_cadence
     rows where `next_scrape_at <= NOW()` and `enabled = TRUE`, converts each to
     a `PortalChangeStats`, and yields them.

  2. `writeback(pg_pool, portal, country, decision)` persists a ScheduleDecision
     back to portal_cadence after the scheduler's plan_cycle finishes.

  3. `ensure_schema(pg_pool)` creates the portal_cadence table idempotently.

  4. `seed_portals(pg_pool)` populates portal_cadence from the PORTAL_REGISTRY.

asyncpg is imported lazily (inside function bodies only) so this module can be
imported and its pure helpers tested without PG drivers installed — mirroring
the coordinator's lazy-import pattern.

Entry point: `python -m scrapers.scheduler_pg`
"""
from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from scrapers.engine.router.domain_map import Tier, get as get_portal_spec
from scrapers.portals import PORTAL_REGISTRY
from scrapers.scheduler import (
    DueSource,
    PortalChangeStats,
    ScheduleDecision,
    SchedulerConfig,
    run as scheduler_run,
)

log = logging.getLogger(__name__)

_DEFAULT_DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://cardex:cardex_dev_only@localhost:5432/cardex",
)

# Default initial interval per tier — higher tiers are more expensive so start
# slower. T0/T1 start at 6h, T2 at 12h, T3 at 24h.
_INITIAL_INTERVAL_H: dict[Tier, float] = {
    Tier.T0: 6.0,
    Tier.T1: 6.0,
    Tier.T2: 12.0,
    Tier.T3: 24.0,
}

# "Static" threshold: if last_change_at is NULL or older than this many days,
# the portal is considered static for section C1 cadence relaxation.
_STATIC_DAYS = 7


# ── Schema DDL (executed via asyncpg, defined as constants) ─────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS portal_cadence (
    portal              TEXT NOT NULL,
    country             CHAR(2) NOT NULL,
    current_interval_h  DOUBLE PRECISION NOT NULL DEFAULT 24.0,
    last_change_at      TIMESTAMPTZ,
    last_scrape_at      TIMESTAMPTZ,
    next_scrape_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    listings_last_cycle INT DEFAULT 0,
    listings_delta      INT DEFAULT 0,
    enabled             BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (portal, country)
)
"""

_IDX_DUE = """
CREATE INDEX IF NOT EXISTS idx_portal_cadence_due
    ON portal_cadence (next_scrape_at) WHERE enabled = TRUE
"""

_IDX_COUNTRY = """
CREATE INDEX IF NOT EXISTS idx_portal_cadence_country
    ON portal_cadence (country, enabled)
"""


# ── Pure helpers (no asyncpg, unit-testable without PG) ─────────────────────

def _row_to_stats(row: Any, now_epoch: int) -> PortalChangeStats:
    """
    Convert a portal_cadence row to a PortalChangeStats for the scheduler.

    Accepts any dict-like or Record that supports __getitem__ by column name.
    Pure function — no I/O.
    """
    last_change = row["last_change_at"]
    listings_delta = row["listings_delta"] or 0

    # A portal "changed" if the last delta was nonzero.
    changed = listings_delta != 0

    # days_since_change: days since last_change_at, or _STATIC_DAYS+1 if NULL.
    if last_change is not None:
        dt = last_change.replace(tzinfo=timezone.utc) if last_change.tzinfo is None else last_change
        delta_s = now_epoch - int(dt.timestamp())
        days_since = max(0, delta_s // 86_400)
    else:
        days_since = _STATIC_DAYS + 1  # trigger relaxation

    return PortalChangeStats(
        portal=row["portal"],
        country=row["country"],
        current_interval_h=row["current_interval_h"],
        changed=changed,
        days_since_change=days_since,
    )


# ── Async PG operations (asyncpg imported lazily) ──────────────────────────

async def ensure_schema(pool: Any) -> None:
    """Create the portal_cadence table and indexes (idempotent)."""
    async with pool.acquire() as conn:
        await conn.execute(_DDL)
        await conn.execute(_IDX_DUE)
        await conn.execute(_IDX_COUNTRY)


async def seed_portals(pool: Any) -> int:
    """
    Insert a cadence row for every registered portal not already in the table.

    Reads PORTAL_REGISTRY (all 71+ scrapers) and domain_map REGISTRY (tier info).
    Returns the count of newly inserted rows.
    """
    inserted = 0
    async with pool.acquire() as conn:
        for domain, scraper_cls in PORTAL_REGISTRY.items():
            country = scraper_cls.COUNTRY
            spec = get_portal_spec(domain)
            tier = spec.tier if spec else Tier.T1
            interval = _INITIAL_INTERVAL_H.get(tier, 12.0)

            result = await conn.execute(
                """
                INSERT INTO portal_cadence (portal, country, current_interval_h, next_scrape_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (portal, country) DO NOTHING
                """,
                domain,
                country,
                interval,
            )
            if result == "INSERT 0 1":
                inserted += 1

    log.info("seed_portals: %d new rows inserted (%d total registered)", inserted, len(PORTAL_REGISTRY))
    return inserted


def make_due_source(pool: Any) -> DueSource:
    """
    Build a DueSource closure over a PG pool.

    The returned callable accepts a sqlite3.Connection (scheduler contract) but
    ignores it — cadence state is read from PG.
    """
    _cache: list[PortalChangeStats] = []
    _cache_epoch: int = 0

    async def _fetch_due() -> list[PortalChangeStats]:
        now_epoch = int(time.time())
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT portal, country, current_interval_h,
                       last_change_at, listings_delta
                FROM portal_cadence
                WHERE enabled = TRUE AND next_scrape_at <= NOW()
                ORDER BY next_scrape_at ASC
                """,
            )
        return [_row_to_stats(r, now_epoch) for r in rows]

    def due_source(_conn: sqlite3.Connection) -> Iterable[PortalChangeStats]:
        """DueSource implementation — reads from PG portal_cadence."""
        nonlocal _cache, _cache_epoch
        now = int(time.time())
        if now > _cache_epoch:
            loop = asyncio.get_event_loop()
            _cache = loop.run_until_complete(_fetch_due())
            _cache_epoch = now
        return _cache

    return due_source


async def writeback(
    pool: Any,
    portal: str,
    country: str,
    decision: ScheduleDecision,
    *,
    delta_stats: dict[str, int] | None = None,
) -> None:
    """
    Persist a ScheduleDecision + optional delta stats back to portal_cadence.

    Called after plan_cycle for each portal that was successfully enqueued.
    """
    now = datetime.now(timezone.utc)
    next_scrape = datetime.fromtimestamp(decision.next_scrape_at, tz=timezone.utc)

    if delta_stats:
        new = delta_stats.get("new", 0)
        gone = delta_stats.get("gone", 0)
        listings_delta = new - gone
        changed = listings_delta != 0
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE portal_cadence
                SET current_interval_h = $1,
                    next_scrape_at = $2,
                    last_scrape_at = $3,
                    listings_delta = $6,
                    listings_last_cycle = $7,
                    last_change_at = CASE WHEN $8 THEN $3 ELSE last_change_at END,
                    updated_at = $3
                WHERE portal = $4 AND country = $5
                """,
                decision.interval_h,
                next_scrape,
                now,
                portal,
                country,
                listings_delta,
                new + gone,
                changed,
            )
    else:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE portal_cadence
                SET current_interval_h = $1,
                    next_scrape_at = $2,
                    updated_at = $3
                WHERE portal = $4 AND country = $5
                """,
                decision.interval_h,
                next_scrape,
                now,
                portal,
                country,
            )


# ── Entry point ─────────────────────────────────────────────────────────────

async def main(config: SchedulerConfig | None = None) -> None:
    """Production entrypoint: wire PG DueSource and run the scheduler loop."""
    import asyncpg  # lazy: only needed at runtime

    config = config or SchedulerConfig()
    dsn = os.environ.get("DATABASE_URL", config.database_url)

    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
    try:
        await ensure_schema(pool)
        await seed_portals(pool)
        due_source = make_due_source(pool)
        await scheduler_run(config, due_source=due_source)
    finally:
        await pool.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main())
