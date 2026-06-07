"""
E07 end-to-end seam check on a real JS/SPA portal (the static seam yields 0 here).

    vehicle_index pointers (real SPA URLs)
      → seed stream:enrich_pending {h,u,s,c}
      → enrich_worker A6 with a PlaywrightFetcher (config routes the SPA source to E07)
      → stream:ingestion_raw → rich_consumer A7 → vehicles
      → verify rich rows, then PURGE by exact URL (validate-with-a-limit-and-purge)

The source's ``configs/portals/<domain>.json`` must select an E07 strategy
(``playwright_meta``) for A6 to render it; otherwise it stays on the static path.

    docker run -d --rm -p 56390:6379 --name cardex-redis-throwaway redis:7-alpine
    FX_RATE_CHF=1.05 python -m scripts.verify_seam_e07 --domain autolina.ch --country CH --limit 3
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
from scrapers.pipeline.playwright_extractor import PlaywrightFetcher  # noqa: E402

_DB_URL = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_THROWAWAY_REDIS = os.environ.get("THROWAWAY_REDIS_URL", "redis://localhost:56390")


async def _noop_static(url: str):
    """Static fetcher placeholder — the SPA source routes to E07, not here."""
    from scrapers.pipeline.generic_extractor import FetchResult
    return FetchResult(url=url, status_code=404, body=b"")


async def run(domain: str, country: str, limit: int) -> int:
    pg = await indexer.make_pg(_DB_URL)
    rdb = aioredis.from_url(_THROWAWAY_REDIS, decode_responses=True)
    try:
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
        for url in urls:
            await rdb.xadd(a6.ENRICH_STREAM, {
                "h": indexer.url_hash(url), "u": url, "s": domain, "c": country,
            })
        print(f"seeded enrich_pending = {await rdb.xlen(a6.ENRICH_STREAM)}")

        # A6 with E07: PlaywrightFetcher renders; config routes the SPA source to it.
        async with PlaywrightFetcher(locale="de-CH" if country == "CH" else "en-US") as e07:
            s6 = await a6.run(
                redis_url=_THROWAWAY_REDIS, fetcher=_noop_static, e07_fetcher=e07,
                limit=limit, batch_size=limit, block_ms=2000, concurrency=2,
                default_country=country, reclaim_idle_ms=10_000,
            )
        print(f"A6(E07) emitted={s6.emitted} dlq={s6.dlq} transient={s6.transient} "
              f"| ingestion_raw = {await rdb.xlen(a6.INGESTION_STREAM)}")

        s7 = await a7.run(database_url=_DB_URL, redis_url=_THROWAWAY_REDIS,
                          limit=limit, batch_size=limit, block_ms=2000)
        async with pg.acquire() as conn:
            after = await conn.fetchval("SELECT count(*) FROM vehicles")
            sample = await conn.fetch(
                "SELECT make, model, year, price_raw, currency_raw, gross_physical_cost_eur "
                "FROM vehicles WHERE source_url = ANY($1::text[])", urls,
            )
        print(f"A7 persisted={s7.persisted} rejected={s7.rejected} errors={s7.errors}")
        print(f"vehicles {before} -> {after} (delta=+{after - before})")
        for r in sample:
            print(f"  ficha: {r['make']} {r['model']} {r['year']} "
                  f"{r['price_raw']} {r['currency_raw']} -> EUR {r['gross_physical_cost_eur']}")

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
    ap.add_argument("--domain", default="autolina.ch")
    ap.add_argument("--country", default="CH")
    ap.add_argument("--limit", type=int, default=3)
    args = ap.parse_args()
    raise SystemExit(asyncio.run(run(args.domain, args.country, args.limit)))


if __name__ == "__main__":
    main()
