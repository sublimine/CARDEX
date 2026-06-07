"""
Re-validate persisted resolutions against the CURRENT gate — purge regressions.

When the validation gate tightens (e.g. the automotive signal moves from any-weak-word
to a strong, discriminating set), domains persisted under the old, looser rule may no
longer hold. This re-fetches every worker-resolved row (those carrying
``external_refs.resolved_via``) and re-applies the live validator; a row that no longer
confirms is **purged** back to identity-only (``domain=NULL``) and re-queued, never left
as a fabricated "dealer with web".

    UPDATE domain=NULL, url=NULL, external_refs -= resolved_via,
           ddg_attempts=0, ddg_last_attempt=NULL  (re-claimable by the fixed worker)

RAM-safe: keyset over the (small) resolved set, low concurrency, gc between batches.
Idempotent: only re-checks rows that still carry a resolved_via tag.

    python -m scrapers.discovery.domain_resolution.revalidate --countries DE,ES,CH,NL,BE
"""
from __future__ import annotations

import argparse
import asyncio
import gc
import logging
import os
from dataclasses import dataclass, field

import asyncpg

from scrapers.discovery.domain_resolution.validate import confirms_automotive, confirms_dealer

log = logging.getLogger("domres_revalidate")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [revalidate] %(message)s",
)

_DSN = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")

_SELECT = """
SELECT id, name, city, country, domain, external_refs->>'resolved_via' AS via
FROM discovery_candidates
WHERE external_refs ? 'resolved_via' AND domain IS NOT NULL
  AND country = ANY($1::text[]) AND id > $2
ORDER BY id LIMIT $3
"""

_PURGE = """
UPDATE discovery_candidates
SET domain = NULL, url = NULL, external_refs = external_refs - 'resolved_via',
    ddg_attempts = 0, ddg_last_attempt = NULL, ddg_error = $2
WHERE id = $1
"""

# Clearing the domain re-enters the row into the identity unique index; if an
# identity-only twin already exists (same source/registry_id/country) the UPDATE
# collides — the FP row is then a redundant duplicate, so delete it (the twin keeps
# the identity and will be re-resolved cleanly).
_PURGE_DELETE = "DELETE FROM discovery_candidates WHERE id = $1"


@dataclass
class Stats:
    checked: int = 0
    kept: int = 0
    purged: int = 0
    unreachable: int = 0
    by_reason: dict = field(default_factory=dict)


def _make_session():
    import curl_cffi.requests as cr

    return cr.AsyncSession(impersonate="chrome", timeout=20)


async def _check(session, row, stats: Stats, pool) -> None:
    stats.checked += 1
    via = row["via"] or ""
    try:
        resp = await session.get(f"https://{row['domain']}/", timeout=15,
                                 allow_redirects=True, verify=False)
        html = resp.text or ""
    except Exception as exc:  # noqa: BLE001
        # Transport failure is NOT proof the domain is wrong — keep it, don't purge on a
        # transient network error (avoid destroying good data on a blip).
        stats.unreachable += 1
        return
    if via.startswith("email"):
        ok, why = confirms_automotive(html)
    else:
        ok, why = confirms_dealer(html, row["name"] or "", row["city"] or "", require_name=True)
    if ok:
        stats.kept += 1
        return
    try:
        await pool.execute(_PURGE, row["id"], f"revalidation_purged:{why}"[:120])
    except asyncpg.UniqueViolationError:
        await pool.execute(_PURGE_DELETE, row["id"])  # identity twin exists → drop dup
    stats.purged += 1
    stats.by_reason[why] = stats.by_reason.get(why, 0) + 1
    log.info("PURGED %s (%s) via=%s reason=%s", row["domain"], (row["name"] or "")[:32], via, why)


async def run(*, countries: list[str], limit: int = 0, concurrency: int = 4) -> Stats:
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=6)
    session = _make_session()
    sem = asyncio.Semaphore(concurrency)
    stats = Stats()
    last_id = 0
    try:
        while limit == 0 or stats.checked < limit:
            take = 200 if limit == 0 else min(200, limit - stats.checked)
            rows = await pool.fetch(_SELECT, countries, last_id, take)
            if not rows:
                break

            async def _guard(r):
                async with sem:
                    await _check(session, r, stats, pool)

            await asyncio.gather(*(_guard(r) for r in rows))
            last_id = rows[-1]["id"]
            gc.collect()
            log.info("progress checked=%d kept=%d purged=%d unreachable=%d",
                     stats.checked, stats.kept, stats.purged, stats.unreachable)
        log.info("DONE checked=%d kept=%d purged=%d unreachable=%d by_reason=%s",
                 stats.checked, stats.kept, stats.purged, stats.unreachable, stats.by_reason)
        return stats
    finally:
        try:
            await session.close()
        except Exception:  # noqa: BLE001
            pass
        await pool.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default="DE,ES,CH,NL,BE,FR")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args()
    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    asyncio.run(run(countries=countries, limit=args.limit, concurrency=args.concurrency))


if __name__ == "__main__":
    main()
