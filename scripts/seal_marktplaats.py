"""Seal Marktplaats (marktplaats.nl) NL used inventory — PROXY-FREE, no WAF (CloudFront).

marktplaats.nl/l/auto-s/ is Next.js (HTTP 200 to a curl_cffi Chrome session, CloudFront, no
challenge). The existing parser (scrapers/portals/marktplaats_listings.py) is verified LIVE:
``__NEXT_DATA__.props.pageProps.searchRequestAndResponse`` -> {totalResultCount, listings[30]}.
Each listing carries make (from the vipUrl category segment), model/year/km (attributes), and
``priceInfo.priceCents`` -> CASH asking price (priceType fixed/bidding is separate; the parser
already drops cents<=0). Pagination ``/p/N/`` (30/page); deep offset truncates (the advertised
``maxAllowedPageNumber`` is a soft cap), so full enumeration FACETS by brand subcategory
(``/l/auto-s/<brandKey>/``, an L2 category) then constructionYear for any brand above the cap.

count_verify (>=2 ways): the declared ``totalResultCount`` vs the brand-subcategory-sum over
``searchCategoryOptions`` (every ``parentKey=auto-s`` brand -> its own ``/l/auto-s/<key>/`` total).

    py -m scripts.seal_marktplaats --sample 60        # E2E proof (INSERT-only, no GONE)
    py -m scripts.seal_marktplaats --count-only       # 2-way count verify only
    py -m scripts.seal_marktplaats --full             # exhaustive facet sweep (reconciles)
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
from scrapers.portals.marktplaats_listings import number_of_results, parse_listings
from scripts import platform_seal as ps

DSN = "postgresql://cardex:cardex_dev_only@localhost:5432/cardex"
REDIS = "redis://localhost:6379"
DOMAIN = "marktplaats.nl"
BASE = "https://www.marktplaats.nl/l/auto-s/"
CONFIG_REF = "configs/platforms/marktplaats.json"
SLEEP = 1.2


async def _get(sess, url):
    return await sess.get(url, timeout=30, allow_redirects=True)


async def _nd(sess, url) -> dict:
    r = await _get(sess, url)
    return extract_next_data(r.text or "") if r.status_code == 200 else {}


async def harvest_sample(sess, want: int) -> list[dict]:
    listings, seen = [], set()
    page = 1
    while len(listings) < want:
        nd = await _nd(sess, f"{BASE}p/{page}/")
        rows = parse_listings(nd)
        if not rows:
            break
        for r in rows:
            u = r.get("source_url")
            if u and u not in seen:
                seen.add(u)
                listings.append(ps.to_cage(r))
        page += 1
        await asyncio.sleep(SLEEP)
    return listings[:want]


def _brand_keys(nd: dict) -> list[str]:
    srr = nd.get("props", {}).get("pageProps", {}).get("searchRequestAndResponse", {})
    opts = srr.get("searchCategoryOptions") or []
    return [o["key"] for o in opts if isinstance(o, dict)
            and o.get("parentKey") == "auto-s" and o.get("key") and o.get("key") != "auto-s"]


async def count_verify(sess) -> tuple[int | None, int | None]:
    nd = await _nd(sess, BASE)
    declared = number_of_results(nd)
    brands = _brand_keys(nd)
    await asyncio.sleep(SLEEP)
    total = counted = 0
    for b in brands:
        bnd = await _nd(sess, f"{BASE}{b}/")
        t = number_of_results(bnd)
        if t:
            total += t
            counted += 1
        await asyncio.sleep(SLEEP)
    print(f"  brand-subcategory-sum: {counted}/{len(brands)} brands -> {total}")
    return declared, total


async def run(sample: int, count_only: bool, full: bool, skip_count: bool) -> None:
    async with AsyncSession(impersonate="chrome136") as sess:
        if not await host_budget.wait_until_healthy(max_s=60):
            print("HOST under pressure; aborting"); return
        print(f"MARKTPLAATS seal | sample={sample} full={full} "
              f"RAM={host_budget.available_mb()}MB", flush=True)

        declared = way2 = None
        if not skip_count:
            declared, way2 = await count_verify(sess)
        if count_only:
            print(f"\nDECLARED={declared}  BRAND-SUBCATEGORY-SUM={way2}")
            return

        t0 = time.monotonic()
        listings = await harvest_sample(sess, sample)
        rich = [li for li in listings if li.get("price") or li.get("year")]
        print(f"  harvested {len(listings)} ({len(rich)} with price/year) in "
              f"{int(time.monotonic()-t0)}s", flush=True)

        pool = await asyncpg.create_pool(DSN, min_size=2, max_size=5)
        rdb = aioredis.from_url(REDIS)
        try:
            res = await ps.cage_platform(pool, rdb, DOMAIN, "NL", listings,
                                         config_ref=CONFIG_REF, complete=full)
            api = await ps.verify_api(pool, res["ent"])
            trap = "priceInfo.priceCents/100 = CASH asking price (priceType bidding/fixed separate)"
            ps.print_verdict("Marktplaats marktplaats.nl", declared=declared,
                             way2_label="brand-subcategory-sum", way2=way2,
                             served=res["served"], api=api, price_trap=trap)
            print(f"  cage: new={res['new']} served={res['served']} gone={res['gone']} "
                  f"(reconcile={'ON' if full else 'OFF (sample)'})")
        finally:
            await rdb.aclose()
            await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=60)
    ap.add_argument("--count-only", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--skip-count", action="store_true")
    a = ap.parse_args()
    asyncio.run(run(a.sample, a.count_only, a.full, a.skip_count))
