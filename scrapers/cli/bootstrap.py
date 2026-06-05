"""
Bootstrap CLI — initialize all production state for a fresh CARDEX deployment.

Runs in order:
  1. SQLite engine.db: create tables + migrate (idempotent)
  2. PG: ensure portal_cadence table + seed all 71+ portals
  3. PG: ensure vehicle_index + vehicle_events tables (indexer schema)
  4. SQLite: populate work_queue with one immediate job per portal (optional)
  5. Report: summary of what was created / already existed

Usage:
    python -m scrapers.cli.bootstrap                     # full bootstrap
    python -m scrapers.cli.bootstrap --seed-queue        # also enqueue all portals now
    python -m scrapers.cli.bootstrap --dry-run           # report only, no writes

Environment:
    DATABASE_URL    postgresql://...  (default: local dev)
    ENGINE_DB_PATH  path to engine.db (default: scrapers/engine.db)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time

from urllib.parse import urlsplit

from scrapers.db import connect, migrate
from scrapers.engine.router.domain_map import Tier, get as get_portal_spec
from scrapers.portals import PORTAL_REGISTRY
from scrapers.scheduler import SchedulerConfig, enqueue

log = logging.getLogger(__name__)


def _mask_dsn(dsn: str) -> str:
    """Render a DSN for display with the password redacted.

    The previous `dsn.split('@')[0]` kept the whole userinfo — including the
    password — before the '@', so the secret was printed verbatim.
    """
    try:
        parts = urlsplit(dsn)
    except ValueError:
        return "<unparseable DSN>"
    if not parts.hostname:
        return "<dsn hidden>"
    user = parts.username or ""
    cred = f"{user}:***@" if parts.password else (f"{user}@" if user else "")
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{cred}{parts.hostname}{port}{parts.path}"


async def _bootstrap_pg(dsn: str, dry_run: bool) -> dict[str, int]:
    """Create PG tables and seed portal_cadence."""
    import asyncpg
    from scrapers.common.indexer import ensure_schema as ensure_indexer
    from scrapers.scheduler_pg import ensure_schema as ensure_cadence, seed_portals

    stats: dict[str, int] = {"cadence_seeded": 0, "indexer_tables": 0}

    if dry_run:
        log.info("[DRY RUN] would create portal_cadence + vehicle_index + vehicle_events")
        stats["cadence_seeded"] = len(PORTAL_REGISTRY)
        return stats

    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
    try:
        await ensure_cadence(pool)
        log.info("PG: portal_cadence table ensured")

        count = await seed_portals(pool)
        stats["cadence_seeded"] = count
        log.info("PG: %d portal_cadence rows seeded", count)

        await ensure_indexer(pool)
        stats["indexer_tables"] = 1
        log.info("PG: vehicle_index + vehicle_events tables ensured")
    finally:
        await pool.close()

    return stats


def _bootstrap_sqlite(db_path: str, dry_run: bool) -> dict[str, int]:
    """Create engine.db and run migrations."""
    stats: dict[str, int] = {"sqlite_version": 0}
    if dry_run:
        log.info("[DRY RUN] would create/migrate engine.db at %s", db_path)
        return stats

    conn = connect(db_path)
    try:
        migrate(conn)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        stats["sqlite_version"] = version
        log.info("SQLite: engine.db at version %d", version)
    finally:
        conn.close()

    return stats


def _seed_work_queue(db_path: str, dry_run: bool) -> int:
    """Enqueue one immediate job per registered portal."""
    if dry_run:
        log.info("[DRY RUN] would enqueue %d portal jobs", len(PORTAL_REGISTRY))
        return len(PORTAL_REGISTRY)

    conn = connect(db_path)
    now = int(time.time())
    enqueued = 0
    try:
        migrate(conn)
        for domain, scraper_cls in sorted(PORTAL_REGISTRY.items()):
            country = scraper_cls.COUNTRY
            spec = get_portal_spec(domain)
            tier = spec.tier if spec else Tier.T1

            # Check if already has pending work
            existing = conn.execute(
                "SELECT 1 FROM work_queue WHERE portal = ? AND country = ? "
                "AND status IN ('pending', 'running') LIMIT 1",
                (domain, country),
            ).fetchone()
            if existing:
                continue

            enqueue(
                conn,
                portal=domain,
                country=country,
                tier=tier,
                scheduled_at=now,
                priority=5,
                now=now,
            )
            enqueued += 1
    finally:
        conn.close()

    log.info("SQLite: %d work_queue jobs enqueued", enqueued)
    return enqueued


async def run(args: argparse.Namespace) -> None:
    dsn = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
    db_path = os.environ.get("ENGINE_DB_PATH", "scrapers/engine.db")

    print(f"CARDEX Bootstrap — {len(PORTAL_REGISTRY)} registered portals")
    print(f"  PG DSN:      {_mask_dsn(dsn)}")
    print(f"  Engine DB:   {db_path}")
    print(f"  Dry run:     {args.dry_run}")
    print(f"  Seed queue:  {args.seed_queue}")
    print()

    # 1. SQLite engine.db
    sqlite_stats = _bootstrap_sqlite(db_path, args.dry_run)
    print(f"  [1/4] SQLite engine.db: version {sqlite_stats.get('sqlite_version', '?')}")

    # 2. PG tables + seed
    try:
        pg_stats = await _bootstrap_pg(dsn, args.dry_run)
        print(f"  [2/4] PG portal_cadence: {pg_stats.get('cadence_seeded', 0)} rows seeded")
        print(f"  [3/4] PG indexer schema: {'ensured' if pg_stats.get('indexer_tables') else 'skipped'}")
    except Exception as exc:
        print(f"  [2/4] PG: FAILED — {exc}")
        print("         (PG is optional for local dev; coordinator uses SQLite)")
        pg_stats = {}

    # 3. Work queue seed (optional)
    if args.seed_queue:
        count = _seed_work_queue(db_path, args.dry_run)
        print(f"  [4/4] Work queue: {count} jobs enqueued")
    else:
        print(f"  [4/4] Work queue: skipped (use --seed-queue to populate)")

    # Summary
    print()
    print("Bootstrap complete. Next steps:")
    print("  1. Start coordinator:  python -m scrapers.coordinator")
    print("  2. Start scheduler:    python -m scrapers.scheduler_pg")
    print("  3. Monitor:            http://localhost:9090/metrics")

    # Per-country summary
    by_country: dict[str, list[str]] = {}
    for domain, cls in sorted(PORTAL_REGISTRY.items()):
        by_country.setdefault(cls.COUNTRY, []).append(domain)
    print()
    print("Portal coverage:")
    for country in sorted(by_country):
        portals = by_country[country]
        print(f"  {country}: {len(portals)} portals")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap CARDEX scraping engine")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no writes")
    parser.add_argument("--seed-queue", action="store_true", help="Enqueue all portals immediately")
    args = parser.parse_args()

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
