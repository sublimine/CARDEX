"""Seal PKW.de (pkw.de) DE used inventory — PROXY-FREE, no WAF (BunnyCDN), keyless JSON API.

pkw.de exposes a clean public JSON API (HTTP 200 to a curl_cffi Chrome session, no token):
  GET /api/v1/cars/search/count[?fueltype=N]  -> {"total_count": N}   (declared total + facet)
  GET /api/v1/cars/search?page=N              -> {results[20], total{count,pages}, aggregations}
``results[]`` carries everything (no per-detail fetch): ``url``, ``name``, ``brand``/``model``,
``mileage``, ``initial_registration`` (YYYY-MM-DD -> year), and ``price`` as a DICT whose
buyer-facing CASH value is ``price.customer`` (gross) — NOT ``netto_price`` (ex-VAT),
``initial_price`` (pre-discount), ``predicted`` (market estimate) or the financing monthly (the
price trap). The search endpoint caps ``total.count`` at 200 (10 pages x 20) per filter, so full
enumeration FACETS by fueltype/brand.

count_verify (>=2 ways): the declared ``/count`` total vs the fueltype partition-sum
(``/count?fueltype=N`` over the fuel enum). [VERIFIED 2026-06-12: total 113,790;
fueltype 1..5 = 62459+31584+763+7204+11214.]

    py -m scripts.seal_pkw --sample 60          # E2E proof (INSERT-only, no GONE)
    py -m scripts.seal_pkw --count-only         # 2-way count verify only
    py -m scripts.seal_pkw --full               # exhaustive facet sweep (reconciles)
"""
from __future__ import annotations

import argparse
import asyncio
import time

import asyncpg
import redis.asyncio as aioredis
from curl_cffi.requests import AsyncSession

from scrapers.common import host_budget
from scripts import platform_seal as ps

DSN = "postgresql://cardex:cardex_dev_only@localhost:5432/cardex"
REDIS = "redis://localhost:6379"
DOMAIN = "pkw.de"
API = "https://www.pkw.de/api/v1/cars/search"
CONFIG_REF = "configs/platforms/pkw.json"
PER_PAGE = 20
SLEEP = 0.8
FUEL_ENUM = range(0, 9)          # fueltype ids; 1..5 populated, rest 0 (verified)


async def _get_json(sess, url):
    r = await sess.get(url, timeout=30, allow_redirects=True)
    return r.json() if r.status_code == 200 else {}


def _year(reg) -> int | None:
    s = str(reg or "")
    return int(s[:4]) if s[:4].isdigit() else None


def parse_results(payload: dict) -> list[dict]:
    out = []
    for it in payload.get("results") or []:
        if not isinstance(it, dict):
            continue
        url = it.get("url") or ""
        if not url:
            continue
        title = it.get("name") or " ".join(
            str(x) for x in (it.get("brand"), it.get("model")) if x).strip() or None
        # price is a DICT; the buyer-facing CASH price is `customer` (gross). NOT netto_price
        # (ex-VAT), NOT initial_price (pre-discount list), NOT predicted (market estimate),
        # NOT monthly_cost / initial_financing_offer.monthly_rate (financing) — the trap.
        pd = it.get("price") or {}
        cash = pd.get("customer") if isinstance(pd, dict) else pd
        out.append({
            "url": url,
            "title": title,
            "price": int(cash) if isinstance(cash, (int, float)) and cash else None,
            "year": _year(it.get("initial_registration")),
            "km": int(it["mileage"]) if isinstance(it.get("mileage"), (int, float)) else None,
        })
    return out


async def harvest_sample(sess, want: int) -> list[dict]:
    listings, seen = [], set()
    page = 1
    while len(listings) < want:
        payload = await _get_json(sess, f"{API}?page={page}")
        rows = parse_results(payload)
        if not rows:
            break
        for c in rows:
            if c["url"] not in seen:
                seen.add(c["url"])
                listings.append(c)
        page += 1
        await asyncio.sleep(SLEEP)
        pages = ((payload.get("total") or {}).get("pages")) or 1
        if page > pages:
            break
    return listings[:want]


async def count_verify(sess) -> tuple[int | None, int | None]:
    declared = (await _get_json(sess, f"{API}/count")).get("total_count")
    await asyncio.sleep(SLEEP)
    total = 0
    parts = []
    for ft in FUEL_ENUM:
        c = (await _get_json(sess, f"{API}/count?fueltype={ft}")).get("total_count") or 0
        if c:
            total += c
            parts.append(f"{ft}:{c}")
        await asyncio.sleep(SLEEP)
    print(f"  fueltype partition: {' '.join(parts)} -> sum={total}")
    return declared, total


async def run(sample: int, count_only: bool, full: bool, skip_count: bool) -> None:
    async with AsyncSession(impersonate="chrome136") as sess:
        if not await host_budget.wait_until_healthy(max_s=60):
            print("HOST under pressure; aborting"); return
        print(f"PKW seal | sample={sample} full={full} RAM={host_budget.available_mb()}MB", flush=True)

        declared = way2 = None
        if not skip_count:
            declared, way2 = await count_verify(sess)
        if count_only:
            print(f"\nDECLARED={declared}  FUELTYPE-SUM={way2}")
            return

        t0 = time.monotonic()
        listings = await harvest_sample(sess, sample)
        rich = [li for li in listings if li.get("price") or li.get("year")]
        print(f"  harvested {len(listings)} ({len(rich)} with price/year) in "
              f"{int(time.monotonic()-t0)}s", flush=True)

        pool = await asyncpg.create_pool(DSN, min_size=2, max_size=5)
        rdb = aioredis.from_url(REDIS)
        try:
            res = await ps.cage_platform(pool, rdb, DOMAIN, "DE", listings,
                                         config_ref=CONFIG_REF, complete=full)
            api = await ps.verify_api(pool, res["ent"])
            trap = ("price.customer = gross CASH (EUR); NOT netto_price (ex-VAT) / initial_price "
                    "(pre-discount) / predicted (market est) / monthly_cost (financing)")
            ps.print_verdict("PKW.de pkw.de", declared=declared,
                             way2_label="fueltype-partition-sum", way2=way2,
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
