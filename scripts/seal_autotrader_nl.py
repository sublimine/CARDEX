"""Seal autotrader.nl NL used inventory — PROXY-FREE, clean CloudFront SSR (no Akamai).

autotrader.nl is the AutoScout24 Netherlands white-label: same inventory and the IDENTICAL
``__NEXT_DATA__`` shape as as24.* (vehicle images come from ``prod.pictures.autoscout24.net``,
the SRP route id is ``/lst``). The repo's earlier census marked it SKIP as "covered by the
autoscout24.* scraper (T2/AKAMAI_V3)" — but that is the gasto-gated path: AS24's own domains
front every HTML doc with Akamai. autotrader.nl serves the SAME NL inventory through a
DIFFERENT edge: CloudFront + nginx + Next.js, HTTP 200 to a plain curl_cffi Chrome session
from a datacenter IP, with ZERO Akamai/CF/DataDome challenge (verified live 2026-06-12).
So this is a PROXY-FREE doorway to AS24-NL inventory that is otherwise Akamai-walled — built
per the mandate ("if genuinely proxy-free SSR, build it"), not a duplicate fake seal.

Because the data shape is AS24, the verified-live parser is reused verbatim:
``scrapers.portals.as24_listings`` — ``number_of_results`` (count oracle) and ``parse_listings``
(``props.pageProps.listings`` -> make/model/year/mileage/CASH-price/url, all from the numeric
``tracking.*`` fields). Faceting bisects the price axis inline (async-safe, since every count
is an awaited HTTP call), the same recursion ``plan_price_partitions`` does synchronously.

URL scheme (PUBLIC route is /auto; /lst 404s — that's the internal Next.js route), all
discovered live, NOT assumed:
  base count   GET /auto                                  -> numberOfResults (≈232k)
  year facet   GET /auto?fregfrom=Y&fregto=Y              -> per-year numberOfResults
  price facet  GET /auto?...&pricefrom=lo&priceto=hi      -> sub-split a year over the cap
  pagination   GET /auto?...&page=P                       -> 20 listings/page (cap 200pg=4000)
  NOTE: ?make=<id> is IGNORED; the make facet is path-based (/auto/<slug>). Year is the
  robust, universal count+enumeration axis (no 288-slug derivation), so it is used here.

The deep-pagination window caps at 200 pages × 20 = 4000 per query (numberOfPages tops at 200
while numberOfResults is ~232k), so faceting is MANDATORY: year -> +price band for any year
over the cap. ``sort=price`` gives a stable order so promoted (tier_rotation) cards don't
churn across pages; global dedupe by url absorbs the residual sponsored overlap.

count_verify (>=2 ways): way1 = base ``numberOfResults``; way2 = per-year-sum (fregfrom=Y&
fregto=Y over the model-year range) + the small no-year residual (cars with no first-
registration date, ≈226 — reported, not hidden, mirroring the mobile.de seal).

price trap: ``tracking.price`` (== ``price.priceFormatted``) is the CASH asking price in EUR.
It is NOT a monthly lease: across a page the values span €799→€124,950 tracking the car
(Porsche Cayenne €124,950, Saab 9-3 €3,950), not a flat /mo band. ``suggestedRetailPrice``
(the new-car MSRP) and the separate leasing facets are deliberately ignored.

    py -m scripts.seal_autotrader_nl --count-only          # 2-way count verify (curl only)
    py -m scripts.seal_autotrader_nl --sample 60           # E2E proof: enumerate+cage(INSERT-only)+verify
    py -m scripts.seal_autotrader_nl --full [--max-leaves N]# exhaustive year×price sweep (reconciles)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
import urllib.parse

import asyncpg
import redis.asyncio as aioredis
from curl_cffi.requests import AsyncSession

from scrapers.common import host_budget
from scrapers.portals.as24_listings import (
    extract_next_data,
    number_of_results,
    parse_listings,
)
from scripts import platform_seal as ps

# Windows console: AS24 titles carry accents (é, ü); make stdout UTF-8 safe at import.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:  # noqa: BLE001
    pass

DSN = "postgresql://cardex:cardex_dev_only@localhost:5432/cardex"
REDIS = "redis://localhost:6379"
DOMAIN = "autotrader.nl"
COUNTRY = "NL"
BASE = "https://www.autotrader.nl/auto"
BASE_URL = "https://www.autotrader.nl"
CONFIG_REF = "configs/platforms/autotrader_nl.json"

# Stable, NL-scoped used+new car query. sort=price keeps pagination order stable so promoted
# (tier_rotation) cards don't reshuffle page→page; global url-dedupe mops up the rest.
COMMON = {"atype": "C", "cy": "NL", "ustate": "N,U", "sort": "price", "desc": "0"}

PAGE_CAP = 200          # numberOfPages tops at 200 (verified live)
PER_PAGE = 20           # 20 listings/page (verified live)
WINDOW_CAP = PAGE_CAP * PER_PAGE   # 4000 reachable per query
LEAF_CAP = 3800         # keep each facet leaf under the 4000 window (headroom for count drift)
SLEEP = 1.2             # jitter-free polite floor; ~0.8 req/s
YEAR_MIN, YEAR_MAX = 1990, 2026
PRICE_HI = 1_000_000    # cash-price ceiling for the bisection axis


async def _nd(sess, **params) -> dict:
    """GET /auto with the common NL query + ``params``; return parsed __NEXT_DATA__ ({} on non-200)."""
    q = urllib.parse.urlencode({**COMMON, **params})
    r = await sess.get(f"{BASE}?{q}", timeout=30, allow_redirects=True)
    return extract_next_data(r.text or "") if r.status_code == 200 else {}


async def _count(sess, **params) -> int | None:
    return number_of_results(await _nd(sess, **params))


# ----------------------------------------------------------------------------- count_verify
async def count_verify(sess) -> tuple[int | None, int | None]:
    """way1 = base numberOfResults; way2 = per-year-sum + pre-1990 cohort + no-year residual.

    The base total spans the full first-registration universe; way2 reconstructs it from three
    disjoint cohorts so the two axes describe the same set: (a) per-year cells 1990..2026,
    (b) the pre-1990 classics cohort (fregto=1989, outside the per-year grid), and (c) the
    no-year residual (cars with no first-registration date, base - with-year) — reported, not
    hidden, mirroring the mobile.de seal.
    """
    base = await _count(sess)
    await asyncio.sleep(SLEEP)
    with_year = await _count(sess, fregfrom=1900, fregto=2030)
    await asyncio.sleep(SLEEP)
    residual = (base - with_year) if (base is not None and with_year is not None) else 0
    pre = await _count(sess, fregto=YEAR_MIN - 1) or 0      # pre-1990 classics cohort
    await asyncio.sleep(SLEEP)
    per_year_sum = max(residual, 0) + pre
    counted = 0
    for y in range(YEAR_MIN, YEAR_MAX + 1):
        c = await _count(sess, fregfrom=y, fregto=y)
        if c:
            per_year_sum += c
            counted += 1
        await asyncio.sleep(SLEEP)
    print(f"  per-year-sum: {counted} years + pre-1990({pre}) + no-year-residual({residual}) "
          f"-> {per_year_sum}", flush=True)
    return base, per_year_sum


# ----------------------------------------------------------------------------- faceting
def _year_params(leaf: dict) -> dict:
    """Year-axis query for a leaf: a single year, or an open/closed range (pre-1990 cohort)."""
    p: dict = {}
    if leaf.get("year_from") is not None:
        p["fregfrom"] = leaf["year_from"]
    if leaf.get("year_to") is not None:
        p["fregto"] = leaf["year_to"]
    return p


async def _price_split(sess, cell: dict, n: int) -> list[dict]:
    """A year cell over LEAF_CAP -> price-band leaves by recursive bisection of [0, PRICE_HI).

    Async-safe mirror of ``as24_listings.plan_price_partitions`` (which is sync): split until
    each band's own ``numberOfResults`` is under the window cap, keeping every count awaited and
    rate-limited. A band still over the cap below 250 EUR width is kept anyway (price spike
    denser than the cap — accept the small leak) so the recursion always terminates. ``cell``
    carries the year axis (``year_from``/``year_to``) the bands inherit.
    """
    yp = _year_params(cell)
    leaves: list[dict] = []
    stack: list[tuple[int, int]] = [(0, PRICE_HI)]
    while stack:
        lo, hi = stack.pop()
        if hi <= lo:
            continue
        c = await _count(sess, **yp, pricefrom=lo, priceto=hi)
        await asyncio.sleep(SLEEP)
        if not c:
            continue
        if c < LEAF_CAP or (hi - lo) <= 250:
            leaves.append({**cell, "price_from": lo, "price_to": hi, "_n": c})
        else:
            mid = lo + (hi - lo) // 2
            stack.append((mid, hi))
            stack.append((lo, mid))
    leaves.sort(key=lambda lf: lf["price_from"])
    return leaves


async def build_facets(sess, *, verbose: bool = True) -> list[dict]:
    """Adaptive leaves, each count < LEAF_CAP: the pre-1990 classics cohort + per year
    1990..2026, price-splitting any cell over the cap. Covers the full fr-addressable universe."""
    leaves: list[dict] = []
    # pre-1990 classics cohort (outside the per-year grid)
    pre_cell = {"year_to": YEAR_MIN - 1}
    pre = await _count(sess, **_year_params(pre_cell))
    await asyncio.sleep(SLEEP)
    if pre:
        leaves.append({**pre_cell, "_n": pre}) if pre < LEAF_CAP \
            else leaves.extend(await _price_split(sess, pre_cell, pre))
    for y in range(YEAR_MIN, YEAR_MAX + 1):
        cell = {"year_from": y, "year_to": y}
        cy = await _count(sess, **_year_params(cell))
        await asyncio.sleep(SLEEP)
        if not cy:
            continue
        if cy < LEAF_CAP:
            leaves.append({**cell, "_n": cy})
        else:
            leaves.extend(await _price_split(sess, cell, cy))
        if verbose:
            print(f"  year {y}: {cy} -> {'leaf' if cy < LEAF_CAP else 'price-split'}", flush=True)
    over = [lf for lf in leaves if lf["_n"] > WINDOW_CAP]
    print(f"  facets: {len(leaves)} leaves, sum_n={sum(lf['_n'] for lf in leaves)}, "
          f"still-over-cap={len(over)} (cap {WINDOW_CAP}/leaf)", flush=True)
    return leaves


def _leaf_params(leaf: dict, page: int) -> dict:
    p = {**_year_params(leaf), "page": page}
    if leaf.get("price_from") is not None:
        p["pricefrom"] = leaf["price_from"]
    if leaf.get("price_to") is not None:
        p["priceto"] = leaf["price_to"]
    return p


async def enumerate_leaf(sess, leaf: dict, *, want: int | None = None) -> list[dict]:
    """Walk a facet leaf's pages 1..min(cap, ceil(n/per_page)); cage-shape rows, dedupe by url."""
    pages = min(PAGE_CAP, (leaf.get("_n", PER_PAGE) // PER_PAGE) + 2)
    by_url: dict[str, dict] = {}
    for pg in range(1, pages + 1):
        nd = await _nd(sess, **_leaf_params(leaf, pg))
        rows = parse_listings(nd, base_url=BASE_URL, currency="EUR")
        if not rows:
            break
        for r in rows:
            cage = ps.to_cage(r)
            if cage["url"]:
                by_url.setdefault(cage["url"], cage)
        await asyncio.sleep(SLEEP)
        if want and len(by_url) >= want:
            break
    return list(by_url.values())


# ----------------------------------------------------------------------------- runs
async def run_count(sess) -> None:
    base, way2 = await count_verify(sess)
    agree = (100 - abs(base - way2) / max(base, 1) * 100) if (base and way2) else None
    print(f"\nBASE numberOfResults = {base}   PER-YEAR-SUM = {way2}"
          + (f"   agreement={agree:.2f}%" if agree is not None else ""), flush=True)


async def run_sample(sess, sample: int) -> None:
    """E2E proof slice: enumerate the UNFILTERED market head (no year facet) so the slice keeps
    the real price distribution (€799→€124,950 on a page — NOT the cheap tail of one old year,
    which would falsely trip the verifier's monthly-payment-trap detector). ``sort=age`` (newest
    first) mixes price naturally; cage INSERT-only (complete=False — a partial set must never
    GONE-mark), then verify the API view."""
    base = await _count(sess)
    await asyncio.sleep(SLEEP)
    listings: list[dict] = []
    seen: set[str] = set()
    t0 = time.monotonic()
    page = 1
    while len(listings) < sample and page <= PAGE_CAP:
        q = urllib.parse.urlencode({**COMMON, "sort": "age", "desc": "1", "page": page})
        r = await sess.get(f"{BASE}?{q}", timeout=30, allow_redirects=True)
        rows = parse_listings(extract_next_data(r.text or "") if r.status_code == 200 else {},
                              base_url=BASE_URL, currency="EUR")
        if not rows:
            break
        for row in rows:
            cage = ps.to_cage(row)
            if cage["url"] and cage["url"] not in seen:
                seen.add(cage["url"])
                listings.append(cage)
        page += 1
        await asyncio.sleep(SLEEP)
    listings = listings[:sample]
    rich = [li for li in listings if li.get("price") or li.get("year")]
    priced = [li["price"] for li in listings if li.get("price")]
    span = f"{min(priced)}-{max(priced)} EUR" if priced else "n/a"
    print(f"  enumerated {len(listings)} listings ({len(rich)} with price/year, "
          f"price span {span}) in {int(time.monotonic()-t0)}s", flush=True)

    pool = await asyncpg.create_pool(DSN, min_size=2, max_size=6)
    rdb = aioredis.from_url(REDIS)
    try:
        res = await ps.cage_platform(pool, rdb, DOMAIN, COUNTRY, listings,
                                     config_ref=CONFIG_REF, complete=False)
        api = await ps.verify_api(pool, res["ent"])
        trap = "tracking.price == price.priceFormatted = CASH EUR (suggestedRetailPrice=MSRP & lease facets ignored)"
        ps.print_verdict("AutoTrader autotrader.nl", declared=base,
                         way2_label="per-year-sum (skipped on sample)", way2=None,
                         served=res["served"], api=api, price_trap=trap)
        print(f"  cage: new={res['new']} served={res['served']} gone={res['gone']} "
              f"(reconcile=OFF (sample))", flush=True)
    finally:
        await rdb.aclose()
        await pool.close()


async def run_full(sess, max_leaves: int) -> None:
    """Exhaustive year×price sweep: build all leaves, enumerate each, cage with reconcile
    (complete=True only on an unbounded sweep). max_leaves bounds a partial run safely."""
    base, way2 = await count_verify(sess)
    leaves = await build_facets(sess)
    if max_leaves:
        leaves = leaves[:max_leaves]
        print(f"  (bounded to first {len(leaves)} leaves)", flush=True)

    listings: list[dict] = []
    t0 = time.monotonic()
    for i, lf in enumerate(leaves, 1):
        if not await host_budget.wait_until_healthy(max_s=120):
            print(f"  host pressure at leaf {i}; stopping sweep", flush=True)
            break
        listings.extend(await enumerate_leaf(sess, lf))
        if i % 10 == 0:
            print(f"  [{i}/{len(leaves)}] cum_listings={len(listings)} "
                  f"({int(time.monotonic()-t0)}s)", flush=True)
    uniq = list({li["url"]: li for li in listings}.values())
    print(f"  enumerated {len(uniq)} unique listings from {len(leaves)} leaves", flush=True)

    complete = not max_leaves               # only a full sweep may reconcile (GONE/DELETE)
    pool = await asyncpg.create_pool(DSN, min_size=2, max_size=6)
    rdb = aioredis.from_url(REDIS)
    try:
        res = await ps.cage_platform(pool, rdb, DOMAIN, COUNTRY, uniq,
                                     config_ref=CONFIG_REF, complete=complete)
        api = await ps.verify_api(pool, res["ent"])
        trap = "tracking.price == price.priceFormatted = CASH EUR (MSRP & lease facets ignored)"
        ps.print_verdict("AutoTrader autotrader.nl", declared=base,
                         way2_label="per-year-sum", way2=way2,
                         served=res["served"], api=api, price_trap=trap)
        print(f"  cage: new={res['new']} served={res['served']} gone={res['gone']} "
              f"(reconcile={'ON' if complete else 'OFF (bounded)'})", flush=True)
    finally:
        await rdb.aclose()
        await pool.close()


async def main(sample: int, count_only: bool, full: bool, max_leaves: int) -> None:
    if not await host_budget.wait_until_healthy(max_s=60):
        print("HOST under pressure; aborting")
        return
    print(f"autotrader.nl seal | count_only={count_only} sample={sample} full={full} "
          f"RAM={host_budget.available_mb()}MB", flush=True)
    async with AsyncSession(impersonate="chrome136") as sess:
        if count_only:
            await run_count(sess)
        elif full:
            await run_full(sess, max_leaves)
        else:
            await run_sample(sess, sample)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=60)
    ap.add_argument("--count-only", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--max-leaves", type=int, default=0)
    a = ap.parse_args()
    asyncio.run(main(a.sample, a.count_only, a.full, a.max_leaves))
