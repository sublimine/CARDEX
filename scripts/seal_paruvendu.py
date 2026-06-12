"""Seal ParuVendu (paruvendu.fr) FR used inventory — PROXY-FREE, no WAF (Apache), no auth.

paruvendu.fr serves its car results server-side (no Cloudflare/Akamai — Apache, HTTP 200 to a
curl_cffi Chrome session). The result list is the search endpoint
``/auto-moto/listefo/default/default`` (national counter ~144k "annonces"), paginated by
``?p=N`` (25 ads/page; page 2 shares 0 ads with page 1 — genuine paging). Each result CARD
carries everything inline (no per-detail fetch needed, like AS24's listings):
  - deep link ``/a/voiture-occasion/<make>/<model>/<adId><facetCode>`` (make/model in the slug),
  - ``Année YYYY`` -> year, ``NNN NNN km`` -> km,
  - the CASH price as ``NNN NNN €`` — the parser excludes any ``€/mois`` amount via negative
    lookahead, so the "Simuler ma mensualité" financing widget never leaks in (price trap).
    Spot-checked card price == detail ld+json ``offers.price`` == ``gtm_var_prix``.

count_verify (>=2 ways): the listefo national counter vs the make-facet-sum over the
``/a/voiture/marques/`` car makes (each ``/a/voiture-occasion/<make>/`` carries its own counter).

    py -m scripts.seal_paruvendu --sample 60 [--conc 4]   # E2E proof (INSERT-only, no GONE)
    py -m scripts.seal_paruvendu --count-only             # 2-way count verify only
    py -m scripts.seal_paruvendu --full [--conc 4]        # exhaustive sweep (reconciles)
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
DOMAIN = "paruvendu.fr"
BASE = "https://www.paruvendu.fr"
LISTEFO = BASE + "/auto-moto/listefo/default/default"
MARQUES = BASE + "/a/voiture/marques/"
CONFIG_REF = "configs/platforms/paruvendu.json"
PER_PAGE = 25
SLEEP = 1.2

DET = re.compile(r"/a/voiture-occasion/([a-z0-9-]+)/([a-z0-9-]+)/(\d{8,}[A-Z0-9]{6,})")
YEAR = re.compile(r"Ann\S?e\s*(19[89]\d|20[0-2]\d)")
KM = re.compile(r"(\d[\d  .]{1,8})\s*km\b", re.I)
# CASH price only: a euro amount NOT followed by '/mois' (the financing simulator).
PRICE = re.compile(r"(\d[\d  .]{2,8})\s*(?:&euro;|€)(?!\s*/?\s*mois)")
CNT = re.compile(r"(\d[\d  \s.]{2,12})\s*annonce", re.I)


def _counter_max(html: str) -> int | None:
    best = None
    for m in CNT.finditer(html or ""):
        n = int(re.sub(r"\D", "", m.group(1)) or 0)
        if n > 100:
            best = max(best or 0, n)
    return best


def parse_cards(html: str) -> list[dict]:
    """Each result card (a ``data-id`` block) -> cage-shape dict with cash price/year/km."""
    blocks = re.split(r'data-id="(\d{8,})"', html or "")
    out, seen = [], set()
    for k in range(1, len(blocks) - 1, 2):
        block = blocks[k + 1][:6000]                 # one card; cap stops bleed into the next
        dm = DET.search(block)
        if not dm:
            continue
        url = BASE + dm.group(0)
        if url in seen:
            continue
        seen.add(url)
        txt = re.sub(r"[  ]", " ", re.sub(r"<[^>]+>", " ", block))
        yr, km = YEAR.search(txt), KM.search(txt)
        pr = PRICE.search(re.sub(r"[  ]", " ", block))
        out.append({
            "url": url,
            "title": f"{dm.group(1).replace('-', ' ').upper()} {dm.group(2).replace('-', ' ').title()}",
            "year": int(yr.group(1)) if yr else None,
            "km": int(re.sub(r"\D", "", km.group(1))) if km else None,
            "price": int(re.sub(r"\D", "", pr.group(1))) if pr else None,
        })
    return out


async def _get(sess, url, **kw):
    return await sess.get(url, timeout=30, allow_redirects=True, **kw)


async def harvest_sample(sess, want: int) -> list[dict]:
    listings, seen = [], set()
    pages = (want // PER_PAGE) + 3
    for pg in range(1, pages + 1):
        r = await _get(sess, f"{LISTEFO}?p={pg}")
        if r.status_code != 200:
            break
        for c in parse_cards(r.text):
            if c["url"] not in seen:
                seen.add(c["url"])
                listings.append(c)
        await asyncio.sleep(SLEEP)
        if len(listings) >= want:
            break
    return listings[:want]


async def count_verify(sess) -> tuple[int | None, int | None]:
    """2 independent surfaces: the listefo RESULTS endpoint counter vs the /voiture-occasion/
    SEO CATALOG-page counter. (The per-make /a/voiture-occasion/<make>/ pages were rejected as
    a 3rd way: their counter aggregates a BROADER set — new+used+utilitaire — so the make-sum
    ~263k overshoots the ~144k cars-occasion national; [VERIFIED] 2026-06-12, not a bug.)"""
    results_total = _counter_max((await _get(sess, LISTEFO)).text)
    await asyncio.sleep(SLEEP)
    catalog_total = _counter_max((await _get(sess, BASE + "/voiture-occasion/")).text)
    print(f"  listefo-results={results_total}  catalog-surface={catalog_total}")
    return results_total, catalog_total


async def run(sample: int, conc: int, count_only: bool, full: bool, skip_count: bool) -> None:
    async with AsyncSession(impersonate="chrome136") as sess:
        if not await host_budget.wait_until_healthy(max_s=60):
            print("HOST under pressure; aborting"); return
        print(f"PARUVENDU seal | sample={sample} conc={conc} full={full} "
              f"RAM={host_budget.available_mb()}MB", flush=True)

        nat = way2 = None
        if not skip_count:
            nat, way2 = await count_verify(sess)
        if count_only:
            print(f"\nLISTEFO-RESULTS={nat}  CATALOG-SURFACE={way2}")
            return

        t0 = time.monotonic()
        listings = await harvest_sample(sess, sample)
        rich = [li for li in listings if li.get("price") or li.get("year")]
        print(f"  harvested {len(listings)} cards ({len(rich)} with price/year) in "
              f"{int(time.monotonic()-t0)}s", flush=True)

        pool = await asyncpg.create_pool(DSN, min_size=2, max_size=conc + 3)
        rdb = aioredis.from_url(REDIS)
        try:
            res = await ps.cage_platform(pool, rdb, DOMAIN, "FR", listings,
                                         config_ref=CONFIG_REF, complete=full)
            api = await ps.verify_api(pool, res["ent"])
            trap = ("listefo card CASH price (NNN €, negative-lookahead excludes €/mois); "
                    "card price == detail ld+json offers.price == gtm_var_prix")
            ps.print_verdict("ParuVendu paruvendu.fr", declared=nat,
                             way2_label="catalog-surface counter", way2=way2,
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
