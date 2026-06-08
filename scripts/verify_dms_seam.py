"""
E2E proof that the DMS/XHR vector reaches `vehicles` (frente C).

Renders a known DMS/widget dealer's catalog, captures the inventory feed XHR, builds
records, pushes them through the SAME rich-persist seam (A7) the static path uses
(record -> vehiclePayload via enrich_worker.record_to_payload -> stream:ingestion_raw ->
rich_consumer -> vehicles), verifies the rows, then PURGES by exact source_url.

    docker run -d --rm -p 56390:6379 --name cardex-redis-throwaway redis:7-alpine
    python -m scripts.verify_dms_seam --domain kuehl.seat.de --url https://kuehl.seat.de/gebrauchtwagen --country DE
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis.asyncio as aioredis  # noqa: E402

from scrapers import enrich_worker as a6  # noqa: E402
from scrapers import rich_consumer as a7  # noqa: E402
from scrapers.common import indexer  # noqa: E402
from scrapers.dealer_scraping.dms_connector import harvest_inventory_xhr  # noqa: E402
from scrapers.pipeline.playwright_xhr import PlaywrightXHRFetcher  # noqa: E402

_DB_URL = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_THROWAWAY_REDIS = os.environ.get("THROWAWAY_REDIS_URL", "redis://localhost:56390")


async def run(domain: str, url: str, country: str, limit: int) -> int:
    pg = await indexer.make_pg(_DB_URL)
    rdb = aioredis.from_url(_THROWAWAY_REDIS, decode_responses=True)
    try:
        async with PlaywrightXHRFetcher(locale="de-DE" if country == "DE" else "en-US",
                                        settle_ms=8000) as xhr:
            records = await harvest_inventory_xhr(url, xhr, country=country, source_domain=domain)
        records = records[:limit]
        if not records:
            print(f"FATAL: DMS capture yielded no records for {url}")
            return 2
        urls = [r.source_url for r in records]

        await rdb.delete(a6.INGESTION_STREAM)
        for rec in records:
            payload = a6.record_to_payload(rec, source_key=domain, url_hash=indexer.url_hash(rec.source_url))
            await rdb.xadd(a6.INGESTION_STREAM, {"payload": json.dumps(payload, separators=(",", ":")),
                                                 "source": domain, "channel": "SCRAPER"})
        async with pg.acquire() as conn:
            before = await conn.fetchval("SELECT count(*) FROM vehicles")
        print(f"DMS extracted {len(records)} records; seeded ingestion_raw={await rdb.xlen(a6.INGESTION_STREAM)}")

        s7 = await a7.run(database_url=_DB_URL, redis_url=_THROWAWAY_REDIS,
                          limit=len(records), batch_size=len(records), block_ms=2000)
        async with pg.acquire() as conn:
            after = await conn.fetchval("SELECT count(*) FROM vehicles")
            sample = await conn.fetch(
                "SELECT make, model, year, price_raw, currency_raw, gross_physical_cost_eur "
                "FROM vehicles WHERE source_url = ANY($1::text[])", urls)
        print(f"A7 persisted={s7.persisted} rejected={s7.rejected} | vehicles {before}->{after}")
        for r in sample:
            print(f"  ficha(DMS): {r['make']} {r['model']} {r['year']} {r['price_raw']}"
                  f"{r['currency_raw']} -> EUR {r['gross_physical_cost_eur']}")

        async with pg.acquire() as conn:
            await conn.execute("DELETE FROM vehicles WHERE source_url = ANY($1::text[])", urls)
            final = await conn.fetchval("SELECT count(*) FROM vehicles")
        print(f"PURGED; vehicles FINAL={final} ({'restored' if final == before else 'MISMATCH'})")
        return 0 if s7.persisted > 0 and final == before else 1
    finally:
        await rdb.aclose()
        await pg.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="kuehl.seat.de")
    ap.add_argument("--url", default="https://kuehl.seat.de/gebrauchtwagen")
    ap.add_argument("--country", default="DE")
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()
    raise SystemExit(asyncio.run(run(args.domain, args.url, args.country, args.limit)))


if __name__ == "__main__":
    main()
