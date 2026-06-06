"""
Full Redis-transport seam check: enrich_pending → A6.run → ingestion_raw →
A7.run → vehicles, over a real Redis (throwaway), with real listings, then purge.

This complements verify_seam.py (which calls the functions directly): here the
actual consumer-group plumbing (XADD / XREADGROUP / XACK) is exercised end to end.

    docker run -d --name cardex-redis-throwaway -p 56390:6379 redis:7-alpine
    python -m scripts.verify_seam_redis --domain autotrack.nl --country NL --limit 2
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis.asyncio as aioredis  # noqa: E402

from scrapers import db  # noqa: E402
from scrapers import enrich_worker as a6  # noqa: E402
from scrapers import rich_consumer as a7  # noqa: E402
from scrapers.common import indexer  # noqa: E402
from scrapers.intelligence import drift_gate  # noqa: E402
from scrapers.portals import config as portal_config  # noqa: E402

_DB_URL = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_THROWAWAY_REDIS = os.environ.get("THROWAWAY_REDIS_URL", "redis://localhost:56390")


async def run(domain: str, country: str, limit: int) -> int:
    pg = await indexer.make_pg(_DB_URL)
    rdb = aioredis.from_url(_THROWAWAY_REDIS, decode_responses=True)
    try:
        # 0. pull real pointers + reset throwaway streams
        async with pg.acquire() as conn:
            rows = await conn.fetch(
                "SELECT url_original FROM vehicle_index WHERE source_domain=$1 AND country=$2 LIMIT $3",
                domain, country, limit,
            )
            before = await conn.fetchval("SELECT count(*) FROM vehicles")
        urls = [r["url_original"] for r in rows]
        if not urls:
            print(f"FATAL: no pointers for {domain}/{country}")
            return 2
        for s in (a6.ENRICH_STREAM, a6.INGESTION_STREAM):
            await rdb.delete(s)

        # 1. seed enrich_pending exactly as indexer.py does ({h,u,s,c})
        for url in urls:
            await rdb.xadd(a6.ENRICH_STREAM, {
                "h": indexer.url_hash(url), "u": url, "s": domain, "c": country,
            })
        print(f"seeded enrich_pending = {await rdb.xlen(a6.ENRICH_STREAM)}")

        # 2. A6: enrich_pending → ingestion_raw (real engine fetch)
        s6 = await a6.run(
            redis_url=_THROWAWAY_REDIS, fetcher=a6.make_engine_fetcher(default_country=country),
            limit=limit, batch_size=limit, block_ms=2000, concurrency=4, default_country=country,
        )
        print(f"A6 emitted={s6.emitted} dlq={s6.dlq} transient={s6.transient} "
              f"| ingestion_raw depth = {await rdb.xlen(a6.INGESTION_STREAM)}")

        # 3. A7: ingestion_raw → vehicles (live PG)
        s7 = await a7.run(
            database_url=_DB_URL, redis_url=_THROWAWAY_REDIS,
            limit=limit, batch_size=limit, block_ms=2000,
        )
        async with pg.acquire() as conn:
            after = await conn.fetchval("SELECT count(*) FROM vehicles")
        meili_depth = await rdb.xlen(a7.MEILI_SYNC_STREAM)
        print(f"A7 persisted={s7.persisted} rejected={s7.rejected} errors={s7.errors} "
              f"| meili_sync depth = {meili_depth}")
        print(f"vehicles {before} -> {after} (delta=+{after - before})")

        # 4. inspect a persisted row (proof of richness) then purge by EXACT url (H2)
        async with pg.acquire() as conn:
            sample = await conn.fetch(
                "SELECT make, model, year, gross_physical_cost_eur, source_id, source_platform "
                "FROM vehicles WHERE source_url = ANY($1::text[])", urls,
            )
            for r in sample:
                print(f"  row: {r['make']} {r['model']} {r['year']} "
                      f"eur={r['gross_physical_cost_eur']} source_id={r['source_id'][:12]}… "
                      f"platform={r['source_platform']}")

            # 4b. DRIFT GATE (anti-breakage hook) — score this harvest against the
            # source's versioned config baseline; alert by source if it deviates.
            cfg = portal_config.load(domain)
            if cfg is not None:
                records = [
                    {"make": r["make"], "model": r["model"], "year": r["year"],
                     "price": r["gross_physical_cost_eur"],
                     "images": ["x"] if r["make"] else []}
                    for r in sample
                ]
                stats = drift_gate.stats_from_records(records, cfg.drift_baseline.required_fields)
                eng = db.connect(os.environ.get("ENGINE_DB_PATH", "scrapers/engine.db"))
                db.migrate(eng)
                report = drift_gate.evaluate(cfg, stats, conn=eng)
                eng.commit(); eng.close()
                print(f"DRIFT GATE [{domain}]: {'OK' if report.ok else 'ALERT'} — {report.reason()}")
            else:
                print(f"DRIFT GATE [{domain}]: no config (add configs/portals/{domain}.json)")

            deleted = await conn.execute("DELETE FROM vehicles WHERE source_url = ANY($1::text[])", urls)
            final = await conn.fetchval("SELECT count(*) FROM vehicles")
        print(f"PURGED {deleted}; vehicles FINAL = {final} "
              f"({'restored' if final == before else 'MISMATCH'})")
        return 0 if s7.persisted > 0 and final == before else 1
    finally:
        await rdb.aclose()
        await pg.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="autotrack.nl")
    ap.add_argument("--country", default="NL")
    ap.add_argument("--limit", type=int, default=2)
    args = ap.parse_args()
    raise SystemExit(asyncio.run(run(args.domain, args.country, args.limit)))


if __name__ == "__main__":
    main()
