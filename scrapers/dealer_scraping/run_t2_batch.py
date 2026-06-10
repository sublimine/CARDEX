"""Batch runner — harvest every inventory_tier='T2' dealer into the live API.

HTTP-only, RAM-light (concurrency 15, per-domain curl_cffi sessions, streamed + GC'd per
dealer). Writes pointers to the canonical Postgres so the persistent entity API reflects
them immediately. Run:

    DATABASE_URL=postgresql://cardex:cardex_dev_only@localhost:5432/cardex \
    REDIS_URL=redis://localhost:56390 \
    python -m scrapers.dealer_scraping.run_t2_batch [limit]
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import asyncpg
import redis.asyncio as aioredis

from scrapers.dealer_scraping.inventory_harvester import harvest_t2_dealer
from scrapers.dealer_scraping.inventory_probe import IN_SCOPE_SQL

log = logging.getLogger("t2_batch")
PG_DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:56390")


async def run(*, concurrency: int = 15, limit: int = 0, cap: int = 0, country: str | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    pg = await asyncpg.create_pool(PG_DSN, min_size=2, max_size=8)
    rdb = aioredis.from_url(REDIS_URL, decode_responses=False)
    try:
        q = ("SELECT domain, country, "
             "       COALESCE(inventory_signals->>'cms','') AS cms, "
             "       COALESCE(inventory_signals->>'cms_confidence','') AS cms_confidence "
             "FROM discovery_candidates "
             "WHERE inventory_tier='T2' AND domain IS NOT NULL AND domain<>'' "
             f"AND {IN_SCOPE_SQL} ")
        args: list = []
        if country:
            q += "AND country=$1 "
            args.append(country.upper()[:2])
        q += "ORDER BY country, md5(domain)"
        if limit:
            q += f" LIMIT {limit}"
        rows = await pg.fetch(q, *args)
        log.info("harvesting %d T2 dealers (concurrency=%d)", len(rows), concurrency)

        sem = asyncio.Semaphore(concurrency)
        results: list[dict] = []
        done = 0

        async def one(d: str, c: str, cms: str, conf: str) -> None:
            nonlocal done
            async with sem:
                kw = {"cms": cms, "cms_confidence": conf}
                if cap:
                    kw["cap"] = cap
                r = await harvest_t2_dealer(pg, rdb, d, c, **kw)
                results.append(r)
                done += 1
                if r.get("new") or done % 10 == 0:
                    log.info("[%d/%d] %s %-28s disc=%d new=%d enr=%d %s",
                             done, len(rows), r["country"], r["domain"],
                             r.get("discovered", 0), r.get("new", 0), r.get("enriched", 0),
                             r.get("method", r.get("error", "")))

        await asyncio.gather(*(one(r["domain"], r["country"], r["cms"], r["cms_confidence"])
                               for r in rows))

        ok = [r for r in results if r.get("yields")]
        total_new = sum(r.get("new", 0) for r in results)
        total_disc = sum(r.get("discovered", 0) for r in results)
        errs = [r for r in results if r.get("error")]
        by_country: dict[str, dict] = {}
        for r in results:
            b = by_country.setdefault(r["country"], {"dealers": 0, "yielding": 0, "caged": 0})
            b["dealers"] += 1
            b["yielding"] += int(bool(r.get("yields")))
            b["caged"] += r.get("new", 0)

        print("\n===== T2 HARVEST BATCH RESULT =====")
        print(f"dealers={len(results)}  yielding={len(ok)}  "
              f"success_rate={round(len(ok)/len(results), 3) if results else 0}")
        print(f"pointers_caged_new={total_new}  discovered_total={total_disc}  errors={len(errs)}")
        print("by_country:", json.dumps(by_country))
        top = sorted(ok, key=lambda r: r.get("new", 0), reverse=True)[:8]
        print("top_dealers:", json.dumps(
            [{"domain": r["domain"], "country": r["country"], "new": r["new"],
              "enriched": r["enriched"], "method": r["method"]} for r in top]))
    finally:
        await rdb.aclose()
        await pg.close()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("limit", type=int, nargs="?", default=0, help="max dealers (0 = all)")
    ap.add_argument("--conc", type=int, default=15)
    ap.add_argument("--cap", type=int, default=0,
                    help="detail URLs caged per dealer (0 = module default; raise for "
                         "family-recipe platforms whose full sitemap should be caged)")
    ap.add_argument("--country", default=None, help="scope to one country (e.g. NL)")
    a = ap.parse_args()
    asyncio.run(run(concurrency=a.conc, limit=a.limit, cap=a.cap, country=a.country))
