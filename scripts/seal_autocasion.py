"""Seal Autocasion (autocasion.com) ES used inventory — PROXY-FREE past Cloudflare (Chrome TLS).

autocasion.com is SSR HTML behind Cloudflare in **pass-through** mode: a curl_cffi Chrome136
session gets HTTP 200 + real HTML with NO JS challenge (no ``__cf_chl`` / "Just a moment"
interstitial — verified 2026-06-12, ``cf-ray`` present, ~1.1 MB body). Tier T1, defense=CF.

Unlike the card-inline platforms (ParuVendu / Kleinanzeigen), the autocasion SRP **cards carry
NO price/year/km** — only the image + the detail anchor. So this connector PER-DETAIL fetches a
bounded sample (the dealer-harvester pattern) and reads the rich fields from the detail page:

  - SRP card anchor (the listing id):
    ``/coches-segunda-mano/<brand>-<model>-ocasion/<slug>-ref<DIGITS>`` (``ref<DIGITS>`` = canonical id).
  - detail ld+json is ``@type=Product`` (NOT Car/Vehicle), with a well-formed
    ``offers{@type:Offer, price, priceCurrency:EUR}`` — that ``offers.price`` is the CASH sale price
    (spot-checked == GTM dataLayer ``price`` == the share-text "en NNN €" == meta description). The
    page also hosts a financing simulator but it exposes NO competing structured /mes amount, so the
    cash price never leaks the monthly trap. ``year`` + ``km`` come from ``pipeline.parse.parse_listing``
    (JSON-LD-first heuristics — the Product ld+json omits them, the DOM carries them).

count_verify (>=2 ways): the global ``/coches-ocasion`` counter vs the SUM of the six GLOBAL fuel
facets ``/coches-segunda-mano/<fuel>`` (``diesel, gasolina, electrico, hibrido, hibrido-enchufable,
gas`` — mutually exclusive + exhaustive: 121,206 vs 121,353 = 99.88%, [VERIFIED] 2026-06-12). The
per-province counters are NOT a clean way — overlapping search radius overshoots the national total.

Result-window cap = page 400 (~9.6k ads/segment); page 401+ silently degrades to a 6-card sticky
carousel. The global SRP therefore only reaches ~9.6k of ~121k, so ``--full`` partitions by
province x fuel (the live-verified SSR facet grid). NOTE: the largest cells (madrid/gasolina ~25k,
madrid/diesel ~17k) still exceed the 9.6k window — a complete national sweep needs a finer 3rd
dimension (the sitemap brand-model categories, ``coches-segunda-mano.xml``, ~30k fine-grained locs).
``--sample`` (the E2E proof) and ``--count-only`` (the 2-way gate) do not hit the cap.

    py -m scripts.seal_autocasion --sample 60 [--conc 4]   # E2E proof (INSERT-only, no GONE)
    py -m scripts.seal_autocasion --count-only             # 2-way count verify only
    py -m scripts.seal_autocasion --full [--conc 4]        # province x fuel sweep (reconciles)
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
from scrapers.pipeline.parse import parse_listing
from scripts import platform_seal as ps

DSN = "postgresql://cardex:cardex_dev_only@localhost:5432/cardex"
REDIS = "redis://localhost:6379"
DOMAIN = "autocasion.com"
BASE = "https://www.autocasion.com"
GLOBAL_SRP = BASE + "/coches-ocasion"
CONFIG_REF = "configs/platforms/autocasion.json"
SLEEP = 1.2                     # jitter floor per CARDEX rate doctrine
PAGE_CAP = 400                  # result-window cap; page 401+ = sticky carousel (no new ads)

# canonical detail anchor: two path segments + `-ref<DIGITS>` (vs the single-segment category).
DET = re.compile(r"/coches-segunda-mano/[a-z0-9-]+/[a-z0-9-]+-ref\d+")
LDJSON = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
# SAFE counter: a 1-3 digit head + grouped thousands (no unbounded \s class — avoids catastrophic
# backtracking on the ~1.1 MB SRP), validated near the ES result nouns.
CNT = re.compile(r"(\d{1,3}(?:[.\s]\d{3})+)\s*(?:coches|veh[ií]culos|anuncios|resultados)", re.I)

# The six SSR fuel facets — mutually exclusive + exhaustive (sum == global within jitter). Used both
# as the count_verify way-2 (global scope) and, crossed with province, as the --full partition grid.
FUELS = ["diesel", "gasolina", "electrico", "hibrido", "hibrido-enchufable", "gas"]


def _counter(html: str) -> int | None:
    vals = [int(re.sub(r"\D", "", m.group(1))) for m in CNT.finditer(html or "")]
    vals = [v for v in vals if v > 500]
    return max(vals) if vals else None


def _digits(v) -> int | None:
    if v in (None, ""):
        return None
    n = int(re.sub(r"\D", "", str(v)) or 0)
    return n or None


def parse_detail(html: str, url: str) -> dict:
    """autocasion detail page -> cage-shape dict {url,title,price,year,km}.

    price/currency come from the ``@type=Product`` ld+json ``offers`` (CASH, EUR); title prefers the
    ld+json ``name``; year + km come from ``parse_listing`` heuristics (the Product ld+json omits
    them). Missing fields stay None — a partial card is still a valid pointer."""
    rec = parse_listing(html or "")            # make / model / year / mileage (heuristic, JSON-LD-first)
    price = ccy = name = None
    for raw in LDJSON.findall(html or ""):
        try:
            d = json.loads(raw)
        except (ValueError, TypeError):
            continue
        for top in (d if isinstance(d, list) else [d]):
            if not isinstance(top, dict):
                continue
            for node in top.get("@graph", [top]):
                if not isinstance(node, dict) or node.get("@type") not in ("Product", "Car", "Vehicle"):
                    continue
                off = node.get("offers") or {}
                if isinstance(off, list):
                    off = off[0] if off else {}
                if isinstance(off, dict) and off.get("price") is not None:
                    price, ccy, name = off.get("price"), off.get("priceCurrency"), node.get("name")
    title = name or (f"{rec.get('make') or ''} {rec.get('model') or ''}".strip() or None)
    yr = rec.get("year")
    return {
        "url": url,
        "title": title,
        "price": _digits(price),
        "year": int(str(yr)[:4]) if yr and str(yr)[:4].isdigit() else None,
        "km": _digits(rec.get("mileage")),
        "currency": ccy,                       # EUR; cage derives currency from country, this is a cross-check
    }


async def _get(sess, url):
    return await sess.get(url, timeout=40, allow_redirects=True)


def _srp_url(seg: str, page: int) -> str:
    """seg='' -> global SRP; seg='madrid/diesel' -> province/fuel cell. page 1 is the bare URL."""
    base = GLOBAL_SRP if not seg else f"{BASE}/coches-segunda-mano/{seg}"
    return base if page <= 1 else f"{base}?page={page}"


async def _collect_anchors(sess, seg: str, *, max_pages: int) -> list[str]:
    """Walk SRP pages of one segment, returning canonical detail URLs (deduped, order-stable).

    Stops on the result-window cap: a page that yields no NEW anchors (the sticky carousel) or a
    short page ends the segment. Never exceeds PAGE_CAP."""
    seen, ordered = set(), []
    for pg in range(1, min(max_pages, PAGE_CAP) + 1):
        r = await _get(sess, _srp_url(seg, pg))
        if r.status_code != 200:
            break
        page_anchors = [BASE + a for a in dict.fromkeys(DET.findall(r.text or ""))]
        fresh = [a for a in page_anchors if a not in seen]
        if not fresh:                          # carousel / exhausted -> stop this segment
            break
        for a in fresh:
            seen.add(a)
            ordered.append(a)
        await asyncio.sleep(SLEEP)
        if len(page_anchors) < 10:             # short page -> last page of the segment
            break
    return ordered


async def _enrich(sess, pool, urls: list[str], conc: int) -> list[dict]:
    """Per-detail fetch + parse, host-budget-gated, bounded concurrency. One bad page is skipped."""
    out: list[dict] = []
    sem = asyncio.Semaphore(max(1, host_budget.effective_conc(conc)))

    async def one(u: str) -> None:
        async with sem:
            async with host_budget.slot(pool, "net"):
                try:
                    r = await _get(sess, u)
                    if r.status_code == 200 and r.text:
                        out.append(parse_detail(r.text, u))
                except Exception:              # noqa: BLE001 — never let one page abort the run
                    pass
                await asyncio.sleep(SLEEP / max(1, conc))

    await asyncio.gather(*(one(u) for u in urls))
    return out


async def count_verify(sess) -> tuple[int | None, int | None]:
    """way-1 = global /coches-ocasion counter; way-2 = sum of the six GLOBAL fuel facets."""
    declared = _counter((await _get(sess, GLOBAL_SRP)).text or "")
    await asyncio.sleep(SLEEP)
    total, parts = 0, []
    for f in FUELS:
        c = _counter((await _get(sess, f"{BASE}/coches-segunda-mano/{f}")).text or "")
        if c:
            total += c
            parts.append(f"{f}:{c}")
        await asyncio.sleep(SLEEP)
    print(f"  fuel-facet-sum: {' '.join(parts)} -> {total}")
    return declared, (total or None)


async def harvest_sample(sess, pool, want: int, conc: int) -> list[dict]:
    """Bounded E2E sample off the global SRP: collect anchors, per-detail enrich to `want` rich rows."""
    pages = (want // 20) + 4
    anchors = await _collect_anchors(sess, "", max_pages=pages)
    listings = await _enrich(sess, pool, anchors[: want + 20], conc)
    return listings[:want]


async def harvest_full(sess, pool, conc: int) -> list[dict]:
    """Exhaustive province x fuel sweep. Cross-cell dedup is the canonical-URL set. NOTE: the biggest
    cells exceed the 9.6k window (documented in the module docstring); this grid is the live-verified
    facet partition, not a guaranteed-complete enumeration of the heaviest provinces."""
    provinces = await _provinces(sess)
    seen: set[str] = set()
    listings: list[dict] = []
    for prov in provinces:
        for fuel in FUELS:
            anchors = await _collect_anchors(sess, f"{prov}/{fuel}", max_pages=PAGE_CAP)
            fresh = [a for a in anchors if a not in seen]
            seen.update(fresh)
            if fresh:
                listings += await _enrich(sess, pool, fresh, conc)
            print(f"    cell {prov}/{fuel}: anchors={len(anchors)} new={len(fresh)} "
                  f"total={len(listings)} RAM={host_budget.available_mb()}MB", flush=True)
            if not await host_budget.wait_until_healthy(max_s=120):
                print("    HOST pressure persists; stopping sweep early"); return listings
    return listings


async def _provinces(sess) -> list[str]:
    """Province slugs from the SSR sitemap leaf (single-segment ``/coches-segunda-mano/<prov>`` locs).
    Falls back to the verified Madrid-first short list if the sitemap is unreachable."""
    fallback = ["madrid", "barcelona", "valencia", "sevilla", "malaga", "alicante"]
    try:
        r = await _get(sess, BASE + "/uploads/sitemap-ng/coches-segunda-mano/coches-segunda-mano.xml")
        locs = re.findall(r"/coches-segunda-mano/([a-z-]+)</loc>", r.text or "")
        provs = sorted({s for s in locs if "-ocasion" not in s and s not in FUELS})
        return provs or fallback
    except Exception:  # noqa: BLE001
        return fallback


async def run(sample: int, conc: int, count_only: bool, full: bool, skip_count: bool) -> None:
    async with AsyncSession(impersonate="chrome136") as sess:   # SESSION-level TLS, never per-request
        if not await host_budget.wait_until_healthy(max_s=60):
            print("HOST under pressure; aborting"); return
        print(f"AUTOCASION seal | sample={sample} conc={conc} full={full} "
              f"RAM={host_budget.available_mb()}MB", flush=True)

        declared = way2 = None
        if not skip_count:
            declared, way2 = await count_verify(sess)
        if count_only:
            print(f"\nGLOBAL-COUNTER={declared}  FUEL-FACET-SUM={way2}")
            return

        pool = await asyncpg.create_pool(DSN, min_size=2, max_size=conc + 5)
        rdb = aioredis.from_url(REDIS)
        try:
            t0 = time.monotonic()
            listings = (await harvest_full(sess, pool, conc) if full
                        else await harvest_sample(sess, pool, sample, conc))
            rich = [li for li in listings if li.get("price") or li.get("year")]
            print(f"  harvested {len(listings)} detail rows ({len(rich)} with price/year) in "
                  f"{int(time.monotonic()-t0)}s", flush=True)

            res = await ps.cage_platform(pool, rdb, DOMAIN, "ES", listings,
                                         config_ref=CONFIG_REF, complete=full)
            api = await ps.verify_api(pool, res["ent"])
            trap = ("detail ld+json @type=Product offers.price = CASH EUR "
                    "(== GTM price == share-text == meta-desc; financing widget exposes no /mes amount)")
            ps.print_verdict("Autocasion autocasion.com", declared=declared,
                             way2_label="fuel-facet-sum", way2=way2,
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
