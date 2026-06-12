"""Seal autoboerse.de DE used inventory — PROXY-FREE past Imperva (Chrome TLS pass-through).

autoboerse.de fronts Imperva/Incapsula (x-cdn=Imperva, incap cookie — the DOSSIER's "none" is
WRONG; T1_CENSUS's Imperva is right), but a curl_cffi Chrome136 session clears the public tier
(HTTP 200 with real ``__NEXT_DATA__`` content — verified 2026-06-12). Deep links live in the
nested sitemap (``/sitemap/autoboerse/Sitemap-Autoboerse-{1..11}.xml``, ~25k each):
  ``/fahrzeugsuche/<make>-<model>-<fuel>-<region>/<visibleId>``
Each DETAIL page's ``__NEXT_DATA__.props.pageProps.data`` carries the rich fields:
  ``price.amount`` -> CASH (EUR; the ``financing`` block is separate — trap-safe), ``mileage.amount``
  -> km, ``registration.year`` -> year, ``title``.

count_verify (>=2 ways): the search ``__NEXT_DATA__`` of /fahrzeugsuche/gebrauchtwagen carries
``classifieds.total`` (USED = ~180.7k) plus two INDEPENDENT inline partitions — ``brands[*].count``
and ``provinces[*].count`` — both summing to the GLOBAL all-vehicle total (~252.6k, == the
homepage "Treffer" counter). Reported: brand-partition-sum vs province-partition-sum (exact),
with the used subset noted.

    py -m scripts.seal_autoboerse --sample 40 [--conc 3]   # E2E proof (INSERT-only, no GONE)
    py -m scripts.seal_autoboerse --count-only             # 2-way count verify only
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
from scrapers.portals.as24_listings import extract_next_data
from scripts import platform_seal as ps

DSN = "postgresql://cardex:cardex_dev_only@localhost:5432/cardex"
REDIS = "redis://localhost:6379"
DOMAIN = "autoboerse.de"
BASE = "https://autoboerse.de"
SEARCH = "https://www.autoboerse.de/fahrzeugsuche/gebrauchtwagen"
SITEMAP_LEAF = "https://autoboerse.de/sitemap/autoboerse/Sitemap-Autoboerse-{n}.xml"
CONFIG_REF = "configs/platforms/autoboerse.json"
SLEEP = 1.2
DET = re.compile(r"<loc>(https://autoboerse\.de/fahrzeugsuche/[a-z0-9-]+/[A-Za-z0-9_-]{8,})</loc>")


async def _get(sess, url):
    return await sess.get(url, timeout=30, allow_redirects=True)


def _data(nd: dict) -> dict:
    """The detail classified lives at props.pageProps.data.classified (data also wraps
    sameDealerCars/similarCars, which must NOT be read as the subject vehicle)."""
    data = nd.get("props", {}).get("pageProps", {}).get("data", {})
    c = data.get("classified") if isinstance(data, dict) else None
    return c if isinstance(c, dict) else {}


def parse_detail(html: str, url: str) -> dict:
    d = _data(extract_next_data(html))
    price = (d.get("price") or {}).get("amount") if isinstance(d.get("price"), dict) else None
    km = (d.get("mileage") or {}).get("amount") if isinstance(d.get("mileage"), dict) else None
    year = (d.get("registration") or {}).get("year") if isinstance(d.get("registration"), dict) else None
    mk = d.get("make") or {}
    md = d.get("model") or {}
    title = d.get("title") or " ".join(str(x.get("name")) for x in (mk, md)
                                       if isinstance(x, dict) and x.get("name")).strip() or None
    return {
        "url": url,
        "title": title,
        "price": int(price) if isinstance(price, (int, float)) and price else None,
        "year": int(str(year)[:4]) if year and str(year)[:4].isdigit() else None,
        "km": int(km) if isinstance(km, (int, float)) else None,
    }


async def enumerate_sitemap(sess, want: int) -> list[str]:
    urls: list[str] = []
    n = 1
    while len(urls) < want and n <= 11:
        r = await _get(sess, SITEMAP_LEAF.format(n=n))
        if r.status_code == 200:
            for u in DET.findall(r.text or ""):
                urls.append(u)
        n += 1
        await asyncio.sleep(SLEEP)
    return urls[:want]


async def count_verify(sess) -> tuple[int | None, int | None]:
    nd = extract_next_data((await _get(sess, SEARCH)).text or "")
    pp = nd.get("props", {}).get("pageProps", {})
    used = (pp.get("classifieds") or {}).get("total")
    bsum = sum(int(b.get("count") or 0) for b in (pp.get("brands") or []) if isinstance(b, dict))
    psum = sum(int(p.get("count") or 0) for p in (pp.get("provinces") or []) if isinstance(p, dict))
    print(f"  used(classifieds.total)={used}  brand-partition-sum={bsum}  province-partition-sum={psum}")
    return bsum, psum


async def run(sample: int, conc: int, count_only: bool, full: bool, skip_count: bool) -> None:
    async with AsyncSession(impersonate="chrome136") as sess:
        if not await host_budget.wait_until_healthy(max_s=60):
            print("HOST under pressure; aborting"); return
        print(f"AUTOBOERSE seal | sample={sample} full={full} RAM={host_budget.available_mb()}MB", flush=True)

        declared = way2 = None
        if not skip_count:
            declared, way2 = await count_verify(sess)
        if count_only:
            print(f"\nBRAND-PARTITION-SUM={declared}  PROVINCE-PARTITION-SUM={way2}")
            return

        urls = await enumerate_sitemap(sess, sample)
        print(f"  enumerated {len(urls)} sitemap deep-links", flush=True)
        sem = asyncio.Semaphore(min(conc, 3))

        async def _one(u):
            async with sem:
                await host_budget.wait_until_healthy(max_s=30)
                try:
                    r = await _get(sess, u)
                    return parse_detail(r.text, u) if r.status_code == 200 else {"url": u}
                finally:
                    await asyncio.sleep(SLEEP)

        t0 = time.monotonic()
        listings = [li for li in await asyncio.gather(*(_one(u) for u in urls)) if li.get("url")]
        rich = [li for li in listings if li.get("price") or li.get("year")]
        print(f"  enriched {len(listings)} ({len(rich)} with price/year) in "
              f"{int(time.monotonic()-t0)}s", flush=True)

        pool = await asyncpg.create_pool(DSN, min_size=2, max_size=conc + 3)
        rdb = aioredis.from_url(REDIS)
        try:
            res = await ps.cage_platform(pool, rdb, DOMAIN, "DE", listings,
                                         config_ref=CONFIG_REF, complete=full)
            api = await ps.verify_api(pool, res["ent"])
            trap = "detail __NEXT_DATA__ data.price.amount = CASH (EUR); financing block separate"
            ps.print_verdict("autoboerse.de", declared=declared,
                             way2_label="province-partition-sum", way2=way2,
                             served=res["served"], api=api, price_trap=trap)
            print(f"  cage: new={res['new']} served={res['served']} gone={res['gone']} "
                  f"(reconcile={'ON' if full else 'OFF (sample)'})")
        finally:
            await rdb.aclose()
            await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=40)
    ap.add_argument("--conc", type=int, default=3)
    ap.add_argument("--count-only", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--skip-count", action="store_true")
    a = ap.parse_args()
    asyncio.run(run(a.sample, a.conc, a.count_only, a.full, a.skip_count))
