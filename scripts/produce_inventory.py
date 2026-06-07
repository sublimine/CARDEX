"""
PRODUCE real car inventory into `vehicles` (frente C) — persist, do NOT purge.

Unlike the measurement harness (validate-with-a-limit-and-purge), this PRODUCES: it
harvests dealers WITH web, prioritizing brand/group segments, and persists every record
(static detail extraction + DMS/widget XHR feed) to `vehicles` via the seam (A7), leaving
it in place so a live `SELECT count(*) FROM vehicles` grows. Bounded by a global cap so
the local disk never fills (the full per-dealer dump is the VPS's job).

RAM-safe: ONE curl_cffi fetcher + ONE Playwright XHR browser per batch (closed between
batches), md5-paged cursor, gc between batches, E07 concurrency 1 (sequential per dealer).

    docker run -d --rm -p 56390:6379 --name cardex-redis-throwaway redis:7-alpine
    python -m scripts.produce_inventory --per-segment 6 --limit 20 --max-cars 4000
"""
from __future__ import annotations

import argparse
import asyncio
import gc
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis.asyncio as aioredis  # noqa: E402

from scrapers import enrich_worker as a6  # noqa: E402
from scrapers import rich_consumer as a7  # noqa: E402
from scrapers.common import indexer  # noqa: E402
from scrapers.dealer_scraping import harvester as hv  # noqa: E402
from scrapers.dealer_scraping.discovery import discover_detail_urls  # noqa: E402
from scrapers.dealer_scraping.dms_connector import harvest_inventory_multi  # noqa: E402
from scrapers.pipeline.generic_extractor import extract_listing  # noqa: E402
from scrapers.pipeline.playwright_xhr import PlaywrightXHRFetcher  # noqa: E402
from scripts.run_dealer_scraping import _LOCALE  # noqa: E402

_DB_URL = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_THROWAWAY_REDIS = os.environ.get("THROWAWAY_REDIS_URL", "redis://localhost:56390")
_TIMEOUT = float(os.environ.get("DEALER_TIMEOUT_S", "90"))

# Ordered by PROVEN yield: VW Group SEAT (DMS/XHR), brand .com (static), dealer
# associations — so production starts fast, then the rest.
_SEGMENTS = ("oem:seat", "oem:audi", "bovag", "oem:vw", "oem:renault",
             "oem:dacia", "oem:hyundai", "agvs", "gelbeseiten")


async def _sample(conn, source_like, n):
    rows = await conn.fetch(
        "SELECT domain, country FROM discovery_candidates "
        "WHERE source ILIKE $1 AND domain IS NOT NULL AND domain<>'' ORDER BY md5(domain) LIMIT $2",
        source_like, n)
    return [(r["domain"], r["country"]) for r in rows]


async def _persist(records, rdb, domain) -> int:
    """Push records through the seam (A7) into `vehicles` — no purge."""
    if not records:
        return 0
    await rdb.delete(a6.INGESTION_STREAM)
    for rec in records:
        payload = a6.record_to_payload(rec, source_key=domain, url_hash=indexer.url_hash(rec.source_url))
        await rdb.xadd(a6.INGESTION_STREAM, {"payload": json.dumps(payload, separators=(",", ":")),
                                             "source": domain, "channel": "SCRAPER"})
    s7 = await a7.run(database_url=_DB_URL, redis_url=_THROWAWAY_REDIS,
                      limit=len(records), batch_size=len(records), block_ms=1500)
    return s7.persisted


async def _harvest_dealer_records(domain, country, static, e07, limit):
    """Collect VehicleRecords from a dealer: static detail extraction + DMS/widget XHR."""
    records = []
    try:
        details, _m, _h, catalog = await asyncio.wait_for(
            discover_detail_urls(domain, static_fetcher=static, e07_fetcher=e07, cap=limit * 2),
            timeout=50)
    except Exception:  # noqa: BLE001
        details, catalog = [], ""
    for u in details[:limit]:
        try:
            rec, _ = await asyncio.wait_for(
                extract_listing(u, static, country=country, source_domain=domain), timeout=25)
            if rec is not None:
                records.append(rec)
        except Exception:  # noqa: BLE001
            continue
    if not records:  # SPA/widget dealer → capture the embedded inventory feed
        try:
            dms = await asyncio.wait_for(
                harvest_inventory_multi(domain, e07, country=country, catalog_url=catalog or "",
                                        max_tries=2, good_enough=limit), timeout=_TIMEOUT * 2)
            records.extend(dms[:limit])
        except Exception:  # noqa: BLE001
            pass
    return records


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


async def run(*, per_segment, limit, max_cars, batch_size) -> dict:
    pg = await indexer.make_pg(_DB_URL)
    rdb = aioredis.from_url(_THROWAWAY_REDIS, decode_responses=True)
    started = time.time()
    work = []
    produced = 0
    yielding = 0
    try:
        async with pg.acquire() as conn:
            before = await conn.fetchval("SELECT count(*) FROM vehicles")
            for src in _SEGMENTS:
                for dc in await _sample(conn, src, per_segment):
                    work.append((src, dc[0], dc[1]))
        # Keep PROVEN-yield segment order (no country sort) so SEAT/brand produce first.
        print(f"PRODUCE: {len(work)} dealers (proven-yield order); vehicles before={before}; cap={max_cars}",
              flush=True)

        for bi, batch in enumerate(_chunks(work, batch_size)):
            if produced >= max_cars:
                break
            static = hv.make_dealer_fetcher()
            e07 = PlaywrightXHRFetcher(locale=_LOCALE.get(batch[0][2], "en-US"))
            await e07.__aenter__()
            try:
                for src, domain, country in batch:
                    if produced >= max_cars:
                        break
                    t0 = time.time()
                    try:
                        recs = await _harvest_dealer_records(domain, country, static, e07, limit)
                        n = await _persist(recs[:max(0, max_cars - produced)], rdb, domain)
                    except Exception as exc:  # noqa: BLE001
                        recs, n = [], 0
                        print(f"  [{src:<13}] {domain:<30} ERR {type(exc).__name__}", flush=True)
                    produced += n
                    yielding += int(n > 0)
                    if n > 0:
                        print(f"  [{src:<13}] {domain:<30} +{n:<3} cars  "
                              f"(total={produced}) ({time.time()-t0:.0f}s)", flush=True)
            finally:
                await e07.__aexit__(None, None, None)
                ac = getattr(static, "aclose", None)
                if ac:
                    await ac()
                static = e07 = None
                gc.collect()
                async with pg.acquire() as conn:
                    live = await conn.fetchval("SELECT count(*) FROM vehicles")
                print(f"-- batch {bi+1} done · LIVE vehicles={live} · yielding_dealers={yielding} "
                      f"· produced={produced} --", flush=True)

        async with pg.acquire() as conn:
            after = await conn.fetchval("SELECT count(*) FROM vehicles")
        return {"dealers": len(work), "yielding_dealers": yielding, "produced": produced,
                "vehicles_before": before, "vehicles_after": after,
                "elapsed_s": round(time.time() - started, 1)}
    finally:
        await rdb.aclose()
        await pg.close()


def main() -> None:
    import logging
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "ERROR").upper())
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-segment", type=int, default=6)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--max-cars", type=int, default=4000)
    ap.add_argument("--batch-size", type=int, default=8)
    args = ap.parse_args()
    if args.batch_size < 1:
        ap.error("--batch-size must be >= 1")
    agg = asyncio.run(run(per_segment=args.per_segment, limit=args.limit,
                          max_cars=args.max_cars, batch_size=args.batch_size))
    print("\n==================== PRODUCE SUMMARY ====================", flush=True)
    print(f"dealers={agg['dealers']} yielding={agg['yielding_dealers']} "
          f"cars_produced={agg['produced']}", flush=True)
    print(f"vehicles {agg['vehicles_before']} -> {agg['vehicles_after']} "
          f"(KEPT, not purged) elapsed={agg['elapsed_s']}s", flush=True)


if __name__ == "__main__":
    main()
