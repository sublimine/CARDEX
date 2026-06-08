"""Scale loop — probe pending with-web dealers in batches, chain-harvest new T2, report funnel.

RAM-aware (the host kills services under pressure): reads available MB before each batch and
backs off concurrency / pauses if it gets tight; aborts before it can OOM a sibling service.
Resumable across runs — classification is persisted, so each invocation advances over the
remaining ``sitemap_status='pending'`` dealers.

    DATABASE_URL=postgresql://cardex:cardex_dev_only@localhost:5432/cardex \
    REDIS_URL=redis://localhost:56390 \
    python -m scrapers.dealer_scraping.run_probe_scale [--batches N] [--size 1000] [--conc 15]
"""
from __future__ import annotations

import argparse
import asyncio
import ctypes
import gc
import json
import logging
import os
import time

import aiohttp
import asyncpg
import redis.asyncio as aioredis

from scrapers.dealer_scraping.inventory_harvester import harvest_t2_dealer
from scrapers.dealer_scraping.inventory_probe import (IN_SCOPE_SQL, claim_pending_batch,
                                                      run_probes, write_results)

_SCOPE_COUNTRIES = "('ES','FR','DE','BE','NL','CH')"

log = logging.getLogger("probe_scale")
PG_DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:56390")

RAM_SOFT_MB = 750     # below this: drop concurrency (raised — the host OOM-killed the API
RAM_HARD_MB = 550     # at ~585MB; back off MUCH earlier to keep sibling services alive)


def _avail_mb() -> int:
    class M(ctypes.Structure):
        _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("tp", ctypes.c_ulonglong),
                    ("ap", ctypes.c_ulonglong), ("tpf", ctypes.c_ulonglong),
                    ("apf", ctypes.c_ulonglong), ("tv", ctypes.c_ulonglong),
                    ("av", ctypes.c_ulonglong), ("ae", ctypes.c_ulonglong)]
    m = M(); m.l = ctypes.sizeof(M)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return int(m.ap // 1024 // 1024)


async def _funnel(pg) -> dict:
    row = await pg.fetchrow(
        "SELECT count(*) FILTER (WHERE domain IS NOT NULL AND domain<>'') AS with_web, "
        " count(*) FILTER (WHERE inventory_tier IS NOT NULL) AS classified, "
        " count(*) FILTER (WHERE inventory_tier='T2') AS t2, "
        " count(*) FILTER (WHERE inventory_tier='T1') AS t1, "
        " count(*) FILTER (WHERE domain IS NOT NULL AND domain<>'' AND sitemap_status='pending') AS pending "
        f"FROM discovery_candidates WHERE {IN_SCOPE_SQL}")
    caged = await pg.fetchval(
        "SELECT count(*) FROM vehicle_index vi JOIN source_entities se USING(entity_ulid) "
        f"WHERE se.kind='dealer' AND se.country IN {_SCOPE_COUNTRIES}")
    dealers_live = await pg.fetchval(
        f"SELECT count(*) FROM source_entities WHERE kind='dealer' AND country IN {_SCOPE_COUNTRIES}")
    return {**dict(row), "caged_pointers": caged, "dealer_entities": dealers_live}


async def run(*, batches: int, size: int, conc: int, timeout: int, harvest: bool,
              country: str | None = None,
              ram_soft: int = RAM_SOFT_MB, ram_hard: int = RAM_HARD_MB) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    pg = await asyncpg.create_pool(PG_DSN, min_size=2, max_size=8)
    rdb = aioredis.from_url(REDIS_URL, decode_responses=False)
    connector = aiohttp.TCPConnector(limit=conc + 10, ssl=False, ttl_dns_cache=300)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"}
    session = aiohttp.ClientSession(connector=connector, headers=headers)
    cum = {"probed": 0, "t1": 0, "t2": 0, "t3": 0, "dead": 0, "err": 0,
           "harvested": 0, "caged_new": 0}
    t_start = time.monotonic()
    try:
        f0 = await _funnel(pg)
        log.info("START funnel: with_web=%(with_web)d classified=%(classified)d pending=%(pending)d "
                 "T2=%(t2)d caged=%(caged_pointers)d", f0)
        for b in range(1, batches + 1):
            avail = _avail_mb()
            if avail < ram_hard:
                log.warning("RAM HARD %d MB < %d — GC+pause, then abort if still low", avail, ram_hard)
                gc.collect(); await asyncio.sleep(10)
                if _avail_mb() < ram_hard:
                    log.error("RAM still critical — aborting to protect sibling services"); break
            cur_conc = conc if avail >= ram_soft else max(4, conc // 2)
            if cur_conc != conc:
                log.warning("RAM soft %d MB — concurrency %d→%d", avail, conc, cur_conc)

            rows = await claim_pending_batch(pg, size, country)
            if not rows:
                log.info("no pending dealers left — universe exhausted"); break

            t_b = time.monotonic()
            results = await run_probes(session, rows, cur_conc, timeout)
            await write_results(pg, results)
            t1 = [r for r in results if r.tier == "T1"]
            t2 = [r for r in results if r.tier == "T2"]
            t3 = [r for r in results if r.tier == "T3"]
            dead = [r for r in results if r.tier == "DEAD"]
            err = [r for r in results if r.error]
            cum["probed"] += len(results); cum["t1"] += len(t1); cum["t2"] += len(t2)
            cum["t3"] += len(t3); cum["dead"] += len(dead); cum["err"] += len(err)

            caged_new = 0; harvested = 0
            if harvest and t2:
                hsem = asyncio.Semaphore(min(6, cur_conc))
                async def _h(d, c):
                    nonlocal caged_new, harvested
                    async with hsem:
                        hr = await harvest_t2_dealer(pg, rdb, d, c)
                        harvested += 1
                        caged_new += hr.get("new", 0)
                await asyncio.gather(*(_h(r.domain, r.country) for r in t2))
                cum["harvested"] += harvested; cum["caged_new"] += caged_new

            f = await _funnel(pg)
            log.info("TANDA %d | probed=%d (T1=%d T2=%d T3=%d DEAD=%d err=%d) | harvested=%d caged_new=%d "
                     "| %ds | RAM=%dMB", b, len(results), len(t1), len(t2), len(t3), len(dead),
                     len(err), harvested, caged_new, int(time.monotonic() - t_b), avail)
            log.info("FUNNEL acc | with_web=%(with_web)d → classified=%(classified)d → "
                     "T2=%(t2)d (+T1=%(t1)d) → caged_pointers=%(caged_pointers)d "
                     "(dealer_entities=%(dealer_entities)d) | pending=%(pending)d", f)

        # final projection
        f = await _funnel(pg)
        elapsed = time.monotonic() - t_start
        rate = cum["probed"] / elapsed if elapsed else 0
        rem = f["pending"]
        eta_min = int(rem / rate / 60) if rate else 0
        t2_rate = cum["t2"] / cum["probed"] if cum["probed"] else 0
        print("\n===== PROBE-SCALE SESSION =====")
        print(f"probed_this_session={cum['probed']} (T1={cum['t1']} T2={cum['t2']} T3={cum['t3']} "
              f"DEAD={cum['dead']} err={cum['err']})  rate={rate:.1f}/s")
        print(f"harvested={cum['harvested']} caged_new={cum['caged_new']}")
        print("FUNNEL:", json.dumps({k: f[k] for k in
              ('with_web', 'classified', 't2', 't1', 'caged_pointers', 'dealer_entities', 'pending')}))
        print(f"PROJECTION: pending={rem} remaining, T2-rate={t2_rate:.1%} → "
              f"~{int(rem * t2_rate)} more T2; exhaust ETA ~{eta_min} min at {rate:.1f}/s")
    finally:
        await session.close(); await rdb.aclose(); await pg.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=int, default=3)
    ap.add_argument("--size", type=int, default=1000)
    ap.add_argument("--conc", type=int, default=15)
    ap.add_argument("--timeout", type=int, default=15)
    ap.add_argument("--no-harvest", action="store_true")
    ap.add_argument("--country", default=None, help="scope probe to one country (e.g. NL, CH)")
    ap.add_argument("--ram-soft", type=int, default=RAM_SOFT_MB, help="MB free below which conc drops")
    ap.add_argument("--ram-hard", type=int, default=RAM_HARD_MB, help="MB free below which it pauses/aborts")
    a = ap.parse_args()
    asyncio.run(run(batches=a.batches, size=a.size, conc=a.conc, timeout=a.timeout, country=a.country,
                    ram_soft=a.ram_soft, ram_hard=a.ram_hard,
                    harvest=not a.no_harvest))
