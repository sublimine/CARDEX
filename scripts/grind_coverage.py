"""
Coverage grind — resumable, batch, per-entity E2E over the WHOLE discovery set.

The mission is 100% end-to-end coverage of every dealer/platform in the 6 countries
(recipe proven + real verified inventory + purge), run and proven LOCALLY before the
VPS ever turns on. ``run_dealer_scraping`` validates a fixed md5-top-N sample and can't
advance; this grinds the ENTIRE ``discovery_candidates`` set, batch after batch, and
records every processed entity in a durable ``coverage_ledger`` so it is:

  * resumable  — skips domains already in the ledger (crash/restart safe);
  * measurable — coverage % = ledger rows / discoverable entities, with the real
                 inventory-yielding subset broken out (the honest "how much is caged");
  * complete   — keeps going until no undone entity remains.

Per entity it runs the SAME production seam as the self-healing remediator:
discover → resolve/detect recipe → extract via A6/A7 into ``vehicles`` (cage) →
count-verify → auto-remediate on drift → PURGE (slice-then-purge; the recipe + the
ledger proof are what we keep). The retry/backoff fetcher (harvester) absorbs dealer
throttling so a slow dealer doesn't stall the grind.

    python -m scripts.grind_coverage                         # grind until done
    python -m scripts.grind_coverage --max-batches 5         # bounded run
    GRIND_BATCH=12 python -m scripts.grind_coverage          # batch size
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis.asyncio as aioredis  # noqa: E402

from scrapers.common import indexer  # noqa: E402
from scrapers.dealer_scraping import harvester as hv  # noqa: E402
from scrapers.dealer_scraping.harvester import DealerHarvestResult, harvest_dealer  # noqa: E402
from scrapers.dealer_scraping.remediation import make_remediator  # noqa: E402
from scrapers.dealer_scraping.seam import make_live_purger, make_live_seam  # noqa: E402
from scrapers.pipeline.playwright_extractor import PlaywrightFetcher  # noqa: E402

_DB_URL = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_THROWAWAY_REDIS = os.environ.get("THROWAWAY_REDIS_URL", "redis://localhost:56390")
_LOCALE = {"DE": "de-DE", "FR": "fr-FR", "ES": "es-ES", "NL": "nl-NL", "CH": "de-CH", "BE": "nl-BE"}
_PER_DEALER_TIMEOUT = float(os.environ.get("DEALER_TIMEOUT_S", "180"))
_BATCH = int(os.environ.get("GRIND_BATCH", "12"))
_LIMIT = int(os.environ.get("GRIND_LIMIT", "300"))   # detail pages extracted/dealer (cage slice)


_LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS coverage_ledger (
    domain          text PRIMARY KEY,
    country         text NOT NULL,
    status          text NOT NULL,          -- yielded | no_inventory | no_web | error | timeout
    web_type        text,
    discovery       text,
    discovered      int  DEFAULT 0,
    inventory_count int  DEFAULT 0,         -- verified vehicles extracted before purge
    recipe          text,                   -- extraction strategy proven for this entity
    drift_ok        boolean,
    purged          boolean,
    error           text,
    verified_at     timestamptz DEFAULT now()
)
"""

_NEXT_BATCH_SQL = """
SELECT dc.domain, dc.country
FROM discovery_candidates dc
WHERE dc.domain IS NOT NULL AND dc.domain <> ''
  AND NOT EXISTS (SELECT 1 FROM coverage_ledger cl WHERE cl.domain = dc.domain)
ORDER BY md5(dc.domain)
LIMIT $1
"""

_UPSERT_LEDGER = """
INSERT INTO coverage_ledger
  (domain, country, status, web_type, discovery, discovered, inventory_count,
   recipe, drift_ok, purged, error, verified_at)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11, now())
ON CONFLICT (domain) DO UPDATE SET
  country=EXCLUDED.country, status=EXCLUDED.status, web_type=EXCLUDED.web_type,
  discovery=EXCLUDED.discovery, discovered=EXCLUDED.discovered,
  inventory_count=EXCLUDED.inventory_count, recipe=EXCLUDED.recipe,
  drift_ok=EXCLUDED.drift_ok, purged=EXCLUDED.purged, error=EXCLUDED.error,
  verified_at=now()
"""


def _status(r: DealerHarvestResult) -> str:
    if r.error:
        return "timeout" if r.error == "per_dealer_timeout" else "error"
    if r.yields_inventory and r.persisted > 0:
        return "yielded"
    if (r.web_type or "none") in ("none", "", "timeout"):
        return "no_web"
    return "no_inventory"


async def _record(pg, r: DealerHarvestResult) -> None:
    recipe = getattr(r, "web_type", None)
    async with pg.acquire() as conn:
        await conn.execute(
            _UPSERT_LEDGER, r.domain, (r.country or "").upper()[:2], _status(r),
            r.web_type, getattr(r, "discovery", None), int(r.discovered or 0),
            int(r.persisted or 0), recipe, bool(getattr(r, "drift_ok", False)),
            bool(getattr(r, "purged", False)), r.error,
        )


async def _process_batch(pg, rdb, batch: list[tuple[str, str]]) -> dict:
    """Run one country-homogeneous-ish batch end-to-end; one browser reused per batch."""
    batch.sort(key=lambda dc: dc[1])
    locale = _LOCALE.get(batch[0][1], "en-US")
    purger = make_live_purger(pg)
    counts = {"yielded": 0, "no_inventory": 0, "no_web": 0, "error": 0, "timeout": 0, "inventory": 0}
    static = hv.make_dealer_fetcher()
    e07 = None
    try:
        e07 = PlaywrightFetcher(locale=locale)
        await e07.__aenter__()
        seam = make_live_seam(rdb, static, e07, redis_url=_THROWAWAY_REDIS, db_url=_DB_URL, isolate=True)
        remediator = make_remediator(static_fetcher=static, e07_fetcher=e07,
                                     seam_runner=seam, purger=purger, limit=_LIMIT)
        for domain, country in batch:
            t0 = time.time()
            try:
                r = await asyncio.wait_for(
                    harvest_dealer(domain, country, static_fetcher=static, e07_fetcher=e07,
                                   seam_runner=seam, purger=purger, limit=_LIMIT,
                                   discovery_cap=5000, remediator=remediator),
                    timeout=_PER_DEALER_TIMEOUT,
                )
            except asyncio.TimeoutError:
                r = DealerHarvestResult(domain, country.upper()[:2], "timeout", "none",
                                        0, 0, 0, False, error="per_dealer_timeout")
            await _record(pg, r)
            st = _status(r)
            counts[st] = counts.get(st, 0) + 1
            counts["inventory"] += int(r.persisted or 0)
            print(f"  {domain:<36} {st:<13} inv={r.persisted:<4} disc={r.discovered:<4} "
                  f"({time.time()-t0:.0f}s)" + (f" ERR={r.error}" if r.error else ""))
    finally:
        if e07 is not None:
            await e07.__aexit__(None, None, None)
        aclose = getattr(static, "aclose", None)
        if aclose:
            await aclose()
        static = e07 = None
        hv.free_batch_memory()
    return counts


async def grind(max_batches: int) -> None:
    pg = await indexer.make_pg(_DB_URL)
    rdb = aioredis.from_url(_THROWAWAY_REDIS, decode_responses=True)
    try:
        async with pg.acquire() as conn:
            await conn.execute(_LEDGER_DDL)
            total = await conn.fetchval(
                "SELECT count(*) FROM discovery_candidates WHERE domain IS NOT NULL AND domain <> ''")
        batch_no = 0
        t_start = time.time()
        while max_batches == 0 or batch_no < max_batches:
            async with pg.acquire() as conn:
                rows = await conn.fetch(_NEXT_BATCH_SQL, _BATCH)
            if not rows:
                print("GRIND: no undone entities left — coverage complete for current discovery set")
                break
            batch_no += 1
            batch = [(r["domain"], r["country"]) for r in rows]
            print(f"\n== batch {batch_no} ({len(batch)} entities) ==")
            await _process_batch(pg, rdb, batch)
            async with pg.acquire() as conn:
                done = await conn.fetchval("SELECT count(*) FROM coverage_ledger")
                yielded = await conn.fetchval("SELECT count(*) FROM coverage_ledger WHERE status='yielded'")
                inv = await conn.fetchval("SELECT coalesce(sum(inventory_count),0) FROM coverage_ledger")
            print(f"  LEDGER: {done}/{total} processed ({100*done/max(1,total):.2f}%) | "
                  f"yielded={yielded} | verified_inventory_seen={inv} | {time.time()-t_start:.0f}s")
    finally:
        await rdb.aclose()
        await pg.close()


def main() -> None:
    import logging
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "WARNING").upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Resumable per-entity E2E coverage grind")
    ap.add_argument("--max-batches", type=int, default=0, help="0 = until done")
    asyncio.run(grind(ap.parse_args().max_batches))


if __name__ == "__main__":
    main()
