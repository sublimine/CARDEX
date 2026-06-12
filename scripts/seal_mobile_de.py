"""Seal mobile.de (suchen.mobile.de) DE used inventory — PROXY-FREE, two coherent engines.

mobile.de is the LARGEST DE market (~1.5M cars). It fronts every HTML *document* with
Akamai Bot Manager, so plain curl_cffi is 403-blocked on the SRP/detail pages. But TWO
keyless surfaces are open and were verified live (2026-06-12):

  1. hit-count JSON  GET https://www.mobile.de/consumer/api/search/hit-count?<srp params>
     -> {"count":N}.  Returns 200 from a datacenter IP via curl_cffi even with an
     unvalidated _abck cookie (Akamai does NOT gate this lightweight GET). This is the
     size oracle (adaptive faceting) AND count_verify, with ZERO browser cost.
       whole-market Car = 1,509,285   (matches the ~1.58M figure within ~5%)

  2. SRP HTML via Camoufox  https://suchen.mobile.de/fahrzeuge/search.html?...&pageNumber=P
     Firefox + real JS mints a valid _abck and reaches the rendered SRP. Listing cards
     carry detail href + full rich data in the DOM, so NO second (Akamai-gated) detail
     fetch is needed. Verified live: 6 clean pages, 0 blocks, 24/p1 + 20/p2.. distinct ids.

These are two surfaces for two jobs (count vs enumeration), never mixed mid-page-sequence:
the JA3 invariant binds the SRP walk (ONE Camoufox browser, one fingerprint, page 1..N),
and hit-count is a separate JSON API on www.mobile.de. RAM-aware: ONE Camoufox at a time
(host_budget BROWSER lane), >=2s between SRP loads (<=0.5 req/s).

Verified filter params (from the SRP __INITIAL_STATE__.filtersConfig):
  fr = FIRST_REGISTRATION (RANGE)  fr=YYYY:YYYY      p  = PRICE (RANGE)  p=min:max  (EUR)
  ft = FUEL_TYPE (MULTI)  PETROL|DIESEL|ELECTRICITY|HYBRID|HYBRID_DIESEL|LPG|CNG|...

Pagination caps at ~50 pages * ~20 = ~1000/search, so faceting is mandatory (AS24-style):
market -> per-year (fr=Y:Y) -> +price band -> +fuel, descending only into leaves over the cap.

    py -m scripts.seal_mobile_de --count-only            # 2-way keyless count verify (no browser)
    py -m scripts.seal_mobile_de --sample 60 [--conc 4]  # E2E proof: enumerate+cage(INSERT-only)+verify
    py -m scripts.seal_mobile_de --full  [--max-leaves N] # exhaustive facet sweep (reconciles)
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time

# Camoufox/Playwright spawns the browser as a subprocess -> needs the Proactor loop on
# Windows. curl_cffi here is fine on Proactor too (no subprocess), so set Proactor once.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

import asyncpg
import redis.asyncio as aioredis
from curl_cffi.requests import AsyncSession

from scrapers.common import host_budget
from scripts import platform_seal as ps

DSN = "postgresql://cardex:cardex_dev_only@localhost:5432/cardex"
REDIS = "redis://localhost:6379"
DOMAIN = "suchen.mobile.de"
COUNTRY = "DE"
CONFIG_REF = "configs/platforms/mobile_de.json"

HIT = "https://www.mobile.de/consumer/api/search/hit-count"
SRP = "https://suchen.mobile.de/fahrzeuge/search.html"
DETAIL = "https://suchen.mobile.de/fahrzeuge/details.html?id={id}"

PAGE_CAP = 50            # mobile.de pager tops out at 50 (verified live + research)
PER_PAGE = 20           # ~20 listings/page (24 on the relevance-sorted first page)
LEAF_CAP = 900          # keep each facet leaf under the ~1000 page-50 ceiling (headroom)
SRP_SLEEP = 2.2         # >=2s between SRP loads -> <=0.5 req/s (RAM-aware, polite)
HIT_SLEEP = 0.3         # hit-count is light; bound in-flight rate

YEAR_MIN, YEAR_MAX = 1990, 2026
# Price ceilings (EUR) to split a per-year cell that still exceeds the cap.
PRICE_EDGES = (2_000, 4_000, 6_000, 8_000, 10_000, 13_000, 16_000, 20_000,
               25_000, 30_000, 40_000, 50_000, 75_000, 100_000)
# Fuel split — last resort for a (year x price) leaf still over the cap (e.g. dense VW years).
FUELS = ("PETROL", "DIESEL", "ELECTRICITY", "HYBRID", "HYBRID_DIESEL", "LPG", "CNG")

_BLOCK = ("zugriff verweigert", "access denied", "sec-if-cpt-container")
_ID_RE = re.compile(r"/fahrzeuge/details\.html\?id=(\d+)")
_EZ_RE = re.compile(r"EZ\s*(\d{2})/(\d{4})")
_KM_RE = re.compile(r"([\d.]{2,})\s*km")
_PRICE_RE = re.compile(r"([\d.]{3,})\s*€")           # NN.NNN €
_CARD_SPLIT = re.compile(r'data-testid="(?:base|tic|top)-result-listing-\d+-link"')
_TITLE_RE = re.compile(r'-title"[^>]*>(.*?)</h2>', re.S)
# Badge labels mobile.de renders before the title span (NEU = newly listed, Gesponsert/
# Top-Angebot = promoted). Strip so titulo_modelo is the clean make+model, not a badge.
_BADGE_RE = re.compile(r"^(?:NEU|Gesponsert|Top-Angebot|Anzeige)\s+", re.I)


# ----------------------------------------------------------------------------- counts
def _srp_query(year_from: int, year_to: int, price_to: int | None = None,
               price_from: int | None = None, fuel: str | None = None,
               page: int | None = None) -> str:
    q = [f"vc=Car", "s=Car", "dam=false", "isSearchRequest=true",
         f"fr={year_from}:{year_to}"]
    if price_from is not None or price_to is not None:
        q.append(f"p={price_from or ''}:{price_to or ''}")
    if fuel:
        q.append(f"ft={fuel}")
    if page is not None:
        q += ["ref=srp", "sb=rel", "od=up", f"pageNumber={page}"]
    return "&".join(q)


async def _hitcount(sess, **kw) -> int | None:
    try:
        r = await sess.get(f"{HIT}?{_srp_query(**kw)}", timeout=30)
        if r.status_code != 200:
            return None
        return int(r.json().get("count"))
    except Exception:  # noqa: BLE001
        return None


async def _hitcount_pre(sess) -> int | None:
    """Pre-1990 classics cohort (fr=:1989) — outside the per-year grid, ~25k cars."""
    try:
        q = "vc=Car&s=Car&dam=false&isSearchRequest=true&fr=:1989"
        r = await sess.get(f"{HIT}?{q}", timeout=30)
        return int(r.json().get("count")) if r.status_code == 200 else None
    except Exception:  # noqa: BLE001
        return None


async def count_verify(sess) -> tuple[int | None, int | None]:
    """Way 1: whole-market (unbounded) hit-count. Way 2: per-year-sum + pre-1990 cohort.

    The bare-market count includes ~97k listings with NO first-registration date that no
    `fr` facet can reach; way 2 is the `fr`-reachable universe (grid + pre-1990), so the
    two intentionally differ by that no-year residual — reported, not hidden."""
    try:
        rb = await sess.get(f"{HIT}?vc=Car&s=Car&dam=false&isSearchRequest=true", timeout=30)
        whole = int(rb.json().get("count")) if rb.status_code == 200 else None
    except Exception:  # noqa: BLE001
        whole = None
    await asyncio.sleep(HIT_SLEEP)
    pre = await _hitcount_pre(sess)
    await asyncio.sleep(HIT_SLEEP)
    per_year_sum = pre or 0
    counted = 0
    for y in range(YEAR_MIN, YEAR_MAX + 1):
        c = await _hitcount(sess, year_from=y, year_to=y)
        if c:
            per_year_sum += c
            counted += 1
        await asyncio.sleep(HIT_SLEEP)
    print(f"  per-year-sum: {counted} years + pre-1990({pre}), sum={per_year_sum}", flush=True)
    return whole, per_year_sum


# ----------------------------------------------------------------------------- faceting
async def _split_cell(sess, year_from, year_to: int, n: int) -> list[dict]:
    """One (year[-range]) cell over LEAF_CAP -> price-band leaves, fuel-split any that
    still exceed the cap. Reused for per-year cells and the pre-1990 cohort alike."""
    leaves: list[dict] = []
    edges = [None, *PRICE_EDGES, None]
    for i in range(len(edges) - 1):
        pf, pt = edges[i], edges[i + 1]
        cp = await _hitcount(sess, year_from=year_from, year_to=year_to,
                             price_from=pf, price_to=pt)
        await asyncio.sleep(HIT_SLEEP)
        if not cp:
            continue
        if cp <= LEAF_CAP:
            leaves.append({"year_from": year_from, "year_to": year_to,
                           "price_from": pf, "price_to": pt, "_n": cp})
            continue
        for ft in FUELS:
            cf = await _hitcount(sess, year_from=year_from, year_to=year_to,
                                 price_from=pf, price_to=pt, fuel=ft)
            await asyncio.sleep(HIT_SLEEP)
            if cf:
                leaves.append({"year_from": year_from, "year_to": year_to,
                               "price_from": pf, "price_to": pt, "fuel": ft, "_n": cf})
    return leaves


async def build_facets(sess, *, verbose: bool = True) -> list[dict]:
    """Adaptive facet leaves, each with a hit-count <= LEAF_CAP (or as small as the
    market allows). Descends market -> year -> +price band -> +fuel, mirroring AS24.
    Includes the pre-1990 classics cohort (fr=:1989) so coverage reaches the full
    fr-addressable universe (~1.41M), not just 1990+ (~1.39M)."""
    leaves: list[dict] = []
    pre = await _hitcount_pre(sess)
    await asyncio.sleep(HIT_SLEEP)
    if pre:
        if pre <= LEAF_CAP:
            leaves.append({"year_from": "", "year_to": 1989, "_n": pre})
        else:
            leaves.extend(await _split_cell(sess, "", 1989, pre))
    for y in range(YEAR_MIN, YEAR_MAX + 1):
        cy = await _hitcount(sess, year_from=y, year_to=y)
        await asyncio.sleep(HIT_SLEEP)
        if not cy:
            continue
        if cy <= LEAF_CAP:
            leaves.append({"year_from": y, "year_to": y, "_n": cy})
        else:
            leaves.extend(await _split_cell(sess, y, y, cy))
        if verbose:
            print(f"  year {y}: {cy} -> {'leaf' if cy <= LEAF_CAP else 'split'}", flush=True)
    over = [lf for lf in leaves if lf["_n"] > PAGE_CAP * PER_PAGE]
    print(f"  facets: {len(leaves)} leaves, sum_n={sum(lf['_n'] for lf in leaves)}, "
          f"still-over-cap={len(over)} (cap {PAGE_CAP*PER_PAGE}/leaf)", flush=True)
    return leaves


# ----------------------------------------------------------------------------- SRP DOM
def _txt(html: str) -> str:
    t = re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", t).strip()


def parse_srp_cards(html: str) -> list[dict]:
    """One rendered SRP page -> cage-shape listings. Rich fields come straight from each
    card's DOM (title h2, main-price-label, the 'EZ MM/YYYY . NNN km . kW . Fuel' row),
    so no Akamai-gated detail fetch is needed."""
    parts = _CARD_SPLIT.split(html)
    out: list[dict] = []
    seen: set[str] = set()
    for seg in parts[1:]:
        mid = _ID_RE.search(seg)
        if not mid:
            continue
        cid = mid.group(1)
        if cid in seen:
            continue
        seen.add(cid)
        body = _txt(seg)
        tm = _TITLE_RE.search(seg)
        title = _BADGE_RE.sub("", _txt(tm.group(1))) if tm else None
        ez = _EZ_RE.search(body)
        km = _KM_RE.search(body)
        pr = _PRICE_RE.search(body)
        out.append({
            "url": DETAIL.format(id=cid),
            "title": title or None,
            "price": int(pr.group(1).replace(".", "")) if pr else None,
            "year": int(ez.group(2)) if ez else None,
            "km": int(km.group(1).replace(".", "")) if km else None,
        })
    return out


async def _load_srp(page, url: str, *, retries: int = 4) -> str:
    """Navigate, absorbing the Akamai sensor interstitial: a deny/sensor page is small,
    so wait+reload until a full SRP (>50KB, no block marker) renders."""
    for attempt in range(1, retries + 1):
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(3500)
        html = await page.content()
        lo = html.lower()
        if len(html) > 50_000 and not any(b in lo for b in _BLOCK):
            return html
        await page.wait_for_timeout(2500 * attempt)
    return await page.content()


async def enumerate_facet(page, leaf: dict, *, want: int | None = None) -> list[dict]:
    """Walk a facet leaf's SRP pages (1..min(cap, ceil(n/per_page))), collecting cage-shape
    listings with rich fields. Stops early at `want` (sample mode)."""
    pages = min(PAGE_CAP, (leaf.get("_n", PER_PAGE) // PER_PAGE) + 2)
    by_id: dict[str, dict] = {}
    for pg in range(1, pages + 1):
        url = f"{SRP}?{_srp_query(leaf['year_from'], leaf['year_to'], leaf.get('price_to'), leaf.get('price_from'), leaf.get('fuel'), page=pg)}"
        html = await _load_srp(page, url)
        if any(b in html.lower() for b in _BLOCK):
            break
        cards = parse_srp_cards(html)
        if not cards:
            break
        for c in cards:
            by_id.setdefault(c["url"], c)
        await asyncio.sleep(SRP_SLEEP)
        if want and len(by_id) >= want:
            break
    return list(by_id.values())


# ----------------------------------------------------------------------------- runs
async def run_count(sess) -> tuple[int | None, int | None]:
    whole, way2 = await count_verify(sess)
    print(f"\nWHOLE-MARKET hit-count = {whole}   PER-YEAR-SUM = {way2}", flush=True)
    return whole, way2


async def run_sample(sess, sample: int) -> None:
    """E2E proof slice: facet -> Camoufox enumerate a few leaves to `sample` listings ->
    cage INSERT-only (complete=False; a partial set must never GONE-mark) -> verify_api."""
    whole = await _hitcount(sess, year_from=YEAR_MIN, year_to=YEAR_MAX)
    await asyncio.sleep(HIT_SLEEP)
    # cheapest representative leaves: a couple of mid-density single years.
    leaves = []
    for y in (2018, 2015, 2012):
        n = await _hitcount(sess, year_from=y, year_to=y)
        await asyncio.sleep(HIT_SLEEP)
        leaves.append({"year_from": y, "year_to": y, "_n": n or PER_PAGE * 5})
    print(f"  sample leaves: {[(lf['year_from'], lf['_n']) for lf in leaves]}", flush=True)

    from camoufox.async_api import AsyncCamoufox
    listings: list[dict] = []
    async with host_budget.slot(None, "browser"):       # process-local browser cap (1)
        async with AsyncCamoufox(headless=True, geoip=False, locale="de-DE") as browser:
            page = await browser.new_page()
            for lf in leaves:
                if len(listings) >= sample:
                    break
                got = await enumerate_facet(page, lf, want=sample - len(listings))
                listings.extend(got)
                print(f"  leaf {lf['year_from']}: +{len(got)} (cum={len(listings)})", flush=True)
    listings = listings[:sample]
    rich = [li for li in listings if li.get("price") or li.get("year")]
    print(f"  enumerated {len(listings)} listings ({len(rich)} with price/year)", flush=True)

    pool = await asyncpg.create_pool(DSN, min_size=2, max_size=6)
    rdb = aioredis.from_url(REDIS)
    try:
        res = await ps.cage_platform(pool, rdb, DOMAIN, COUNTRY, listings,
                                     config_ref=CONFIG_REF, complete=False)
        api = await ps.verify_api(pool, res["ent"])
        trap = ("SRP card main-price-label = CASH price (EUR); the 'Versicherung ab .. mtl.' "
                "insurance and 'FINANZIERUNG ab ..%' financing strings are separate DOM nodes, "
                "never matched by the NN.NNN-euro price regex")
        ps.print_verdict("mobile.de suchen.mobile.de", declared=whole,
                         way2_label="per-year-sum (skipped on sample)", way2=None,
                         served=res["served"], api=api, price_trap=trap)
        print(f"  cage: new={res['new']} served={res['served']} gone={res['gone']} "
              f"(reconcile=OFF (sample))", flush=True)
    finally:
        await rdb.aclose()
        await pool.close()


async def run_full(sess, max_leaves: int) -> None:
    """Exhaustive facet sweep: build all leaves, enumerate every one via ONE Camoufox,
    cage with reconcile (complete=True). max_leaves bounds a partial run for safety."""
    whole, way2 = await count_verify(sess)
    leaves = await build_facets(sess)
    if max_leaves:
        leaves = leaves[:max_leaves]
        print(f"  (bounded to first {len(leaves)} leaves)", flush=True)

    from camoufox.async_api import AsyncCamoufox
    listings: list[dict] = []
    t0 = time.monotonic()
    async with host_budget.slot(None, "browser"):
        async with AsyncCamoufox(headless=True, geoip=False, locale="de-DE") as browser:
            page = await browser.new_page()
            for i, lf in enumerate(leaves, 1):
                if not await host_budget.wait_until_healthy(max_s=120):
                    print(f"  host pressure at leaf {i}; stopping sweep", flush=True)
                    break
                got = await enumerate_facet(page, lf)
                listings.extend(got)
                if i % 10 == 0:
                    print(f"  [{i}/{len(leaves)}] cum_listings={len(listings)} "
                          f"({int(time.monotonic()-t0)}s)", flush=True)
    # global dedupe by url
    uniq = list({li["url"]: li for li in listings}.values())
    print(f"  enumerated {len(uniq)} unique listings from {len(leaves)} leaves", flush=True)

    complete = not max_leaves                            # only a full sweep may reconcile
    pool = await asyncpg.create_pool(DSN, min_size=2, max_size=6)
    rdb = aioredis.from_url(REDIS)
    try:
        res = await ps.cage_platform(pool, rdb, DOMAIN, COUNTRY, uniq,
                                     config_ref=CONFIG_REF, complete=complete)
        api = await ps.verify_api(pool, res["ent"])
        ps.print_verdict("mobile.de suchen.mobile.de", declared=whole,
                         way2_label="per-year-sum", way2=way2,
                         served=res["served"], api=api,
                         price_trap="SRP main-price-label = CASH EUR (insurance/financing excluded)")
        print(f"  cage: new={res['new']} served={res['served']} gone={res['gone']} "
              f"(reconcile={'ON' if complete else 'OFF (bounded)'})", flush=True)
    finally:
        await rdb.aclose()
        await pool.close()


async def main(sample: int, conc: int, count_only: bool, full: bool, max_leaves: int) -> None:
    if not await host_budget.wait_until_healthy(max_s=60):
        print("HOST under pressure; aborting")
        return
    print(f"mobile.de seal | count_only={count_only} sample={sample} full={full} "
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
    ap.add_argument("--conc", type=int, default=4)
    ap.add_argument("--count-only", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--max-leaves", type=int, default=0)
    a = ap.parse_args()
    asyncio.run(main(a.sample, a.conc, a.count_only, a.full, a.max_leaves))
