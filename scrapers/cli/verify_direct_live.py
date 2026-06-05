"""
Live verification — prove the coordinator scrapes T0/T1 direct (no proxy).

Exercises the REAL engine end to end: real direct identities, the real
coordinator loop, real direct curl_cffi sessions (make_live_session), the real
PG/Redis delta sink, and the live portal APIs. The only concession to politeness
is breadth: the T0/T1 demo scrapers are wrapped to fetch a single segment, ≤2
pages, no subdivision — enough to write real rows without hammering a source. The
engine code itself is unchanged; in production these portals paginate fully.

What it proves:
  * T0 (marktplaats.nl) and T1 (autotrack.nl) jobs EXECUTE on a direct identity
    and write real vehicles to PG vehicle_index.
  * T2 (mobile.de) and T3 (leboncoin.fr) jobs find no eligible identity (they
    require a proxy, none exists) and stay queued on NO_IDENTITY backoff.

Usage:
    REDIS_URL=redis://localhost:56379 python -m scrapers.cli.verify_direct_live
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path

from scrapers import coordinator
from scrapers.coordinator import CoordinatorConfig, make_live_session, make_live_sink_factory
from scrapers.db import connect, migrate
from scrapers.engine.identity.direct import ensure_direct_identities
from scrapers.engine.router.domain_map import Tier, get as get_portal_spec
from scrapers.portals import PORTAL_REGISTRY
from scrapers.scheduler import enqueue

# (domain, country, tier-label) — two direct-eligible, two proxy-only.
_T0 = ("marktplaats.nl", "NL", "T0")
_T1 = ("autotrack.nl", "NL", "T1")
_T2 = ("mobile.de", "DE", "T2")
_T3 = ("leboncoin.fr", "FR", "T3")
_JOBS = (_T0, _T1, _T2, _T3)

# Domains whose scrape is bounded for the demo (the direct-eligible ones we run).
_BOUNDED_DOMAINS = {_T0[0], _T1[0]}


class _BoundedMixin:
    """Politeness cap for the live demo: one segment, ≤2 pages, no subdivision."""

    MAX_PAGES = 2

    def partition_params(self):  # type: ignore[override]
        return super().partition_params()[:1]

    def subdivide_segment(self, params):  # type: ignore[override]
        return []


def _bounded_resolver(domain: str):
    """coordinator.get_scraper replacement: bound T0/T1 demo portals, real otherwise."""
    cls = PORTAL_REGISTRY.get(domain)
    if cls is None:
        return None
    if domain in _BOUNDED_DOMAINS:
        bounded = type(f"Bounded{cls.__name__}", (_BoundedMixin, cls), {})
        return bounded()
    return cls()


def _enqueue_jobs(conn) -> None:
    now = int(time.time())
    for i, (domain, country, _tier) in enumerate(_JOBS):
        spec = get_portal_spec(domain)
        tier = spec.tier if spec else Tier.T1
        enqueue(conn, portal=domain, country=country, tier=tier,
                scheduled_at=now, priority=5 + i, now=now)


def _report(conn, pg_counts: dict[str, int]) -> None:
    print("\n" + "=" * 68)
    print("WORK QUEUE — final state after max_cycles=10")
    print("=" * 68)
    print(f"{'portal':<20}{'tier':<6}{'status':<10}{'attempts':<9}{'last_error':<13}{'backoff_s':>9}")
    now = int(time.time())
    for domain, country, tier in _JOBS:
        row = conn.execute(
            "SELECT status, attempts, last_error, scheduled_at FROM work_queue "
            "WHERE portal=? ORDER BY created_at DESC LIMIT 1",
            (domain,),
        ).fetchone()
        backoff = max(0, (row["scheduled_at"] or now) - now) if row["status"] == "pending" else 0
        print(f"{domain:<20}{tier:<6}{row['status']:<10}{row['attempts']:<9}"
              f"{str(row['last_error'] or '-'):<13}{backoff:>9}")
    print("\n" + "=" * 68)
    print("POSTGRES vehicle_index — real vehicles indexed")
    print("=" * 68)
    for domain, _c, tier in _JOBS:
        print(f"{domain:<20}{tier:<6}{pg_counts.get(domain, 0):>6} rows")


async def main() -> None:
    dsn = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:56379")

    db_path = str(Path(tempfile.gettempdir()) / "cardex_verify_direct.db")
    for suffix in ("", "-wal", "-shm"):
        p = Path(db_path + suffix)
        if p.exists():
            p.unlink()

    conn = connect(db_path)
    migrate(conn)
    created = ensure_direct_identities(conn)
    print(f"direct identities ensured: {created}")
    _enqueue_jobs(conn)
    print(f"enqueued {len(_JOBS)} jobs: " + ", ".join(f"{d}({t})" for d, _c, t in _JOBS))

    # Bound the breadth of the two direct-eligible demo scrapers. Restored in the
    # finally block so importing this module never leaves the coordinator patched.
    original_get_scraper = coordinator.get_scraper
    coordinator.get_scraper = _bounded_resolver  # type: ignore[assignment]

    from scrapers.common import indexer
    pg = await indexer.make_pg(dsn)
    rdb = await indexer.make_redis(redis_url)
    await indexer.ensure_schema(pg)

    # Demo-scoped reset: clear ONLY the four demo domains so the report shows
    # exactly the rows THIS run indexes (the in-process delta dedups against PG,
    # so a prior run would otherwise mask fresh inserts as "0 new").
    demo_domains = [d for d, _c, _t in _JOBS]
    await pg.execute("DELETE FROM vehicle_index WHERE source_domain = ANY($1::text[])", demo_domains)
    await pg.execute("DELETE FROM vehicle_events WHERE source_domain = ANY($1::text[])", demo_domains)

    # Baseline counts so we report what THIS run indexed.
    base_counts = {
        d: await pg.fetchval("SELECT count(*) FROM vehicle_index WHERE source_domain=$1", d)
        for d, _c, _t in _JOBS
    }

    async def _noop_sleep(_d: float) -> None:
        return None

    cfg = CoordinatorConfig(db_path=db_path, prometheus_port=0)
    try:
        await coordinator.run(
            cfg,
            session_factory=make_live_session,
            sink_factory=make_live_sink_factory(pg, rdb),
            conn=conn,
            sleep=_noop_sleep,
            now_fn=time.time,
            max_cycles=10,
        )
        pg_counts = {
            d: (await pg.fetchval("SELECT count(*) FROM vehicle_index WHERE source_domain=$1", d)) - base_counts[d]
            for d, _c, _t in _JOBS
        }
    finally:
        coordinator.get_scraper = original_get_scraper  # type: ignore[assignment]
        await rdb.aclose()
        await pg.close()

    _report(conn, pg_counts)
    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
