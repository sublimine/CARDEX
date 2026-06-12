"""Seal Kleinanzeigen (kleinanzeigen.de) DE used cars — PROXY-FREE past Akamai BM (Chrome TLS).

kleinanzeigen.de/s-autos/c216 is SSR HTML behind Akamai Bot Manager, but a curl_cffi Chrome136
session clears the public tier (HTTP 200, no 403 — verified 2026-06-12). Each result CARD (a
``data-adid`` block) carries everything inline (no per-detail fetch):
  - deep link ``/s-anzeige/<slug>/<id>``, title (embedded ``"title":``),
  - price element ``price-shipping--price`` -> CASH € (the trailing "VB" = Verhandlungsbasis /
    negotiable is a FLAG, not a different price; C2C, so no monthly-financing trap),
  - ``simpletag`` tags: ``NNN km`` -> km and ``EZ MM/YYYY`` (Erstzulassung) -> year.
Counter: ``... von 784.646 Gebrauchtwagen``. Pagination ``/s-autos/seite:N/c216`` (25/page; deep
offset truncates), so full enumeration FACETS by brand subcategory ``/s-autos/<brand>/c216``.

count_verify (>=2 ways): the ``von N Gebrauchtwagen`` national counter vs the price-band-sum
(``/s-autos/preis:LO:HI/c216`` over a complete price partition — the SRP brand links are NOT a
clean partition; they overshoot).

    py -m scripts.seal_kleinanzeigen --sample 60        # E2E proof (INSERT-only, no GONE)
    py -m scripts.seal_kleinanzeigen --count-only        # 2-way count verify only
    py -m scripts.seal_kleinanzeigen --full              # exhaustive facet sweep (reconciles)
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
DOMAIN = "kleinanzeigen.de"
BASE = "https://www.kleinanzeigen.de"
CONFIG_REF = "configs/platforms/kleinanzeigen.json"
SLEEP = 1.5            # Akamai — pace conservatively

DET = re.compile(r"/s-anzeige/[a-z0-9-]+/\d+-\d+-\d+")
PRICE_TXT = re.compile(r"price-shipping--price\"[^>]*>\s*([0-9.]+)\s*€")
TAG = re.compile(r"simpletag[^>]*>([^<]+)<")
TITLE = re.compile(r'"title":"([^"]+)"')
COUNTER = re.compile(r"von\s*([0-9.]+)\s*Gebrauchtwagen")
# Price bands are a clean COMPLETE partition (the brand links on the SRP are not — they mix in
# broad/overlapping facets that overshoot). Open-ended top band has empty HI.
PRICE_BANDS = [(0, 2500), (2500, 5000), (5000, 10000), (10000, 20000),
               (20000, 40000), (40000, 80000), (80000, None)]


def _counter(html: str) -> int | None:
    m = COUNTER.search(html or "")
    return int(m.group(1).replace(".", "")) if m else None


def parse_cards(html: str) -> list[dict]:
    blocks = re.split(r'data-adid="(\d+)"', html or "")
    out, seen = [], set()
    for k in range(1, len(blocks) - 1, 2):
        block = blocks[k + 1][:9000]
        dm = DET.search(block)
        if not dm:
            continue
        url = BASE + dm.group(0)
        if url in seen:
            continue
        seen.add(url)
        pm = PRICE_TXT.search(block)
        price = int(pm.group(1).replace(".", "")) if pm else None
        year = km = None
        for t in TAG.findall(block):
            t = t.strip()
            if t.endswith("km"):
                km = int(re.sub(r"\D", "", t) or 0) or None
            elif "EZ" in t:
                ym = re.search(r"(19[89]\d|20[0-2]\d)", t)
                if ym:
                    year = int(ym.group(1))
        tm = TITLE.search(block)
        out.append({"url": url, "title": tm.group(1)[:120] if tm else None,
                    "price": price if price and price > 50 else None, "year": year, "km": km})
    return out


async def _get(sess, url):
    return await sess.get(url, timeout=30, allow_redirects=True)


async def harvest_sample(sess, want: int) -> list[dict]:
    listings, seen = [], set()
    page = 1
    while len(listings) < want and page <= 50:
        url = f"{BASE}/s-autos/c216" if page == 1 else f"{BASE}/s-autos/seite:{page}/c216"
        r = await _get(sess, url)
        if r.status_code != 200:
            break
        for c in parse_cards(r.text):
            if c["url"] not in seen:
                seen.add(c["url"])
                listings.append(c)
        page += 1
        await asyncio.sleep(SLEEP)
    return listings[:want]


async def count_verify(sess) -> tuple[int | None, int | None]:
    declared = _counter((await _get(sess, f"{BASE}/s-autos/c216")).text or "")
    await asyncio.sleep(SLEEP)
    total = 0
    parts = []
    for lo, hi in PRICE_BANDS:
        url = f"{BASE}/s-autos/preis:{lo}:{hi if hi else ''}/c216"
        c = _counter((await _get(sess, url)).text or "")
        if c:
            total += c
            parts.append(f"{lo}-{hi or ''}:{c}")
        await asyncio.sleep(SLEEP)
    print(f"  price-band-sum: {' '.join(parts)} -> {total}")
    return declared, total


async def run(sample: int, count_only: bool, full: bool, skip_count: bool) -> None:
    async with AsyncSession(impersonate="chrome136") as sess:
        if not await host_budget.wait_until_healthy(max_s=60):
            print("HOST under pressure; aborting"); return
        print(f"KLEINANZEIGEN seal | sample={sample} full={full} "
              f"RAM={host_budget.available_mb()}MB", flush=True)

        declared = way2 = None
        if not skip_count:
            declared, way2 = await count_verify(sess)
        if count_only:
            print(f"\nDECLARED={declared}  PRICE-BAND-SUM={way2}")
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
            trap = "card price-shipping--price = CASH EUR (trailing 'VB'=negotiable flag; C2C, no financing)"
            ps.print_verdict("Kleinanzeigen kleinanzeigen.de", declared=declared,
                             way2_label="price-band-sum", way2=way2,
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
