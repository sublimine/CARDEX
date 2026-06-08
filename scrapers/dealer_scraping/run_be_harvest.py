"""Stage 3 — harvest BE dealers' COMPLETE inventory and cage in the live API.

Belgium-only (country='BE'), sequential, RAM-safe. Re-harvests every BE T2 dealer with a high
cap so the FULL inventory (not a 20-sample) is caged as pointers; enriches a sample with JSON-LD
for price/year. The host OOM-killed the API once under a conc-40 harvest — so this runs at LOW
concurrency with a RAM guard that skips remaining dealers before it can starve a sibling service.
Validate-and-purge: the fetched HTML is dropped per dealer; the pointers stay.

    DATABASE_URL=... REDIS_URL=redis://localhost:56390 \
    python -m scrapers.dealer_scraping.run_be_harvest [--conc 4] [--cap 1500] [--country BE]
"""
from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import logging
import os
import time

import asyncpg
import redis.asyncio as aioredis

from scrapers.dealer_scraping.inventory_harvester import harvest_t2_dealer
from scrapers.dealer_scraping.inventory_probe import IN_SCOPE_SQL

log = logging.getLogger("be_harvest")
PG_DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:56390")
RAM_ABORT_MB = 520     # below this: stop launching new dealers (protect the API/delta_worker)


def _avail_mb() -> int:
    class M(ctypes.Structure):
        _fields_ = [("l", ctypes.c_ulong), ("ld", ctypes.c_ulong), ("a", ctypes.c_ulonglong),
                    ("ap", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong), ("c", ctypes.c_ulonglong),
                    ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong), ("f", ctypes.c_ulonglong)]
    m = M(); m.l = ctypes.sizeof(M)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return int(m.ap // 1024 // 1024)


async def run(*, country: str, conc: int, cap: int, sample: int) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    pg = await asyncpg.create_pool(PG_DSN, min_size=2, max_size=6)
    rdb = aioredis.from_url(REDIS_URL, decode_responses=False)
    try:
        rows = await pg.fetch(
            f"SELECT domain, country FROM discovery_candidates "
            f"WHERE country=$1 AND inventory_tier='T2' AND domain IS NOT NULL AND domain<>'' "
            f"AND {IN_SCOPE_SQL} ORDER BY md5(domain)", country)
        log.info("harvesting %d %s T2 dealers (conc=%d, cap=%d) — COMPLETE inventory", len(rows), country, conc, cap)

        sem = asyncio.Semaphore(conc)
        results: list[dict] = []
        skipped = 0
        done = 0

        async def one(d: str, c: str) -> None:
            nonlocal skipped, done
            if _avail_mb() < RAM_ABORT_MB:           # RAM guard: never starve a sibling service
                skipped += 1
                return
            async with sem:
                r = await harvest_t2_dealer(pg, rdb, d, c, sample_limit=sample, cap=cap)
                results.append(r)
                done += 1
                if r.get("new") or done % 10 == 0:
                    log.info("[%d/%d] %s disc=%d new=%d enr=%d RAM=%dMB",
                             done, len(rows), d, r.get("discovered", 0), r.get("new", 0),
                             r.get("enriched", 0), _avail_mb())

        await asyncio.gather(*(one(r["domain"], r["country"]) for r in rows))

        ok = [r for r in results if r.get("yields")]
        total_new = sum(r.get("new", 0) for r in results)
        print(f"\n===== BE HARVEST (COMPLETE) =====")
        print(f"dealers_processed={len(results)} skipped_for_ram={skipped} yielding={len(ok)} "
              f"pointers_caged_new={total_new}")
        top = sorted(ok, key=lambda r: r.get("discovered", 0), reverse=True)[:8]
        print("top:", json.dumps([{"d": r["domain"], "disc": r["discovered"], "new": r["new"],
                                   "enr": r["enriched"], "m": r["method"]} for r in top]))
    finally:
        await rdb.aclose()
        await pg.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="BE")
    ap.add_argument("--conc", type=int, default=4)
    ap.add_argument("--cap", type=int, default=1500)
    ap.add_argument("--sample", type=int, default=25)
    a = ap.parse_args()
    asyncio.run(run(country=a.country, conc=a.conc, cap=a.cap, sample=a.sample))
