"""
NL dealer inventory vertical — end-to-end on a single real dealer domain.

This wires the long-dead dealer path (blueprint P2-1: ``dealer_inventory=0``,
``generic_extractor`` complete-but-never-invoked) all the way to L2:

    dealer domain
      → generic_extractor.discover_listing_urls   (A4 dealer-path, engine fetch)
      → seed stream:enrich_pending {h,u,s,c}        (L1 pointer contract, C5)
      → enrich_worker (A6)  → stream:ingestion_raw  (C7)
      → rich_consumer (A7)  → vehicles (L2)         (C8) + meili_sync
      → verify rich rows, then PURGE by exact URL   (validate-with-a-limit-and-purge)

The same anti-detection engine that harvests portals fetches the dealer pages, so
this is the real dealer chain, not a mock. Throwaway Redis isolates the test from
production streams.

    docker run -d --rm -p 56390:6379 --name cardex-redis-throwaway redis:7-alpine
    python -m scripts.verify_dealer_vertical --domain munsterhuis.nl --country NL --limit 5
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis.asyncio as aioredis  # noqa: E402

from scrapers import enrich_worker as a6  # noqa: E402
from scrapers import rich_consumer as a7  # noqa: E402
from scrapers.common import indexer  # noqa: E402
from scrapers.pipeline import generic_extractor as ge  # noqa: E402

_DB_URL = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_THROWAWAY_REDIS = os.environ.get("THROWAWAY_REDIS_URL", "redis://localhost:56390")


async def run(domain: str, country: str, limit: int) -> int:
    pg = await indexer.make_pg(_DB_URL)
    rdb = aioredis.from_url(_THROWAWAY_REDIS, decode_responses=True)
    fetcher = a6.make_engine_fetcher(default_country=country)
    base_url = f"https://{domain}/"
    try:
        async with pg.acquire() as conn:
            before = await conn.fetchval("SELECT count(*) FROM vehicles")

        # 1. A4 dealer-path: discover this dealer's listing URLs via the engine.
        a6._enrich_country.set(country)  # identity selection for the engine fetcher
        urls = await ge.discover_listing_urls(base_url, fetcher, max_urls=limit)
        urls = urls[:limit]
        print(f"discover_listing_urls({domain}) = {len(urls)}")
        for u in urls[:5]:
            print(f"  url: {u}")
        if not urls:
            print(f"RESULT: 0 listing URLs discovered for {domain} "
                  f"(no vehicle sitemap / WP-REST CPT) — try another dealer")
            return 3

        # 2. seed enrich_pending exactly as indexer.py does ({h,u,s,c})
        for s in (a6.ENRICH_STREAM, a6.INGESTION_STREAM):
            await rdb.delete(s)
        for url in urls:
            await rdb.xadd(a6.ENRICH_STREAM, {
                "h": indexer.url_hash(url), "u": url, "s": domain, "c": country,
            })
        print(f"seeded enrich_pending = {await rdb.xlen(a6.ENRICH_STREAM)}")

        # 3. A6: enrich_pending → ingestion_raw (engine fetch + parse each detail)
        s6 = await a6.run(
            redis_url=_THROWAWAY_REDIS, fetcher=fetcher,
            limit=len(urls), batch_size=len(urls), block_ms=2000,
            concurrency=4, default_country=country,
        )
        print(f"A6 emitted={s6.emitted} dlq={s6.dlq} transient={s6.transient} "
              f"| ingestion_raw = {await rdb.xlen(a6.INGESTION_STREAM)}")

        # 4. A7: ingestion_raw → vehicles
        s7 = await a7.run(
            database_url=_DB_URL, redis_url=_THROWAWAY_REDIS,
            limit=len(urls), batch_size=len(urls), block_ms=2000,
        )
        async with pg.acquire() as conn:
            after = await conn.fetchval("SELECT count(*) FROM vehicles")
            sample = await conn.fetch(
                "SELECT make, model, year, gross_physical_cost_eur, source_platform "
                "FROM vehicles WHERE source_url = ANY($1::text[])", urls,
            )
        print(f"A7 persisted={s7.persisted} rejected={s7.rejected} errors={s7.errors} "
              f"| meili_sync = {await rdb.xlen(a7.MEILI_SYNC_STREAM)}")
        print(f"vehicles {before} -> {after} (delta=+{after - before})")
        for r in sample:
            print(f"  row: {r['make']} {r['model']} {r['year']} "
                  f"eur={r['gross_physical_cost_eur']} platform={r['source_platform']}")

        # 5. PURGE by EXACT url (H2) — local is a test bench, not a store
        async with pg.acquire() as conn:
            await conn.execute("DELETE FROM vehicles WHERE source_url = ANY($1::text[])", urls)
            final = await conn.fetchval("SELECT count(*) FROM vehicles")
        print(f"PURGED; vehicles FINAL = {final} ({'restored' if final == before else 'MISMATCH'})")
        return 0 if s7.persisted > 0 and final == before else 1
    finally:
        await rdb.aclose()
        await pg.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", required=True)
    ap.add_argument("--country", default="NL")
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()
    raise SystemExit(asyncio.run(run(args.domain, args.country, args.limit)))


if __name__ == "__main__":
    main()
