"""
Seam verification harness — proves L1 → L2 grows `vehicles` from REAL listings,
then purges (validate-with-a-limit-and-purge; the local disk is a test bench).

Flow (no Redis required — calls the tested A6/A7 functions directly):
  1. read N real listing URLs from vehicle_index for a clean portal
  2. A6 enrich_one  : engine-fetch each URL → parse → vehiclePayload (C7, H1)
  3. A7 persist_one : vehiclePayload → INSERT vehicles (live PG)
  4. report vehicles count before/after
  5. PURGE by EXACT source_url equality (H2 — never LIKE)

Usage:
  python -m scripts.verify_seam --domain gaspedaal.nl --country NL --limit 3
  python -m scripts.verify_seam --domain gaspedaal.nl --limit 3 --no-purge
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

# ensure repo root on path so `scrapers.*` imports resolve when run as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.common import indexer  # noqa: E402
from scrapers.enrich_worker import enrich_one, make_engine_fetcher  # noqa: E402
from scrapers.pipeline import fx_eur  # noqa: E402
from scrapers.rich_consumer import persist_one  # noqa: E402

_DB_URL = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")


async def _count(pool) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT count(*) FROM vehicles")


async def run(domain: str, country: str, limit: int, purge: bool) -> int:
    pool = await indexer.make_pg(_DB_URL)
    rates = fx_eur.load_rates_from_env()
    fetcher = make_engine_fetcher()
    inserted_urls: list[str] = []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT url_original FROM vehicle_index "
                "WHERE source_domain=$1 AND country=$2 LIMIT $3",
                domain, country, limit,
            )
        urls = [r["url_original"] for r in rows]
        if not urls:
            print(f"FATAL: no vehicle_index rows for {domain}/{country}")
            return 2

        before = await _count(pool)
        print(f"vehicles BEFORE = {before}")
        print(f"enriching {len(urls)} real {domain} listings (limit={limit}) ...")

        ok = fetched_fail = persist_fail = 0
        for url in urls:
            fields = {"h": indexer.url_hash(url), "u": url, "s": domain, "c": country}
            payload, reason = await enrich_one(fields, fetcher, default_country=country)
            if payload is None:
                fetched_fail += 1
                print(f"  enrich FAIL  {url}  reason={reason}")
                continue
            result, preason = await persist_one(
                pool, payload, source=domain, channel="SCRAPER", rates=rates
            )
            if result is None:
                persist_fail += 1
                print(f"  persist FAIL {url}  reason={preason}")
                continue
            ok += 1
            inserted_urls.append(payload["source_url"])
            print(f"  OK  ulid={result.ulid} insert={result.is_insert} eur={result.eur} "
                  f"make={payload['make']} model={payload['model']} year={payload['year']}")

        after = await _count(pool)
        print(f"vehicles AFTER  = {after}  (delta=+{after - before}; "
              f"ok={ok} enrich_fail={fetched_fail} persist_fail={persist_fail})")

        if purge and inserted_urls:
            async with pool.acquire() as conn:
                # H2: EXACT-equality purge of only the URLs we inserted. Never LIKE.
                deleted = await conn.execute(
                    "DELETE FROM vehicles WHERE source_url = ANY($1::text[])", inserted_urls
                )
            final = await _count(pool)
            print(f"PURGED {deleted}; vehicles FINAL = {final} "
                  f"({'restored to baseline' if final == before else 'MISMATCH'})")
        elif not purge:
            print("purge skipped (--no-purge); rows left in vehicles")
        return 0 if ok > 0 else 1
    finally:
        await pool.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="gaspedaal.nl")
    ap.add_argument("--country", default="NL")
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--no-purge", dest="purge", action="store_false")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(run(args.domain, args.country, args.limit, args.purge)))


if __name__ == "__main__":
    main()
