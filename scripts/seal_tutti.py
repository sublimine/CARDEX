"""Seal tutti.ch (CH) Autos used inventory — PROXY-FREE, Cloudflare pass-through, no auth.

tutti.ch is Switzerland's largest classifieds site. The Autos vertical is a Next.js SSR
surface: a curl_cffi Chrome session gets HTTP 200 (Cloudflare is pass-through to a Chrome
UA, NO JS challenge — verified live 2026-06-12). Every listing page embeds a
``<script id="__NEXT_DATA__">`` whose React-Query ``dehydratedState`` carries the
``SearchListingsByConstraints`` result:

  props.pageProps.dehydratedState.queries[?key[0]=="SearchListingsByConstraints"].state.data
    -> listings.totalCount        (the count oracle, scoped to the selected category)
    -> listings.edges[].node      (30/page: listingID, title, formattedPrice, canton, deSlug)
    -> selectedCategory.categoryID  ("cars" == Autos — the scope guard)

SCOPE GUARD (the all-categories trap): the bare ``/de/q/autos/<token>`` token resolves to
``selectedCategory.categoryID == "cars"`` with totalCount ~84.7K. A token-less / generic
search resolves to selectedCategory=None and totalCount ~2.18M (ALL categories — the
2.19M dossier figure). Every parse asserts categoryID=="cars" before trusting a count, so a
silent fallback to all-categories can never be counted as Autos.

RESULT-WINDOW CAP + FACET: a single search serves ~150 pages (30/page ≈ 4.5K) before tutti
hard-redirects (HTTP 307 -> /de/q, category dropped). 84.7K Autos therefore needs faceting.
The page itself hands us the partition: ``seoInformation.linkSections`` has a
"Wähle einen Kanton:" section with one {slug, searchToken} per canton (26 CH cantons + FL).
Each canton search keeps categoryID=="cars" with its own (smaller) window.

count_verify (>=2 ways):
  way 1 (declared) = ``listings.totalCount`` on the all-Switzerland Autos search.
  way 2 (facet)    = sum of ``listings.totalCount`` over the 27 per-canton Autos searches.
  (live 2026-06-12: 84.673 vs 84.721 == 99.94% agreement.)

price trap: ``edge.node.formattedPrice`` ("65'900.-") is the CASH ask in CHF (Swiss
apostrophe thousands sep, ".-" suffix). The detail page's ``seoInformation.numericPrice``
equals it (65900) and there is NO lease/monthly field on a tutti car listing — so the SSR
formattedPrice is trap-safe. Currency is stamped CHF by the cage (country_currency("CH")).

    py -m scripts.seal_tutti --count-only          # 2-way count (all-CH + 27 canton facets)
    py -m scripts.seal_tutti --sample 60 [--conc 1]  # E2E proof (INSERT-only, no GONE)
    py -m scripts.seal_tutti --full [--max-pages N]  # exhaustive per-canton sweep (reconciles)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time

import asyncpg
import redis.asyncio as aioredis
from curl_cffi.requests import AsyncSession

from scrapers.common import host_budget
from scripts import platform_seal as ps

# Windows proactor loop + UTF-8 stdout (Swiss titles carry ü/ä/é; platform_seal also repairs).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

DSN = "postgresql://cardex:cardex_dev_only@localhost:5432/cardex"
REDIS = "redis://localhost:6379"
DOMAIN = "tutti.ch"
COUNTRY = "CH"
CONFIG_REF = "configs/platforms/tutti.json"
BASE = "https://www.tutti.ch"

# All-Switzerland Autos search (categoryID=="cars"). The token is stable across buildIds
# (it encodes the category, not a buildId), but we ALSO re-read the live canton partition
# from the page so a token rotation degrades to "fewer facets", never to wrong data.
AUTOS_SLUG = "autos"
AUTOS_TOKEN = "Ak8CkY2Fyc5TAwMDA"

PER_PAGE = 30
PAGE_CAP = 150            # empirical result-window before the 307 -> /de/q category drop
SLEEP = 0.6              # polite; tutti is pass-through, no ban pressure observed
CARS_CATEGORY = "cars"   # selectedCategory.categoryID that means "Autos" (the scope guard)

_ND = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


async def _get(sess, url, **kw):
    return await sess.get(url, timeout=30, allow_redirects=True, **kw)


def _next_data(html: str) -> dict | None:
    m = _ND.search(html or "")
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def _search_data(nd: dict | None) -> dict | None:
    """props.pageProps.dehydratedState.queries[SearchListingsByConstraints].state.data.

    Returns None if the search query is absent (e.g. a 307-redirect payload), so callers
    fail closed rather than reading a stale/blank shape."""
    if not nd:
        return None
    queries = (((nd.get("props") or {}).get("pageProps") or {})
               .get("dehydratedState") or {}).get("queries") or []
    for q in queries:
        key = q.get("queryKey") or []
        if key and key[0] == "SearchListingsByConstraints":
            return ((q.get("state") or {}).get("data")) or None
    return None


def _is_cars(data: dict | None) -> bool:
    """Scope guard: the search MUST be the Autos category, not the all-categories fallback."""
    if not data:
        return False
    sc = data.get("selectedCategory") or {}
    return isinstance(sc, dict) and sc.get("categoryID") == CARS_CATEGORY


_PRICE = re.compile(r"\d")


def _parse_price(formatted: str | None) -> int | None:
    """"65'900.-" / "3'900.-" -> 65900 / 3900 (CHF cash). Strips Swiss apostrophe + ".-".
    Drops anything with no digits (e.g. "Auf Anfrage" / None)."""
    if not formatted or not _PRICE.search(formatted):
        return None
    # The "-" after the decimal point is a Swiss "no centimes" marker, not part of the int.
    head = formatted.split(".")[0]
    digits = re.sub(r"\D", "", head)
    return int(digits) if digits else None


def parse_edges(data: dict) -> list[dict]:
    """listings.edges[].node -> cage-shape dicts. URL from seoInformation.deSlug under /de/vi/
    + listingID (the verified detail pattern). Only category=="cars" nodes are kept."""
    out: list[dict] = []
    listings = data.get("listings") or {}
    for e in listings.get("edges") or []:
        node = e.get("node") or {}
        lid = node.get("listingID")
        if not lid:
            continue
        # Per-node category guard: drop any non-car node (promoted/placement bleed-through).
        pc = (node.get("primaryCategory") or {}).get("categoryID")
        if pc and pc != CARS_CATEGORY:
            continue
        seo = node.get("seoInformation") or {}
        slug = seo.get("deSlug")
        url = f"{BASE}/de/vi/{slug}/{lid}" if slug else f"{BASE}/de/vi/{lid}"
        out.append({
            "url": url,
            "title": node.get("title") or None,
            "price": _parse_price(node.get("formattedPrice")),
            "year": None,   # not in the SSR card; enrich-on-detail later (numericPrice page)
            "km": None,
        })
    return out


def _total_count(data: dict | None) -> int | None:
    if not data:
        return None
    return (data.get("listings") or {}).get("totalCount")


def _canton_links(data: dict | None) -> list[dict]:
    """seoInformation.linkSections "Wähle einen Kanton:" -> [{label, slug, token}] (excl.
    'Ganze Schweiz', which is the all-CH total, not a facet)."""
    if not data:
        return []
    for sec in (data.get("seoInformation") or {}).get("linkSections") or []:
        if "anton" in (sec.get("title") or ""):   # "Kanton" / "Wähle einen Kanton"
            out = []
            for li in sec.get("links") or []:
                slug, tok = li.get("slug"), li.get("searchToken")
                if slug and tok and slug != AUTOS_SLUG:
                    out.append({"label": li.get("label"), "slug": slug, "token": tok})
            return out
    return []


def _search_url(slug: str, token: str, page: int = 1) -> str:
    return f"{BASE}/de/q/{slug}/{token}?page={page}"


async def _fetch_search(sess, slug: str, token: str, page: int = 1) -> dict | None:
    """Fetch one Autos search page and return its SearchListingsByConstraints data, or None
    if the response is not a cars-scoped search (redirect / category drop / parse miss)."""
    r = await _get(sess, _search_url(slug, token, page))
    if r.status_code != 200:
        return None
    data = _search_data(_next_data(r.text))
    return data if _is_cars(data) else None


# --------------------------------------------------------------------------- count_verify
async def count_verify(sess) -> tuple[int | None, int | None, list[dict]]:
    """way1 = all-CH Autos totalCount; way2 = sum of per-canton totalCount. Also returns the
    live canton partition (so --full reuses it without a second home fetch)."""
    base = await _fetch_search(sess, AUTOS_SLUG, AUTOS_TOKEN)
    if base is None:
        return None, None, []
    declared = _total_count(base)
    cantons = _canton_links(base)
    facet_sum = 0
    got = 0
    for c in cantons:
        data = await _fetch_search(sess, c["slug"], c["token"])
        tc = _total_count(data)
        if tc is not None:
            facet_sum += tc
            got += 1
        await asyncio.sleep(SLEEP)
    way2 = facet_sum if got == len(cantons) and cantons else None
    return declared, way2, cantons


# --------------------------------------------------------------------------- enumeration
async def _walk_search(sess, slug: str, token: str, *, want: int | None,
                       seen: set[str], sink: list[dict]) -> None:
    """Page a single (canton) Autos search 1..PAGE_CAP, collecting cars-scoped edges until the
    window caps (307 -> non-cars data -> None) or a page yields no new ids or `want` is hit."""
    for pg in range(1, PAGE_CAP + 1):
        data = await _fetch_search(sess, slug, token, pg)
        if data is None:           # category dropped / redirect / window cap -> stop this facet
            break
        edges = parse_edges(data)
        if not edges:
            break
        before = len(seen)
        for it in edges:
            if it["url"] not in seen:
                seen.add(it["url"])
                sink.append(it)
        await asyncio.sleep(SLEEP)
        if len(seen) == before:    # no new ids -> end of this facet's window
            break
        if want and len(sink) >= want:
            break


async def harvest_sample(sess, want: int) -> list[dict]:
    """Unfiltered all-CH walk to reach `want` (the first pages never cap)."""
    seen: set[str] = set()
    sink: list[dict] = []
    await _walk_search(sess, AUTOS_SLUG, AUTOS_TOKEN, want=want, seen=seen, sink=sink)
    return sink[:want]


async def harvest_full(sess, cantons: list[dict], max_pages: int) -> list[dict]:
    """Exhaustive per-canton sweep. Each canton is walked to its window cap; the global dedup
    set unions overlapping listings. (Cantons larger than the ~4.5K window are still capped —
    a brand/price sub-facet pass is the next refinement, declared in count_coverage.)"""
    seen: set[str] = set()
    sink: list[dict] = []
    t0 = time.monotonic()
    walked = 0
    for i, c in enumerate(cantons, 1):
        if not await host_budget.wait_until_healthy(max_s=120):
            print(f"  host pressure at canton {i}/{len(cantons)}; stopping", flush=True)
            break
        await _walk_search(sess, c["slug"], c["token"], want=None, seen=seen, sink=sink)
        walked += 1
        print(f"  [{i}/{len(cantons)}] {c['label']:<24} cum={len(sink)} "
              f"({int(time.monotonic()-t0)}s)", flush=True)
        if max_pages and walked >= max_pages:
            print(f"  bounded stop after {walked} cantons", flush=True)
            break
    return sink


# --------------------------------------------------------------------------- run
async def run(sample: int, conc: int, count_only: bool, full: bool,
              max_pages: int, skip_count: bool) -> None:
    async with AsyncSession(impersonate="chrome136") as sess:
        if not await host_budget.wait_until_healthy(max_s=60):
            print("HOST under pressure; aborting")
            return
        print(f"TUTTI seal | count_only={count_only} sample={sample} full={full} "
              f"RAM={host_budget.available_mb()}MB", flush=True)

        declared = way2 = None
        cantons: list[dict] = []
        if not skip_count or full:
            declared, way2, cantons = await count_verify(sess)
            print(f"  count_verify: declared(all-CH cars)={declared}  "
                  f"canton-facet-sum={way2}  cantons={len(cantons)}", flush=True)
            if declared is None:
                print("  could not resolve cars-scoped Autos search (scope guard tripped); abort")
                return
        if count_only:
            if declared and way2:
                diff = abs(declared - way2) / max(declared, 1) * 100
                print(f"\nDECLARED={declared}  CANTON-FACET-SUM={way2}  "
                      f"agreement={100 - diff:.2f}%")
            else:
                print(f"\nDECLARED={declared}  CANTON-FACET-SUM={way2}")
            return

        t0 = time.monotonic()
        if full:
            if not cantons:
                print("  no canton partition; abort full"); return
            listings = await harvest_full(sess, cantons, max_pages)
            complete = not max_pages
        else:
            listings = await harvest_sample(sess, sample)
            complete = False
        rich = [li for li in listings if li.get("price") or li.get("year")]
        print(f"  harvested {len(listings)} ({len(rich)} with price/year) in "
              f"{int(time.monotonic()-t0)}s", flush=True)

        pool = await asyncpg.create_pool(DSN, min_size=2, max_size=conc + 3)
        rdb = aioredis.from_url(REDIS)
        try:
            res = await ps.cage_platform(pool, rdb, DOMAIN, COUNTRY, listings,
                                         config_ref=CONFIG_REF, complete=complete)
            api = await ps.verify_api(pool, res["ent"])
            trap = ("edge.formattedPrice = CASH (CHF int, Swiss '''' thousands sep); "
                    "detail numericPrice == it, no lease/monthly field on a car listing")
            ps.print_verdict("tutti.ch Autos", declared=declared,
                             way2_label="canton-facet-sum", way2=way2,
                             served=res["served"], api=api, price_trap=trap)
            print(f"  cage: new={res['new']} served={res['served']} gone={res['gone']} "
                  f"(reconcile={'ON' if complete else 'OFF (sample/bounded)'})", flush=True)
        finally:
            await rdb.aclose()
            await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=60)
    ap.add_argument("--conc", type=int, default=1)
    ap.add_argument("--count-only", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--max-pages", type=int, default=0)
    ap.add_argument("--skip-count", action="store_true")
    a = ap.parse_args()
    asyncio.run(run(a.sample, a.conc, a.count_only, a.full, a.max_pages, a.skip_count))
