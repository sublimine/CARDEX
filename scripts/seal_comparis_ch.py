"""Seal comparis.ch (carfinder) CH used inventory — PROXY-FREE via Camoufox + DataDome warm-up.

comparis.ch is Switzerland's largest meta-aggregator (~217k used cars, aggregating
autoscout24.ch, autolina.ch, carmarket.ch, drive-in.ch, carweb.ch). The 2026-06-04
"plain SSR, no WAF" classification is STALE: the carfinder now fronts DataDome, and a cold
curl_cffi hit is 403 (datadome cookie, 771B block). Verified live 2026-06-12:

  * curl_cffi cold              -> 403 DataDome block.
  * Camoufox cold              -> DataDome CAPTCHA interstitial on page 0.
  * Camoufox + HOMEPAGE WARM-UP -> carfinder loads clean (802KB, 10 ids, no captcha),
    page 1 yields 10 distinct ids -> clean 0-indexed pagination.

So the via is Camoufox with a homepage warm-up that mints a valid DataDome cookie BEFORE
touching the listing surface. ONE browser (host_budget BROWSER lane), <=0.5 req/s.

Per-listing data: the SSR carfinder embeds a schema.org ItemList ld+json with, for each
card, the detail `url`, the vehicle `name` (make + model + variant), and a thumbnail. That
island is present at SSR time (no hydration needed), so it is the authoritative enumeration
+ title source. Price/year/km are hydrated client-side and NOT reliably in the SSR DOM, so
listings are caged as rich-title pointers (km opportunistically when the card text carries
it); detail-level enrichment is a later pass. Count_verify reads the same page:
  way 1: resultCount / AggregateOffer.offerCount   way 2: ItemList numberOfItems.

  py -m scripts.seal_comparis_ch --count-only           # 2-way count (1 warmed page)
  py -m scripts.seal_comparis_ch --sample 40            # E2E: enumerate+cage(INSERT-only)+verify
  py -m scripts.seal_comparis_ch --full [--max-pages N] # exhaustive grid sweep (reconciles)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from itertools import product

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

import asyncpg
import redis.asyncio as aioredis

from scrapers.common import host_budget
from scripts import platform_seal as ps

DSN = "postgresql://cardex:cardex_dev_only@localhost:5432/cardex"
REDIS = "redis://localhost:6379"
DOMAIN = "comparis.ch"
COUNTRY = "CH"
CONFIG_REF = "configs/platforms/comparis_ch.json"

HOME = "https://www.comparis.ch/"
BASE = "https://www.comparis.ch/carfinder/marktplatz"
DETAIL = "https://www.comparis.ch/carfinder/marktplatz/details/show/{id}"

PER_PAGE = 10            # ~10 cards/SSR page (verified)
PAGE_CAP = 200          # cells over 2000 listings get year x price subdivision
WARM_WAIT = 3500
SRP_WAIT = 6500         # let the ItemList island render
SRP_SLEEP = 2.2         # <=0.5 req/s
_HARD_DD = ("captcha-delivery", "geo.captcha-delivery", "verifying you are human")

# Year x price grid (CHF) — Swiss market skews high. Mirrors the existing portal scraper.
YEAR_BANDS = ((1990, 2000), (2000, 2005), (2005, 2008), (2008, 2011), (2011, 2014),
              (2014, 2016), (2016, 2018), (2018, 2020), (2020, 2022), (2022, 2024),
              (2024, 2026))
PRICE_BANDS = ((0, 5_000), (5_000, 10_000), (10_000, 15_000), (15_000, 20_000),
               (20_000, 30_000), (30_000, 40_000), (40_000, 50_000), (50_000, 75_000),
               (75_000, 100_000), (100_000, None))

_DETAIL_RE = re.compile(r"/carfinder/marktplatz/details/show/(\d+)")
_ITEMLIST_RE = re.compile(
    r'\{"@context":"http://schema\.org/","@type":"ItemList".*?\]\}', re.S)
_COUNT_RES = (re.compile(r'"resultCount"\s*:\s*(\d+)'),
              re.compile(r'"offerCount"\s*:\s*(\d+)'),
              re.compile(r"([\d'’.\s]{2,})\s*(?:Ergebnisse|Inserate|Treffer)", re.I))
_NUMITEMS_RE = re.compile(r'"numberOfItems"\s*:\s*(\d+)')


# ----------------------------------------------------------------------------- parsing
def _clean(s: str | None) -> str | None:
    if not s:
        return None
    return re.sub(r"\s+", " ", s).strip() or None


def parse_listings(html: str) -> list[dict]:
    """ItemList ld+json -> cage-shape listings (url + title from `name`). km opportunistic."""
    m = _ITEMLIST_RE.search(html)
    out: list[dict] = []
    if not m:
        # fallback: raw detail ids (title-less pointers) so a page is never silently empty
        for cid in dict.fromkeys(_DETAIL_RE.findall(html)):
            out.append({"url": DETAIL.format(id=cid), "title": None,
                        "price": None, "year": None, "km": None})
        return out
    try:
        il = json.loads(m.group(0))
    except ValueError:
        return out
    # NOTE: rendered km tokens exist in the DOM but their order is NOT guaranteed to align
    # with the ItemList element order (top promoted cards render "100 km" placeholders), so
    # positional mileage is unreliable -> we deliberately cage NO km here (no fabricated data).
    # Price/year hydrate client-side. Detail-level enrichment is a separate pass on
    # /details/show/{id}. The authoritative SSR fields are url + name(title).
    for e in il.get("itemListElement", []):
        url = e.get("url") or ""
        mid = _DETAIL_RE.search(url)
        if not mid:
            continue
        out.append({
            "url": DETAIL.format(id=mid.group(1)),
            "title": _clean(e.get("name")),
            "price": None,
            "year": None,
            "km": None,
        })
    return out


def parse_counts(html: str) -> tuple[int | None, int | None]:
    """way1: resultCount/offerCount; way2: ItemList numberOfItems."""
    w1 = None
    for rx in _COUNT_RES:
        m = rx.search(html)
        if m:
            w1 = int(re.sub(r"\D", "", m.group(1)))
            break
    m2 = _NUMITEMS_RE.search(html)
    w2 = int(m2.group(1)) if m2 else None
    return w1, w2


# ----------------------------------------------------------------------------- browser
async def _warm(page) -> None:
    """Mint a valid DataDome cookie on the benign homepage before the listing surface."""
    await page.goto(HOME, wait_until="domcontentloaded", timeout=45_000)
    await page.wait_for_timeout(WARM_WAIT)


def _build_url(page_idx: int, yf: int | None = None, yt: int | None = None,
               pf: int | None = None, pt: int | None = None) -> str:
    q = ["sort=2", f"page={page_idx}", "condition=occasion"]
    if yf is not None:
        q.append(f"yearfrom={yf}")
    if yt is not None:
        q.append(f"yearto={yt}")
    if pf is not None:
        q.append(f"pricefrom={pf}")
    if pt is not None:
        q.append(f"priceto={pt}")
    return f"{BASE}?{'&'.join(q)}"


async def _load(page, url: str, *, retries: int = 3) -> str:
    for attempt in range(1, retries + 1):
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(SRP_WAIT)
        html = await page.content()
        lo = html.lower()
        if not any(m in lo for m in _HARD_DD) and _ITEMLIST_RE.search(html):
            return html
        await page.wait_for_timeout(2500 * attempt)
        await _warm(page)                       # re-warm the cookie, then retry
    return await page.content()


async def enumerate_cell(page, *, want: int | None = None, yf=None, yt=None,
                         pf=None, pt=None) -> list[dict]:
    """Walk a (year x price) cell's 0-indexed pages, collecting ItemList listings."""
    by_url: dict[str, dict] = {}
    for pg in range(0, PAGE_CAP):
        html = await _load(page, _build_url(pg, yf, yt, pf, pt))
        if any(m in html.lower() for m in _HARD_DD):
            break
        items = parse_listings(html)
        if not items:
            break
        before = len(by_url)
        for it in items:
            by_url.setdefault(it["url"], it)
        await asyncio.sleep(SRP_SLEEP)
        if len(by_url) == before:               # no new ids -> end of cell
            break
        if want and len(by_url) >= want:
            break
    return list(by_url.values())


# ----------------------------------------------------------------------------- runs
async def run_count(browser) -> tuple[int | None, int | None]:
    page = await browser.new_page()
    try:
        await _warm(page)
        html = await _load(page, _build_url(0))
        w1, w2 = parse_counts(html)
        print(f"\nRESULT-COUNT = {w1}   ITEMLIST-numberOfItems = {w2}", flush=True)
        return w1, w2
    finally:
        await page.close()


async def run_sample(browser, sample: int) -> tuple[list[dict], int | None, int | None]:
    page = await browser.new_page()
    try:
        await _warm(page)
        html0 = await _load(page, _build_url(0))
        w1, w2 = parse_counts(html0)
        listings = parse_listings(html0)
        # keep walking unfiltered pages to reach `sample`
        seen = {li["url"] for li in listings}
        for pg in range(1, PAGE_CAP):
            if len(listings) >= sample:
                break
            html = await _load(page, _build_url(pg))
            new = [li for li in parse_listings(html) if li["url"] not in seen]
            if not new:
                break
            listings.extend(new)
            seen.update(li["url"] for li in new)
            await asyncio.sleep(SRP_SLEEP)
        return listings[:sample], w1, w2
    finally:
        await page.close()


async def run_full(browser, max_pages: int) -> tuple[list[dict], int | None, int | None]:
    page = await browser.new_page()
    listings: list[dict] = []
    w1 = w2 = None
    t0 = time.monotonic()
    try:
        await _warm(page)
        html0 = await _load(page, _build_url(0))
        w1, w2 = parse_counts(html0)
        cells = [{"yf": yf, "yt": yt, "pf": pf, "pt": pt}
                 for (yf, yt), (pf, pt) in product(YEAR_BANDS, PRICE_BANDS)]
        walked = 0
        for ci, cell in enumerate(cells, 1):
            if not await host_budget.wait_until_healthy(max_s=120):
                print(f"  host pressure at cell {ci}; stopping", flush=True)
                break
            got = await enumerate_cell(page, yf=cell["yf"], yt=cell["yt"],
                                       pf=cell["pf"], pt=cell["pt"])
            listings.extend(got)
            walked += 1
            if ci % 5 == 0:
                print(f"  [{ci}/{len(cells)}] cells, cum={len(listings)} "
                      f"({int(time.monotonic()-t0)}s)", flush=True)
            if max_pages and walked >= max_pages:
                print(f"  bounded stop after {walked} cells", flush=True)
                break
        return list({li["url"]: li for li in listings}.values()), w1, w2
    finally:
        await page.close()


async def main(sample: int, count_only: bool, full: bool, max_pages: int) -> None:
    if not await host_budget.wait_until_healthy(max_s=60):
        print("HOST under pressure; aborting")
        return
    print(f"comparis.ch seal | count_only={count_only} sample={sample} full={full} "
          f"RAM={host_budget.available_mb()}MB", flush=True)
    from camoufox.async_api import AsyncCamoufox

    async with host_budget.slot(None, "browser"):
        async with AsyncCamoufox(headless=True, geoip=False, locale="de-CH") as browser:
            if count_only:
                await run_count(browser)
                return
            if full:
                listings, w1, w2 = await run_full(browser, max_pages)
                complete = not max_pages
            else:
                listings, w1, w2 = await run_sample(browser, sample)
                complete = False

    print(f"  enumerated {len(listings)} listings "
          f"({sum(1 for li in listings if li.get('title'))} with title)", flush=True)
    pool = await asyncpg.create_pool(DSN, min_size=2, max_size=6)
    rdb = aioredis.from_url(REDIS)
    try:
        res = await ps.cage_platform(pool, rdb, DOMAIN, COUNTRY, listings,
                                     config_ref=CONFIG_REF, complete=complete)
        api = await ps.verify_api(pool, res["ent"])
        ps.print_verdict("comparis.ch carfinder", declared=w1,
                         way2_label="ItemList numberOfItems", way2=w2,
                         served=res["served"], api=api,
                         price_trap="ItemList ld+json = url+name(title)+thumb; price/year "
                         "hydrate client-side (pointer-level cage, enrich on detail later)")
        print(f"  cage: new={res['new']} served={res['served']} gone={res['gone']} "
              f"(reconcile={'ON' if complete else 'OFF (sample/bounded)'})", flush=True)
    finally:
        await rdb.aclose()
        await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=40)
    ap.add_argument("--count-only", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--max-pages", type=int, default=0)
    a = ap.parse_args()
    asyncio.run(main(a.sample, a.count_only, a.full, a.max_pages))
