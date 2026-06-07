"""
Domain-resolution orchestrator — RAM-safe, idempotent, multi-via.

Finds the website for dealers that have name+city+country but no ``domain``, the
core of the "dealers WITH web" goal. For each dealer: web-search (DDG→Mojeek) →
rank candidate domains → VALIDATE each top candidate's homepage (must prove it's
this dealer) → ``UPDATE … SET domain`` by id. A domain is persisted ONLY after
validation; nothing is invented.

RAM-SAFE (non-negotiable — fill RAM slowly, never saturate):
  * KEYSET pagination by id (``WHERE domain IS NULL AND id > last``) — at most
    ``batch`` rows in memory, ever; no ``fetchall``, no long-held cursor/txn.
  * Low fixed CONCURRENCY (semaphore) + jittered sleep per search → polite to DDG
    and bounded sockets.
  * ``gc.collect()`` between batches + an RSS watchdog that throttles (sleeps) if
    resident memory climbs past a threshold.

IDEMPOTENT: only NULL-domain rows are selected and the UPDATE is guarded
``WHERE id=$ AND domain IS NULL``; re-running never re-resolves or duplicates. A
domain already owned by another (domain,country) row (a chain sharing a site) hits
the unique index → caught and skipped, not crashed.

Only UPDATEs existing rows (never INSERT) — safe to run alongside the FR sweep,
provided ``--countries`` excludes FR until that sweep finishes.

    python -m scrapers.discovery.domain_resolution.resolver \
        --countries DE,ES,CH,NL,BE --batch 500 --concurrency 3 --limit 0
"""
from __future__ import annotations

import argparse
import asyncio
import gc
import logging
import os
import random
import time
from dataclasses import dataclass, field

import asyncpg

from scrapers.discovery.domain_resolution.candidate import ranked_candidates
from scrapers.discovery.domain_resolution.search import search_all
from scrapers.discovery.domain_resolution.validate import validate_domain

log = logging.getLogger("domain_resolution")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [domres] %(message)s",
)

_DSN = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_RSS_LIMIT_MB = int(os.environ.get("DOMRES_RSS_LIMIT_MB", "1200"))
_VALIDATE_TOP = int(os.environ.get("DOMRES_VALIDATE_TOP", "3"))

_SELECT = """
SELECT id, name, city, country
FROM discovery_candidates
WHERE domain IS NULL AND name IS NOT NULL AND country = ANY($1::text[]) AND id > $2
ORDER BY id
LIMIT $3
"""


@dataclass
class Stats:
    """Per-country/-via resolution tally."""

    attempted: int = 0
    resolved: int = 0
    no_results: int = 0
    no_valid_candidate: int = 0
    false_positives: int = 0          # candidates fetched that FAILED validation
    dup_domain: int = 0               # validated but domain already owned (chain)
    by_country: dict = field(default_factory=dict)
    by_provider: dict = field(default_factory=dict)

    def bump(self, d: dict, key: str) -> None:
        d[key] = d.get(key, 0) + 1


def _rss_mb() -> float | None:
    try:
        import psutil  # type: ignore

        return psutil.Process().memory_info().rss / 1e6
    except Exception:  # noqa: BLE001 — psutil optional; batch+gc already bound RAM
        return None


def _make_session():
    """One reused curl_cffi browser-impersonating session for search + validation."""
    import curl_cffi.requests as cr

    return cr.AsyncSession(impersonate="chrome", timeout=20)


async def resolve_one(session, row, stats: Stats) -> None:
    """Search → rank → validate-top → UPDATE for one dealer (UPDATE done by caller)."""
    name, city, country = row["name"], row["city"] or "", row["country"]
    stats.attempted += 1
    stats.bump(stats.by_country, f"{country}:attempted")

    provider, html = await search_all(session, name, city)
    if not html:
        stats.no_results += 1
        return
    stats.bump(stats.by_provider, f"{provider}:pages")

    async def _fetch(url):
        return await session.get(url, timeout=15, allow_redirects=True)

    for host, _score in ranked_candidates(html, name, country, top=_VALIDATE_TOP + 1)[:_VALIDATE_TOP]:
        ok, why = await validate_domain(host, name, city, _fetch)
        if ok:
            row["_resolved"] = host
            row["_provider"] = provider
            stats.resolved += 1
            stats.bump(stats.by_country, f"{country}:resolved")
            stats.bump(stats.by_provider, f"{provider}:resolved")
            log.info("RESOLVED %s/%s → %s (%s, %s)", name[:40], country, host, provider, why)
            return
        stats.false_positives += 1
    stats.no_valid_candidate += 1


async def _persist(pool, row) -> str | None:
    """Idempotent UPDATE of the resolved domain by id; returns the host or None."""
    host = row.get("_resolved")
    if not host:
        return None
    try:
        await pool.execute(
            "UPDATE discovery_candidates SET domain=$1, url=$2, last_seen=NOW() "
            "WHERE id=$3 AND domain IS NULL",
            host, f"https://{host}/", row["id"],
        )
        return host
    except asyncpg.UniqueViolationError:
        return "_dup"  # another (domain,country) row owns it (chain) — skip, not fatal


async def _maybe_throttle() -> None:
    rss = _rss_mb()
    if rss is not None and rss > _RSS_LIMIT_MB:
        log.warning("RSS %.0fMB > %dMB — throttling (gc + sleep)", rss, _RSS_LIMIT_MB)
        gc.collect()
        await asyncio.sleep(8)


async def run(
    *,
    countries: list[str],
    batch_size: int = 500,
    concurrency: int = 3,
    limit: int = 0,
    sleep_base: float = 1.2,
    start_id: int = 0,
    pool: asyncpg.Pool | None = None,
    session=None,
) -> Stats:
    """Resolve domains for ``countries`` in RAM-safe keyset batches. ``limit``>0 caps attempts."""
    owns_pool = pool is None
    owns_session = session is None
    pool = pool or await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    session = session or _make_session()
    sem = asyncio.Semaphore(concurrency)
    stats = Stats()
    last_id = start_id
    t0 = time.monotonic()
    try:
        while limit == 0 or stats.attempted < limit:
            take = batch_size if limit == 0 else min(batch_size, limit - stats.attempted)
            rows = await pool.fetch(_SELECT, countries, last_id, take)
            if not rows:
                break
            mutable = [dict(r) for r in rows]

            async def _guarded(r):
                async with sem:
                    await resolve_one(session, r, stats)
                    await asyncio.sleep(sleep_base + random.uniform(0, 0.8))  # polite

            await asyncio.gather(*(_guarded(r) for r in mutable))
            for r in mutable:
                host = await _persist(pool, r)
                if host == "_dup":
                    stats.resolved -= 1
                    stats.dup_domain += 1

            last_id = mutable[-1]["id"]
            gc.collect()
            await _maybe_throttle()
            log.info("batch done last_id=%d attempted=%d resolved=%d (%.0fs)",
                     last_id, stats.attempted, stats.resolved, time.monotonic() - t0)
        log.info("DONE attempted=%d resolved=%d no_results=%d no_valid=%d false_pos=%d dup=%d",
                 stats.attempted, stats.resolved, stats.no_results,
                 stats.no_valid_candidate, stats.false_positives, stats.dup_domain)
        return stats
    finally:
        if owns_session:
            try:
                await session.close()
            except Exception:  # noqa: BLE001
                pass
        if owns_pool:
            await pool.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default="DE,ES,CH,NL,BE",
                    help="ISO-2 list; exclude FR while the FR sweep runs")
    ap.add_argument("--batch", type=int, default=500)
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--start-id", type=int, default=0, help="keyset start (sample a fresh slice)")
    args = ap.parse_args()
    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    asyncio.run(run(countries=countries, batch_size=args.batch,
                    concurrency=args.concurrency, limit=args.limit, start_id=args.start_id))


if __name__ == "__main__":
    main()
