"""
DDG resolver worker — identity-only rows → domain via DuckDuckGo HTML search.

Consumes `discovery_candidates` where `domain IS NULL` (rows produced by
identity-only sources: SIRENE, Zefix, BMW STOLO, OSM without website tag).
For each row, builds a `name + city + country` query and asks the
DDGResolver to return a validated domain.

Outcome routing
---------------
    resolved          → UPDATE SET domain, url
                         • collision with existing (domain,country) row:
                           merge external_refs into the existing row and
                           DELETE the identity-only row
                         • otherwise plain UPDATE
                         — the promoted row immediately enters the
                           sitemap_resolver queue (sitemap_status='pending'
                           + domain now NOT NULL)

    not resolved      → UPDATE SET ddg_attempts = ddg_attempts + 1,
                                    ddg_last_attempt = NOW(),
                                    ddg_error = <reason>
                         after 5 failed attempts the row drops out of the
                         queue index permanently

Claim protocol
--------------
Atomic CTE claim identical to the other workers. `ddg_last_attempt` is
bumped at claim time to serve as cursor + crash recovery — a worker that
dies mid-resolve releases its claim after the stale interval.

Usage
-----
    python -m scrapers.discovery.ddg_worker
    DDG_WORKER_ONESHOT=1 python -m scrapers.discovery.ddg_worker

Environment
-----------
    DATABASE_URL             postgresql://...
    DDG_WORKER_BATCH         rows per claim        (default 25)
    DDG_WORKER_CONCURRENCY   parallel resolves     (default 5)
    DDG_WORKER_MIN_INTERVAL  PG interval between retries per row
                             (default '24 hours')
    DDG_WORKER_MAX_ATTEMPTS  give-up threshold     (default 5)
    DDG_WORKER_IDLE_SLEEP    sleep when queue empty (default 60)
    DDG_WORKER_ONESHOT       if '1', exit when queue is empty
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import asyncpg
import httpx

from scrapers.discovery.sources.ddg_resolver import DDGResolver

log = logging.getLogger(__name__)

_DEFAULT_DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://cardex:cardex@localhost:5432/cardex",
)

_BATCH_SIZE = int(os.environ.get("DDG_WORKER_BATCH", "25"))
_CONCURRENCY = int(os.environ.get("DDG_WORKER_CONCURRENCY", "5"))
_MIN_INTERVAL = os.environ.get("DDG_WORKER_MIN_INTERVAL", "24 hours")
_MAX_ATTEMPTS = int(os.environ.get("DDG_WORKER_MAX_ATTEMPTS", "5"))
_IDLE_SLEEP = float(os.environ.get("DDG_WORKER_IDLE_SLEEP", "60"))
_ONESHOT = os.environ.get("DDG_WORKER_ONESHOT", "0") == "1"


# ── SQL ──────────────────────────────────────────────────────────────────────

_CLAIM_SQL = f"""
WITH claimed AS (
    SELECT id
    FROM discovery_candidates
    WHERE domain IS NULL
      AND ddg_attempts < {_MAX_ATTEMPTS}
      AND (ddg_last_attempt IS NULL
           OR ddg_last_attempt < NOW() - $2::interval)
      AND name IS NOT NULL
    ORDER BY ddg_last_attempt NULLS FIRST, first_seen
    LIMIT $1
    FOR UPDATE SKIP LOCKED
)
UPDATE discovery_candidates
   SET ddg_last_attempt = NOW()
FROM claimed
WHERE discovery_candidates.id = claimed.id
RETURNING
    discovery_candidates.id,
    discovery_candidates.country,
    discovery_candidates.name,
    discovery_candidates.city,
    discovery_candidates.ddg_attempts,
    discovery_candidates.external_refs
"""

# Attempt to promote identity → domain-ful. If the unique index on
# (domain, country) blocks us, the caller handles the collision path.
_PROMOTE_SQL = """
UPDATE discovery_candidates
SET domain        = $2,
    url           = $3,
    sitemap_status = 'pending',
    ddg_error     = NULL
WHERE id = $1
"""

_MARK_FAIL_SQL = """
UPDATE discovery_candidates
SET ddg_attempts     = ddg_attempts + 1,
    ddg_error        = $2,
    ddg_last_attempt = NOW()
WHERE id = $1
"""

# Collision path: the resolved domain already exists for this country.
# Merge external_refs into the existing row and delete the identity-only
# duplicate. Merging preserves OEM partner IDs, NAF codes, OSM ids, etc.,
# so the existing domain-ful row accumulates provenance from every source
# that saw the same dealer.
_COLLISION_MERGE_SQL = """
WITH moved AS (
    DELETE FROM discovery_candidates
    WHERE id = $1
    RETURNING external_refs
)
UPDATE discovery_candidates
SET external_refs = discovery_candidates.external_refs || COALESCE(moved.external_refs, '{}'::jsonb)
FROM moved
WHERE discovery_candidates.domain = $2
  AND discovery_candidates.country = $3
"""


# ── Worker ───────────────────────────────────────────────────────────────────

async def _claim_batch(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    return await pool.fetch(_CLAIM_SQL, _BATCH_SIZE, _MIN_INTERVAL)


async def _resolve_one(
    pool: asyncpg.Pool,
    resolver: DDGResolver,
    row: asyncpg.Record,
) -> str:
    """Returns outcome tag: 'resolved' | 'collided' | 'failed' | 'error'."""
    try:
        website = await resolver.resolve(
            name=row["name"],
            city=row["city"],
            country=row["country"],
        )
    except Exception as exc:
        await pool.execute(
            _MARK_FAIL_SQL,
            row["id"],
            f"resolve_exc:{type(exc).__name__}"[:200],
        )
        return "error"

    if not website:
        await pool.execute(_MARK_FAIL_SQL, row["id"], "no_match")
        return "failed"

    domain = _extract_domain(website)
    if not domain:
        await pool.execute(_MARK_FAIL_SQL, row["id"], "invalid_domain")
        return "failed"

    # Happy path: atomic UPDATE. Unique violation → collision merge.
    try:
        await pool.execute(_PROMOTE_SQL, row["id"], domain, website)
        return "resolved"
    except asyncpg.UniqueViolationError:
        # Another row already owns (domain, country). Merge external_refs
        # from the identity-only row into the incumbent and delete the
        # identity-only row.
        try:
            await pool.execute(
                _COLLISION_MERGE_SQL,
                row["id"],
                domain,
                row["country"],
            )
            return "collided"
        except Exception as exc:
            log.warning(
                "ddg_worker: collision merge failed id=%d domain=%s: %s",
                row["id"], domain, exc,
            )
            await pool.execute(
                _MARK_FAIL_SQL,
                row["id"],
                f"collision_merge_err:{type(exc).__name__}"[:200],
            )
            return "error"
    except Exception as exc:
        await pool.execute(
            _MARK_FAIL_SQL,
            row["id"],
            f"promote_err:{type(exc).__name__}"[:200],
        )
        return "error"


async def _process_batch(
    pool: asyncpg.Pool,
    resolver: DDGResolver,
    batch: list[asyncpg.Record],
) -> dict[str, int]:
    sem = asyncio.Semaphore(_CONCURRENCY)
    counts = {"resolved": 0, "collided": 0, "failed": 0, "error": 0}

    async def _one(row: asyncpg.Record) -> None:
        async with sem:
            outcome = await _resolve_one(pool, resolver, row)
            counts[outcome] = counts.get(outcome, 0) + 1

    await asyncio.gather(*(_one(r) for r in batch))
    return counts


def _extract_domain(url: str) -> str | None:
    import urllib.parse
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return None
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or None


async def run() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    pool = await asyncpg.create_pool(
        _DEFAULT_DSN, min_size=2, max_size=6, command_timeout=60,
    )
    log.info(
        "ddg_worker: starting — batch=%d conc=%d min_interval=%r max_attempts=%d oneshot=%s",
        _BATCH_SIZE, _CONCURRENCY, _MIN_INTERVAL, _MAX_ATTEMPTS, _ONESHOT,
    )

    totals = {"resolved": 0, "collided": 0, "failed": 0, "error": 0}

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            limits=httpx.Limits(
                max_keepalive_connections=_CONCURRENCY * 2,
                max_connections=_CONCURRENCY * 4,
            ),
        ) as client:
            resolver = DDGResolver(client)

            while True:
                batch = await _claim_batch(pool)
                if not batch:
                    if _ONESHOT:
                        log.info("ddg_worker: queue empty, oneshot exit")
                        break
                    log.debug("ddg_worker: queue empty, sleeping %.0fs", _IDLE_SLEEP)
                    await asyncio.sleep(_IDLE_SLEEP)
                    continue

                counts = await _process_batch(pool, resolver, batch)
                for k, v in counts.items():
                    totals[k] = totals.get(k, 0) + v

                log.info(
                    "ddg_worker: batch=%d  resolved=%d collided=%d failed=%d error=%d  "
                    "totals=%d/%d/%d/%d",
                    len(batch),
                    counts["resolved"], counts["collided"],
                    counts["failed"], counts["error"],
                    totals["resolved"], totals["collided"],
                    totals["failed"], totals["error"],
                )
    finally:
        await pool.close()

    log.info(
        "ddg_worker: stopped — totals resolved=%d collided=%d failed=%d error=%d",
        totals["resolved"], totals["collided"],
        totals["failed"], totals["error"],
    )


if __name__ == "__main__":
    asyncio.run(run())
