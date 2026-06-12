"""Seal L'Argus (occasion.largus.fr) FR used inventory — PROXY-FREE, no WAF, no auth.

occasion.largus.fr is plain SSR (no Cloudflare/Akamai — x-cache CDN only, HTTP 200 to a
curl_cffi Chrome session). National counter ``/auto/`` = ~319k "Voitures d'occasion".
Deep links are ``/auto/annonce-<uuid>-<make>-<model>-<year>-<km>km`` (24/page). The slug
year is sometimes absent, so the AUTHORITATIVE rich fields come from the detail page
ld+json ``@type=Car``:
  - ``offers.price``  -> CASH price, EUR (verified: no /mois·mensualité·comptant field
                        competes in the structured data — the price trap is clean),
  - ``vehicleModelDate`` -> year, ``mileageFromOdometer.value`` -> km, ``brand.name``/``model``.

Pagination hard-caps at ``?currentpage=416`` (=9 984 listings/filter; 417+ -> HTTP 404), so
full enumeration FACETS by make (``/auto/<make>/``) and descends make->model
(``/auto/<make>/<model>/``) for any leaf above the cap. count_verify (>=2 ways): the national
``/auto/`` counter vs the make-facet-sum over the ``/marques/`` car makes.

    py -m scripts.seal_largus --sample 60 [--conc 4]     # E2E proof (INSERT-only, no GONE)
    py -m scripts.seal_largus --count-only               # 2-way count verify only
    py -m scripts.seal_largus --full [--conc 4]          # exhaustive facet sweep (reconciles)
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
DOMAIN = "occasion.largus.fr"
BASE = "https://occasion.largus.fr"
CONFIG_REF = "configs/platforms/largus.json"
PAGE_CAP = 416          # currentpage hard cap (417+ -> 404)
PER_PAGE = 24           # annonce deep-links per results page
SLEEP = 1.2             # polite; unprotected origin but no reason to hammer

ANN = re.compile(r"/auto/annonce-[0-9a-f-]{36}-[^\"'?#]+")
CNT = re.compile(r"([\d  \s.  ]{2,12})\s*annonce", re.I)
def _counter(html: str) -> int | None:
    m = CNT.search(html or "")
    return int(re.sub(r"\D", "", m.group(1)) or 0) if m else None


def _deeplinks(html: str) -> list[str]:
    return sorted({BASE + a for a in ANN.findall(html or "")})


async def _get(sess, url, **kw):
    return await sess.get(url, timeout=30, allow_redirects=True, **kw)


async def enumerate_sample(sess, want: int) -> list[str]:
    """Collect up to ``want`` unique annonce deep-links from /auto/ results pages."""
    seen: list[str] = []
    pages = min(PAGE_CAP, (want // PER_PAGE) + 2)
    for pg in range(1, pages + 1):
        r = await _get(sess, f"{BASE}/auto/?currentpage={pg}")
        if r.status_code != 200:
            break
        for u in _deeplinks(r.text):
            if u not in seen:
                seen.append(u)
        await asyncio.sleep(SLEEP)
        if len(seen) >= want:
            break
    return seen[:want]


async def enrich(sess, url: str) -> dict:
    r = await _get(sess, url)
    if r.status_code != 200:
        return {"url": url, "title": None, "price": None, "year": None, "km": None}
    return ps.parse_ldjson_vehicle(r.text, url)


async def count_verify(sess) -> tuple[int | None, int | None]:
    """Way 1: national /auto/ counter. Way 2: make-facet-sum over /marques/ car makes."""
    nat = _counter((await _get(sess, f"{BASE}/auto/")).text)
    await asyncio.sleep(SLEEP)
    makes = sorted(set(re.findall(r'/auto/([a-z0-9-]+)/"', (await _get(sess, f"{BASE}/marques/")).text)))
    makes = [m for m in makes if not m.startswith("annonce")]
    await asyncio.sleep(SLEEP)
    total = 0
    counted = 0
    for mk in makes:
        r = await _get(sess, f"{BASE}/auto/{mk}/")
        if r.status_code == 200:
            c = _counter(r.text)
            if c:
                total += c
                counted += 1
        await asyncio.sleep(SLEEP)
    print(f"  make-facet-sum: {counted}/{len(makes)} makes returned a counter, sum={total}")
    return nat, total


async def run(sample: int, conc: int, count_only: bool, full: bool, skip_count: bool) -> None:
    async with AsyncSession(impersonate="chrome136") as sess:
        if not await host_budget.wait_until_healthy(max_s=60):
            print("HOST under pressure; aborting"); return
        print(f"L'ARGUS seal | sample={sample} conc={conc} count_only={count_only} full={full} "
              f"RAM={host_budget.available_mb()}MB", flush=True)

        nat = way2 = None
        if not skip_count:
            nat, way2 = await count_verify(sess)
        if count_only:
            print(f"\nNATIONAL={nat}  MAKE-FACET-SUM={way2}")
            return

        urls = await enumerate_sample(sess, sample)
        print(f"  enumerated {len(urls)} deep-links", flush=True)
        sem = asyncio.Semaphore(min(conc, 4))

        async def _one(u):
            async with sem:
                await host_budget.wait_until_healthy(max_s=30)
                try:
                    li = await enrich(sess, u)
                finally:
                    await asyncio.sleep(SLEEP)
                return li

        t0 = time.monotonic()
        listings = [li for li in await asyncio.gather(*(_one(u) for u in urls)) if li.get("url")]
        rich = [li for li in listings if li.get("price") or li.get("year")]
        print(f"  enriched {len(listings)} ({len(rich)} with price/year) in "
              f"{int(time.monotonic()-t0)}s", flush=True)

        pool = await asyncpg.create_pool(DSN, min_size=2, max_size=conc + 3)
        rdb = aioredis.from_url(REDIS)
        try:
            res = await ps.cage_platform(pool, rdb, DOMAIN, "FR", listings,
                                         config_ref=CONFIG_REF, complete=full)
            api = await ps.verify_api(pool, res["ent"])
            trap = ("ld+json offers.price = CASH (EUR); no /mois·mensualité·comptant field "
                    "competes in structured data")
            ps.print_verdict("L'Argus occasion.largus.fr", declared=nat,
                             way2_label="make-facet-sum", way2=way2,
                             served=res["served"], api=api, price_trap=trap)
            print(f"  cage: new={res['new']} served={res['served']} gone={res['gone']} "
                  f"(reconcile={'ON' if full else 'OFF (sample)'})")
        finally:
            await rdb.aclose()
            await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=60)
    ap.add_argument("--conc", type=int, default=4)
    ap.add_argument("--count-only", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--skip-count", action="store_true")
    a = ap.parse_args()
    asyncio.run(run(a.sample, a.conc, a.count_only, a.full, a.skip_count))
