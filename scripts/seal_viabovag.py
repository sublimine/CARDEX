"""Seal viaBOVAG (viabovag.nl) NL used inventory — PROXY-FREE, no WAF (Next.js/IIS), no auth.

viabovag.nl serves search via a Next.js data route (HTTP 200 to a curl_cffi Chrome session,
no Cloudflare/Akamai). The buildId is read once from the /auto HTML ``__NEXT_DATA__`` and reused:
  GET /_next/data/{buildId}/srp.json?mobilityType=auto&selectedFilters=pagina-{N}
``pageProps.serverSearchResults`` -> {count, results[24]}; each result carries everything
(no per-detail fetch): ``url`` (absolute), ``title``, ``price`` (CASH int — the lease/finance
``isFinanceable``/leasePrice is separate, so price is trap-safe), ``vehicle.{brand,model,year,
mileage}``. Pagination caps at pagina-4167 (24/page); later pages return stale data.

count_verify (>=2 ways): the declared ``serverSearchResults.count`` vs the full brand-facet-sum
(``serverSearchFacets.facets[Brand].optionCategories[full].options[*].count`` — the 132-brand
complete partition, == total).

    py -m scripts.seal_viabovag --sample 60 [--conc 1]    # E2E proof (INSERT-only, no GONE)
    py -m scripts.seal_viabovag --count-only              # 2-way count verify only
    py -m scripts.seal_viabovag --full                    # exhaustive sweep (reconciles)
"""
from __future__ import annotations

import argparse
import asyncio
import re
import time

import asyncpg
import redis.asyncio as aioredis
from curl_cffi.requests import AsyncSession

from scrapers.common import host_budget
from scripts import platform_seal as ps

DSN = "postgresql://cardex:cardex_dev_only@localhost:5432/cardex"
REDIS = "redis://localhost:6379"
DOMAIN = "viabovag.nl"
BASE = "https://www.viabovag.nl"
CONFIG_REF = "configs/platforms/viabovag.json"
PER_PAGE = 24
PAGE_CAP = 4167
SLEEP = 1.0

BUILD = re.compile(r'"buildId"\s*:\s*"([A-Za-z0-9_-]+)"')


async def _get(sess, url, **kw):
    return await sess.get(url, timeout=30, allow_redirects=True, **kw)


async def resolve_build_id(sess) -> str | None:
    html = (await _get(sess, f"{BASE}/auto")).text or ""
    m = BUILD.search(html)
    return m.group(1) if m else None


def _data_url(bid: str, page: int) -> str:
    return f"{BASE}/_next/data/{bid}/srp.json?mobilityType=auto&selectedFilters=pagina-{page}"


def parse_results(payload: dict) -> list[dict]:
    sr = (payload.get("pageProps", {}) or {}).get("serverSearchResults", {}) or {}
    out = []
    for it in sr.get("results") or []:
        if not isinstance(it, dict):
            continue
        url = it.get("url") or ""
        if url.startswith("/"):
            url = BASE + url
        if not url:
            continue
        veh = it.get("vehicle") or {}
        title = it.get("title") or " ".join(
            str(x) for x in (veh.get("brand"), veh.get("model")) if x).strip() or None
        out.append({
            "url": url,
            "title": title,
            "price": it.get("price") if isinstance(it.get("price"), (int, float)) else None,
            "year": veh.get("year") if isinstance(veh.get("year"), int) else None,
            "km": veh.get("mileage") if isinstance(veh.get("mileage"), (int, float)) else None,
        })
    return out


def _brand_facet_sum(payload: dict) -> int | None:
    """Full brand partition: the Brand group's optionCategory with the most options."""
    facets = ((payload.get("pageProps", {}) or {}).get("serverSearchFacets", {}) or {}).get("facets") or []
    best = None
    for g in facets:
        if (g.get("name") or g.get("label") or "").lower().startswith("brand"):
            for oc in g.get("optionCategories") or []:
                opts = oc.get("options") or []
                s = sum(int(o.get("count") or 0) for o in opts if isinstance(o, dict))
                if best is None or len(opts) > best[0]:
                    best = (len(opts), s)
    return best[1] if best else None


async def harvest_sample(sess, bid: str, want: int) -> list[dict]:
    listings, seen = [], set()
    pages = (want // PER_PAGE) + 2
    for pg in range(1, min(pages, PAGE_CAP) + 1):
        r = await _get(sess, _data_url(bid, pg))
        if r.status_code != 200:
            break
        for c in parse_results(r.json()):
            if c["url"] not in seen:
                seen.add(c["url"])
                listings.append(c)
        await asyncio.sleep(SLEEP)
        if len(listings) >= want:
            break
    return listings[:want]


async def count_verify(sess, bid: str) -> tuple[int | None, int | None]:
    payload = (await _get(sess, _data_url(bid, 1))).json()
    declared = ((payload.get("pageProps", {}) or {}).get("serverSearchResults", {}) or {}).get("count")
    return declared, _brand_facet_sum(payload)


async def run(sample: int, conc: int, count_only: bool, full: bool, skip_count: bool) -> None:
    async with AsyncSession(impersonate="chrome136") as sess:
        if not await host_budget.wait_until_healthy(max_s=60):
            print("HOST under pressure; aborting"); return
        bid = await resolve_build_id(sess)
        print(f"VIABOVAG seal | buildId={bid} sample={sample} full={full} "
              f"RAM={host_budget.available_mb()}MB", flush=True)
        if not bid:
            print("could not resolve buildId; abort"); return

        declared = way2 = None
        if not skip_count:
            declared, way2 = await count_verify(sess, bid)
        if count_only:
            print(f"\nDECLARED={declared}  BRAND-FACET-SUM={way2}")
            return

        t0 = time.monotonic()
        listings = await harvest_sample(sess, bid, sample)
        rich = [li for li in listings if li.get("price") or li.get("year")]
        print(f"  harvested {len(listings)} ({len(rich)} with price/year) in "
              f"{int(time.monotonic()-t0)}s", flush=True)

        pool = await asyncpg.create_pool(DSN, min_size=2, max_size=conc + 3)
        rdb = aioredis.from_url(REDIS)
        try:
            res = await ps.cage_platform(pool, rdb, DOMAIN, "NL", listings,
                                         config_ref=CONFIG_REF, complete=full)
            api = await ps.verify_api(pool, res["ent"])
            trap = "result.price = CASH (EUR int); isFinanceable/leasePrice are separate fields"
            ps.print_verdict("viaBOVAG viabovag.nl", declared=declared,
                             way2_label="brand-facet-sum", way2=way2,
                             served=res["served"], api=api, price_trap=trap)
            print(f"  cage: new={res['new']} served={res['served']} gone={res['gone']} "
                  f"(reconcile={'ON' if full else 'OFF (sample)'})")
        finally:
            await rdb.aclose()
            await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=60)
    ap.add_argument("--conc", type=int, default=1)
    ap.add_argument("--count-only", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--skip-count", action="store_true")
    a = ap.parse_args()
    asyncio.run(run(a.sample, a.conc, a.count_only, a.full, a.skip_count))
