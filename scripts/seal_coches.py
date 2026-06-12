"""Seal coches.net ES used cars — CloudFront + Lambda@Edge custom (RATE-BANS the IP).

coches.net/segunda-mano/ is a custom React SSR (NO __NEXT_DATA__) that inlines the search state
as ``window.__INITIAL_PROPS__ = JSON.parse("...")``. [VERIFIED 2026-06-12 on cold hits, before the
ban]:
  - ``initialResults.totalResults`` = ~249.4k, ``totalPages`` ~8313, ``items[30]`` per page,
  - each item: ``url`` (relative semantic deep link), ``price`` (CASH int e.g. 53900 — NOT the
    financing; ``isFinanced`` is a separate bool; the detail page labels it "Precio al contado"),
    ``makeId``/``modelId`` (numeric), ``imgUrl``,
  - ``initialResults.aggregations[*].items[*].totalResults`` = facet partition (count way2).

LIVE-BLOCK [VERIFIED]: Lambda@Edge IP-BANS after a short burst (~6 reqs) and holds the ban for
50+ min (every request then returns an ~8.7 KB "Ups!" page, HTTP 200, no __INITIAL_PROPS__). So:
  - pace VERY conservatively (>= 5 s) and minimise requests (every field is in each page's props),
  - the live E2E in THIS session is blocked by the persistent ban — run from a fresh/rotated ES IP.

[ASSUMED — could not confirm live before the ban, flagged]: the pagination param is ``?pg=N``
(the make-filter ``/segunda-mano/<make>/`` returned 200). Confirm both on the first clean-IP run.
price trap is VERIFIED (item.price = cash); count way1/way2 logic is VERIFIED against the props.

    py -m scripts.seal_coches --sample 60        # E2E (needs a non-banned ES IP)
    py -m scripts.seal_coches --count-only        # 2-way count (1 request)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time

import asyncpg
import redis.asyncio as aioredis
from curl_cffi.requests import AsyncSession

from scrapers.common import host_budget
from scripts import platform_seal as ps

DSN = "postgresql://cardex:cardex_dev_only@localhost:5432/cardex"
REDIS = "redis://localhost:6379"
DOMAIN = "coches.net"
BASE = "https://www.coches.net"
SEARCH = "https://www.coches.net/segunda-mano/"
CONFIG_REF = "configs/platforms/coches.json"
SLEEP = 5.0            # Lambda@Edge IP-bans on bursts — pace hard
YEAR_IN_SLUG = re.compile(r"-(19\d\d|20\d\d)-[a-z]+-\d{6,}")   # "...-2007-en-madrid-57135482-..."


def extract_props(html: str) -> dict:
    """window.__INITIAL_PROPS__ = JSON.parse("<escaped json>") -> dict. {} when blocked/absent."""
    i = (html or "").find("__INITIAL_PROPS__")
    if i < 0:
        return {}
    p = html.find('JSON.parse("', i)
    if p < 0:
        return {}
    start = p + len("JSON.parse(")
    j = start + 1
    while j < len(html):
        if html[j] == "\\":
            j += 2
            continue
        if html[j] == '"':
            break
        j += 1
    try:
        return json.loads(json.loads(html[start:j + 1]))
    except (ValueError, TypeError):
        return {}


def _title_from_url(url: str) -> str | None:
    seg = url.strip("/").split("/")[-1]
    seg = re.split(r"-\d{4}-[a-z]+-\d{6,}", seg)[0]        # drop -YYYY-city-id tail
    seg = re.sub(r"-\d{6,}.*$", "", seg)
    return seg.replace("-", " ").strip().title() or None if seg else None


def parse_items(props: dict) -> list[dict]:
    ir = (props.get("initialResults") or {})
    out = []
    for it in ir.get("items") or []:
        if not isinstance(it, dict):
            continue
        url = it.get("url") or ""
        if url.startswith("/"):
            url = BASE + url
        if not url:
            continue
        ym = YEAR_IN_SLUG.search(it.get("url") or "")
        price = it.get("price")
        out.append({
            "url": url,
            "title": _title_from_url(it.get("url") or ""),
            "price": int(price) if isinstance(price, (int, float)) and price else None,
            "year": int(ym.group(1)) if ym else None,
            "km": None,   # [ASSUMED] item km field unconfirmed (ban); detail page has it
        })
    return out


def _agg_sum(props: dict) -> int | None:
    """Largest aggregation partition's totalResults sum (the make/value facet)."""
    aggs = (props.get("initialResults") or {}).get("aggregations") or []
    best = None
    for a in aggs:
        items = a.get("items") if isinstance(a, dict) else None
        if not items:
            continue
        s = sum(int(i.get("totalResults") or 0) for i in items if isinstance(i, dict))
        if best is None or s > best:
            best = s
    return best


async def _get(sess, url):
    return await sess.get(url, timeout=30, allow_redirects=True)


async def harvest_sample(sess, want: int) -> tuple[list[dict], str]:
    listings, seen = [], set()
    page = 1
    status = "OK"
    while len(listings) < want and page <= 100:
        r = await _get(sess, f"{SEARCH}?pg={page}")          # [ASSUMED] ?pg=N
        props = extract_props(r.text or "")
        rows = parse_items(props)
        if not props or not rows:
            status = f"BLOCKED/empty@pg{page} (status={r.status_code} len={len(r.text or '')})"
            print(f"  {status}", flush=True)
            break
        for c in rows:
            if c["url"] not in seen:
                seen.add(c["url"])
                listings.append(c)
        print(f"  pg {page}: +{len(rows)} (total {len(listings)})", flush=True)
        page += 1
        await asyncio.sleep(SLEEP)
    return listings[:want], status


async def run(sample: int, count_only: bool, full: bool) -> None:
    async with AsyncSession(impersonate="chrome136") as sess:
        if not await host_budget.wait_until_healthy(max_s=60):
            print("HOST under pressure; aborting"); return
        print(f"COCHES seal | sample={sample} RAM={host_budget.available_mb()}MB", flush=True)

        props = extract_props((await _get(sess, SEARCH)).text or "")
        if not props:
            print("  BLOCKED: no __INITIAL_PROPS__ (Lambda@Edge IP-ban). Run from a fresh ES IP.")
            return
        declared = (props.get("initialResults") or {}).get("totalResults")
        way2 = _agg_sum(props)
        print(f"  declared totalResults={declared}  aggregation-partition-sum={way2}", flush=True)
        if count_only:
            print(f"\nTOTAL={declared}  AGGREGATION-SUM={way2}")
            return
        await asyncio.sleep(SLEEP)

        t0 = time.monotonic()
        listings, status = await harvest_sample(sess, sample)
        rich = [li for li in listings if li.get("price") or li.get("year")]
        print(f"  harvested {len(listings)} ({len(rich)} with price/year) | {status} "
              f"in {int(time.monotonic()-t0)}s", flush=True)
        if not listings:
            return

        pool = await asyncpg.create_pool(DSN, min_size=2, max_size=5)
        rdb = aioredis.from_url(REDIS)
        try:
            res = await ps.cage_platform(pool, rdb, DOMAIN, "ES", listings,
                                         config_ref=CONFIG_REF, complete=full)
            api = await ps.verify_api(pool, res["ent"])
            trap = "item.price = CASH int ('Precio al contado'); isFinanced/financing separate"
            ps.print_verdict("coches.net", declared=declared,
                             way2_label="aggregation-partition-sum", way2=way2,
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
    a = ap.parse_args()
    asyncio.run(run(a.sample, a.count_only, a.full))
