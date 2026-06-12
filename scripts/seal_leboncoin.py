"""Seal leboncoin (leboncoin.fr) FR used cars — DataDome surface; proxy-free SUSTAINABILITY probe.

leboncoin.fr/recherche?category=2 is Next.js behind DataDome. A curl_cffi Chrome136 session gets
HTTP 200 with full ``__NEXT_DATA__`` on a cold hit (verified 2026-06-12: searchData.total=781.5k,
35 ads/page via the existing scrapers/portals/leboncoin_listings.py parser). The OPEN QUESTION
(DOSSIER + parser caveat) is whether DataDome challenges under SUSTAINED pagination — so this
connector's ``--sample`` run is the live sustainability test: it paginates and reports the page at
which DataDome first blocks (no ``__NEXT_DATA__`` / 403), if any.

price trap: ad ``price[0]`` = CASH (== price_cents/100); the ``monthly_payment_price`` attribute
(e.g. 189 EUR/mo lease_to_own) is SEPARATE — the parser uses price[0], trap-safe.
count_verify (>=2 ways, both inline in page-1 searchData, zero extra DataDome exposure):
``total`` vs ``total_pro + total_private`` (the seller partition).

WARNING: per the DOSSIER, sustained proxy-free paging from a datacenter/CH IP is NOT guaranteed;
production harvest of all 781k needs an FR residential/mobile egress. This seals the parser +
caging + counts + trap and MEASURES the proxy-free ceiling — it does not claim full-volume proxy-free.

    py -m scripts.seal_leboncoin --sample 60 [--pages 12]   # E2E + sustainability probe
    py -m scripts.seal_leboncoin --count-only               # 2-way count (1 request)
"""
from __future__ import annotations

import argparse
import asyncio
import time

import asyncpg
import redis.asyncio as aioredis
from curl_cffi.requests import AsyncSession

from scrapers.common import host_budget
from scrapers.portals.as24_listings import extract_next_data
from scrapers.portals.leboncoin_listings import number_of_results, parse_listings
from scripts import platform_seal as ps

DSN = "postgresql://cardex:cardex_dev_only@localhost:5432/cardex"
REDIS = "redis://localhost:6379"
DOMAIN = "leboncoin.fr"
SEARCH = "https://www.leboncoin.fr/recherche?category=2"
CONFIG_REF = "configs/platforms/leboncoin.json"
SLEEP = 2.5            # DataDome — pace conservatively, single coherent JA3 session


async def _get(sess, url):
    return await sess.get(url, timeout=30, allow_redirects=True)


def _seller_partition(sd: dict) -> int | None:
    pro, priv = sd.get("total_pro"), sd.get("total_private")
    if isinstance(pro, int) and isinstance(priv, int):
        return pro + priv
    return None


async def harvest_sample(sess, want: int, max_pages: int) -> tuple[list[dict], int, str]:
    """Paginate until ``want`` ads or DataDome blocks. Returns (listings, last_ok_page, status)."""
    listings, seen = [], set()
    blocked_at = 0
    page = 1
    while len(listings) < want and page <= max_pages:
        r = await _get(sess, f"{SEARCH}&page={page}")
        nd = extract_next_data(r.text or "") if r.status_code == 200 else {}
        ads = parse_listings(nd) if nd else []
        if r.status_code != 200 or not nd or not ads:
            blocked_at = page
            print(f"  DataDome/empty at page {page}: status={r.status_code} "
                  f"has_nd={bool(nd)} ads={len(ads)}", flush=True)
            break
        for a in ads:
            u = a.get("source_url")
            if u and u not in seen:
                seen.add(u)
                listings.append(ps.to_cage(a))
        print(f"  page {page}: +{len(ads)} ads (total {len(listings)})", flush=True)
        page += 1
        await asyncio.sleep(SLEEP)
    status = f"BLOCKED@p{blocked_at}" if blocked_at else f"OK through p{page-1}"
    return listings[:want], page - 1, status


async def run(sample: int, pages: int, count_only: bool, full: bool) -> None:
    async with AsyncSession(impersonate="chrome136") as sess:
        if not await host_budget.wait_until_healthy(max_s=60):
            print("HOST under pressure; aborting"); return
        print(f"LEBONCOIN seal | sample={sample} max_pages={pages} "
              f"RAM={host_budget.available_mb()}MB", flush=True)

        r0 = await _get(sess, SEARCH)
        nd0 = extract_next_data(r0.text or "")
        sd0 = nd0.get("props", {}).get("pageProps", {}).get("searchData", {})
        declared = number_of_results(nd0)
        way2 = _seller_partition(sd0)
        print(f"  declared total={declared}  total_pro+total_private={way2}  "
              f"max_pages={sd0.get('max_pages')}", flush=True)
        if count_only:
            print(f"\nTOTAL={declared}  SELLER-PARTITION-SUM={way2}")
            return
        await asyncio.sleep(SLEEP)

        t0 = time.monotonic()
        listings, last_page, status = await harvest_sample(sess, sample, pages)
        rich = [li for li in listings if li.get("price") or li.get("year")]
        print(f"  harvested {len(listings)} ({len(rich)} with price/year) | sustained: {status} "
              f"in {int(time.monotonic()-t0)}s", flush=True)

        pool = await asyncpg.create_pool(DSN, min_size=2, max_size=5)
        rdb = aioredis.from_url(REDIS)
        try:
            res = await ps.cage_platform(pool, rdb, DOMAIN, "FR", listings,
                                         config_ref=CONFIG_REF, complete=full)
            api = await ps.verify_api(pool, res["ent"])
            trap = "ad price[0] = CASH (== price_cents/100); monthly_payment_price attr (lease) ignored"
            ps.print_verdict("leboncoin leboncoin.fr", declared=declared,
                             way2_label="seller-partition-sum", way2=way2,
                             served=res["served"], api=api, price_trap=trap)
            print(f"  sustained-pagination probe: {status} (proxy-free ceiling this IP)")
            print(f"  cage: new={res['new']} served={res['served']} gone={res['gone']} "
                  f"(reconcile={'ON' if full else 'OFF (sample)'})")
        finally:
            await rdb.aclose()
            await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=60)
    ap.add_argument("--pages", type=int, default=12)
    ap.add_argument("--count-only", action="store_true")
    ap.add_argument("--full", action="store_true")
    a = ap.parse_args()
    asyncio.run(run(a.sample, a.pages, a.count_only, a.full))
