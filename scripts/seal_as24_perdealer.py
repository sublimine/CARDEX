"""Seal AutoScout24 via PER-DEALER ENUMERATION — the COMPLETE, drift-free AS24 harvest.

WHY this beats market faceting. AS24's market search caps at ~4000 results/query, so the
faceting connector (``scrapers/common/autoscout24.py``) must split year×price×fuel and STILL
plateaus near ~65 % with page-drift (the relevance pager re-orders, leaking listings between
pages). But AS24 also exposes a DEALER directory, and every dealer's own stock is FAR under
the 4000 cap (verified: a 603-car dealer is the large end). Enumerating per dealer therefore
gives COMPLETE coverage, ZERO market-facet drift, and country→dealer attribution for free.

Two VERIFIED surfaces (curl_cffi chrome136, proxy-free, 2026-06-12):

  1. CENSUS — the dealer directory API (identity + count):
       GET /dealer-search/api?country=<CC>&pageIndex=<N>&size<=100&sortBy=best
       -> {results:[{customerId, companyName, slug, address, ...}], totalDealers, numberOfPages}
       DE totalDealers ≈ 19.8k. ``customerId`` is the stable dealer id; ``slug`` keys the profile.

  2. STOCK — the dealer PROFILE page SSR (the per-dealer inventory, rich):
       GET /haendler/<slug>?page=<N>   (__NEXT_DATA__.props.pageProps)
         numberOfResults                 = the dealer's EXACT stock count (<< 4000 cap)
         listings[].url                  = /angebote/<slug>-<uuid>   (absolute deep link)
         listings[].prices.public.priceRaw         = CASH price (int EUR) — NOT the /mois rate
         listings[].vehicle.make/.model
         listings[].vehicle.mileageInKm.raw        = km
         listings[].vehicle.firstRegistrationDate.raw "YYYY-MM-DD" -> year

Each dealer becomes a ``kind='dealer'`` source_entity keyed by a SYNTHETIC stable domain
``as24-dealer-<customerId>.autoscout24.de`` (the API exposes no own website here; identity
resolution to the dealer's real site is a separate, lossy downstream step this method does
NOT depend on). Caging routes through the SAME ``cage_inventory`` seam every connector uses, so
each dealer shows up LIVE in ``/v1/entities/{ulid}/inventory`` and reconciles per-dealer
(the delta is naturally per-dealer — a dealer's GONE cars are exactly its sold stock).

Anti-bot reality: AS24 throttles repeated /haendler hits from a warm datacenter IP (200 +
softblock HTML with no __NEXT_DATA__). Mitigated structurally: session-level impersonate
(JA3-coherent), jittered pacing, retry-on-softblock, and the host_budget NET lane. The pager
tops out ~31 pages (~620 slots): dealers under ~500 stock reach 100 %; the largest lose the
relevance-pager residual (~85 % on a 603-car dealer), reported honestly per dealer.

    py -m scripts.seal_as24_perdealer --count-only [--country DE] [--census-cap N]
        dealer census + per-dealer stock-sum (samples stock to estimate the country total
        vs the ~831k market figure) — the coverage-potential math, no caging.
    py -m scripts.seal_as24_perdealer --sample 5 [--country DE]
        E2E proof: enumerate N real dealers, cage INSERT-only (a partial run never GONE-marks),
        verify each via the per-entity API. Prints each dealer's entity key for the verifier.
    py -m scripts.seal_as24_perdealer --full [--country DE] [--max-dealers N]
        every dealer in the country: enumerate full stock -> cage + reconcile (per-dealer).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys

# curl_cffi has no subprocess, so the Selector loop is fine on Windows (and asyncpg prefers it).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

import asyncpg
import redis.asyncio as aioredis
from curl_cffi.requests import AsyncSession

from scrapers.common import host_budget
from scrapers.common.indexer import _hash_urls
from scrapers.dealer_scraping.inventory_harvester import _entity_ulid, cage_inventory

DSN = "postgresql://cardex:cardex_dev_only@localhost:5432/cardex"
REDIS = "redis://localhost:6379"

# Country -> AS24 host + profile path segment. The census API's ``country`` param is
# authoritative (resolves the BE=DE-mirror problem). CH is a separate platform (excluded,
# like as24_dealers). Profile segment differs per locale (verified in as24_nextjs).
_COUNTRY = {
    "DE": {"host": "www.autoscout24.de", "haendler": "haendler"},
    "FR": {"host": "www.autoscout24.fr", "haendler": "garages"},
    "ES": {"host": "www.autoscout24.es", "haendler": "profesionales"},
    "NL": {"host": "www.autoscout24.nl", "haendler": "autobedrijven"},
    "BE": {"host": "www.autoscout24.be", "haendler": "nl/verkopers"},
}

CENSUS_SIZE = 100          # dealer-search API hard cap (size>=250 -> HTTP 400)
PAGE_SIZE = 20             # listings per profile page
PAGER_CAP = 34             # profile relevance-pager tops out ~31 pages; small headroom
PER_DEALER_HARD = 4000     # AS24 search ceiling — a dealer over this would need in-dealer faceting
CENSUS_SLEEP = 0.3         # between census API pages (light JSON)
PAGE_SLEEP = 1.2           # base between profile pages; +jitter (warm-IP polite, <=0.7 req/s)
PAGE_JITTER = 0.6
RETRIES = 4                # softblock/partial retries per profile page

_NEXT = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
# CF/AS24 warm-IP softblock tells (mirrors scrapers/common/autoscout24.py markers).
_SOFTBLOCK = ("just a moment", "enable javascript and cookies", "cf-browser-verification",
              "checking your browser", "__cf_chl_", "attention required")


# --------------------------------------------------------------------------- parsing
def _digits(v) -> int | None:
    if v is None:
        return None
    m = re.search(r"\d[\d.\s']*", str(v))
    if not m:
        return None
    try:
        return int(re.sub(r"[.\s']", "", m.group(0)))
    except ValueError:
        return None


def _price(v) -> int | None:
    n = _digits(v)
    return n if n is not None and 100 <= n <= 5_000_000 else None


def _year(v) -> int | None:
    # firstRegistrationDate.raw is "YYYY-MM-DD"; year is the leading 4 digits.
    s = str(v or "")
    if len(s) >= 4 and s[:4].isdigit():
        y = int(s[:4])
        return y if 1950 <= y <= 2027 else None
    return None


def _km(v) -> int | None:
    n = _digits(v)
    return n if n is not None and 0 <= n <= 2_000_000 else None


def parse_listing(li: dict, host: str) -> dict | None:
    """One profile ``listings[]`` entry -> cage shape {url,title,price,year,km}. Pure.

    ``prices.public.priceRaw`` is the CASH price (gross); ``monthlyRateGross`` is a SEPARATE
    financing node, never read here -> price-trap-safe by construction.
    """
    path = li.get("url")
    if not path or not isinstance(path, str):
        return None
    url = path if path.startswith("http") else f"https://{host}{path}"
    veh = li.get("vehicle") or {}
    prices = (li.get("prices") or {}).get("public") or (li.get("prices") or {}).get("dealer") or {}
    make = (veh.get("make") or "").strip()
    model = (veh.get("model") or "").strip()
    title = (f"{make} {model}").strip() or None
    fr = veh.get("firstRegistrationDate") or {}
    mileage = veh.get("mileageInKm") or {}
    return {
        "url": url,
        "title": title,
        "price": _price(prices.get("priceRaw")),
        "year": _year(fr.get("raw")),
        "km": _km(mileage.get("raw")),
    }


def _pageprops(html: str) -> dict | None:
    """Extract __NEXT_DATA__.props.pageProps; None if absent (softblock/partial page)."""
    m = _NEXT.search(html or "")
    if not m:
        return None
    try:
        nd = json.loads(m.group(1))
    except (ValueError, TypeError):
        return None
    return nd.get("props", {}).get("pageProps")


# --------------------------------------------------------------------------- fetch
async def census_page(sess: AsyncSession, country: str, page_index: int,
                      size: int = CENSUS_SIZE) -> tuple[list[dict], int]:
    """One dealer-search API page -> (results, totalDealers)."""
    host = _COUNTRY[country]["host"]
    r = await sess.get(f"https://{host}/dealer-search/api",
                       params={"country": country, "pageIndex": page_index, "size": size, "sortBy": "best"},
                       timeout=30)
    if r.status_code != 200:
        return [], 0
    d = r.json()
    if not isinstance(d, dict):
        return [], 0
    res = d.get("results") or []
    total = d.get("totalDealers")
    return (res if isinstance(res, list) else []), (int(total) if isinstance(total, (int, float)) else 0)


async def iter_census(sess: AsyncSession, country: str, *, cap: int = 0):
    """Yield dealer records {customerId, slug, companyName, ...} draining all census pages.
    Robust to totalDealers drift — stops on an empty/short page, never trusts the count."""
    emitted = 0
    for page_index in range(1, 100_000):
        results, _ = await census_page(sess, country, page_index)
        if not results:
            return
        for rec in results:
            if rec.get("customerId") is None or not rec.get("slug"):
                continue
            yield rec
            emitted += 1
            if cap and emitted >= cap:
                return
        if len(results) < CENSUS_SIZE:
            return
        await asyncio.sleep(CENSUS_SLEEP)


async def fetch_profile_page(sess: AsyncSession, country: str, slug: str,
                             page: int) -> dict | None:
    """Fetch one /haendler/<slug>?page=N, retrying through warm-IP softblocks/partials.
    Returns pageProps (with .listings) or None when every retry came back blocked."""
    host = _COUNTRY[country]["host"]
    seg = _COUNTRY[country]["haendler"]
    url = f"https://{host}/{seg}/{slug}"
    for attempt in range(1, RETRIES + 1):
        try:
            r = await sess.get(url, params={"page": page}, timeout=30)
            lo = r.text.lower()
            if r.status_code == 200 and not any(s in lo for s in _SOFTBLOCK):
                pp = _pageprops(r.text)
                if pp is not None and pp.get("listings") is not None:
                    return pp
        except Exception:  # noqa: BLE001 — transport hiccup folds into the retry/backoff
            pass
        await asyncio.sleep(2.0 * attempt + random.uniform(0, 1.0))  # backoff on block/partial
    return None


async def dealer_stock(sess: AsyncSession, country: str, slug: str, *,
                       want: int | None = None, max_pages: int = PAGER_CAP) -> tuple[list[dict], int | None]:
    """Walk a dealer's profile pages 1..cap -> (cage-shape listings deduped by url, numberOfResults).

    ``want`` stops early (sample mode). ``numberOfResults`` is the dealer's declared stock; we
    return whatever the pager actually yields (the pager-cap residual is reported by the caller).
    """
    host = _COUNTRY[country]["host"]
    by_url: dict[str, dict] = {}
    declared: int | None = None
    for page in range(1, max_pages + 1):
        pp = await fetch_profile_page(sess, country, slug, page)
        if pp is None:
            break  # blocked through all retries — stop this dealer, keep what we have
        if declared is None:
            declared = pp.get("numberOfResults")
        rows = pp.get("listings") or []
        if not rows:
            break
        for li in rows:
            cg = parse_listing(li, host)
            if cg:
                by_url.setdefault(cg["url"], cg)
        if len(rows) < PAGE_SIZE:
            break  # short page = last page (dealer fully enumerated, no cap residual)
        if want and len(by_url) >= want:
            break
        await asyncio.sleep(PAGE_SLEEP + random.uniform(0, PAGE_JITTER))
    return list(by_url.values()), declared


# --------------------------------------------------------------------------- caging
def dealer_domain(customer_id) -> str:
    """Synthetic stable per-dealer entity key. The census API exposes no own website here;
    this keys the source_entity so entity_ulid is canonical and country→dealer is attributed."""
    return f"as24-dealer-{customer_id}.autoscout24.de"


async def cage_dealer(pool, rdb, customer_id, country: str, listings: list[dict], *,
                      complete: bool) -> dict:
    """Cage one dealer's stock under a ``kind='dealer'`` entity; reconcile iff ``complete``.

    Mirrors platform_seal.cage_platform but with kind='dealer'/tier='T1' (AS24's own clean
    surface, no deep defense). complete=False (the --sample path) is INSERT-only: a partial
    set must NEVER GONE-mark a dealer's cars it simply did not reach.
    """
    domain = dealer_domain(customer_id)
    cc = (country or "")[:2]
    config_ref = f"as24:dealer:{customer_id}"
    caged = await cage_inventory(pool, rdb, domain, cc, listings,
                                 config_ref=config_ref, kind="dealer", tier="T1")
    ent = _entity_ulid(domain)
    gone = 0
    if complete:
        keep = list(_hash_urls([li["url"] for li in listings if li.get("url")]).keys())
        async with pool.acquire() as c:
            async with c.transaction():
                stale = await c.fetch(
                    "SELECT url_hash,url_original FROM vehicle_index "
                    "WHERE entity_ulid=$1 AND NOT (url_hash = ANY($2))", ent, keep)
                if stale:
                    await c.execute(
                        "INSERT INTO vehicle_events (url_hash,url_original,source_domain,country,event_type) "
                        "SELECT h,u,$3,$4,'GONE' FROM unnest($1::text[],$2::text[]) AS t(h,u)",
                        [r["url_hash"] for r in stale], [r["url_original"] for r in stale], domain, cc)
                    await c.execute(
                        "DELETE FROM vehicle_index WHERE entity_ulid=$1 AND NOT (url_hash = ANY($2))",
                        ent, keep)
                    gone = len(stale)
    async with pool.acquire() as c:
        served = await c.fetchval("SELECT count(*) FROM vehicle_index WHERE entity_ulid=$1", ent)
    return {"domain": domain, "ent": ent, "served": served, "new": caged["new"],
            "discovered": caged["discovered"], "gone": gone}


async def verify_dealer_api(pool, ent: str, *, sample: int = 4) -> dict:
    """Prove the per-entity API view serves this dealer's rows with rich fields (what
    GET /v1/entities/{ulid}/inventory returns)."""
    async with pool.acquire() as c:
        served = await c.fetchval("SELECT count(*) FROM entity_inventory WHERE entity_ulid=$1", ent)
        with_price = await c.fetchval("SELECT count(*) FROM entity_inventory WHERE entity_ulid=$1 AND price IS NOT NULL", ent)
        with_year = await c.fetchval("SELECT count(*) FROM entity_inventory WHERE entity_ulid=$1 AND year IS NOT NULL", ent)
        kind = await c.fetchval("SELECT kind FROM source_entities WHERE entity_ulid=$1", ent)
        rows = await c.fetch(
            "SELECT source_url,title,year,price,currency,mileage_km,detail_level "
            "FROM entity_inventory WHERE entity_ulid=$1 ORDER BY source_url LIMIT $2", ent, sample)
    return {"served": served, "with_price": with_price, "with_year": with_year,
            "kind": kind, "sample": [dict(r) for r in rows]}


# --------------------------------------------------------------------------- runs
async def run_count(sess: AsyncSession, country: str, census_cap: int, stock_sample: int) -> None:
    """Dealer census + stock-sum projection. Samples ``stock_sample`` dealers' declared
    numberOfResults to estimate avg stock, then projects total = dealers × avg vs the market
    figure — the coverage-potential math, NO caging."""
    # full census count
    _, total = await census_page(sess, country, 1, size=1)
    print(f"\n== AS24 {country} dealer census ==", flush=True)
    print(f"  totalDealers (declared) = {total}", flush=True)

    # walk the census (optionally capped) to count real dealer records + sample stock
    dealers = 0
    stock_sum = 0
    sampled = 0
    over_cap = 0
    sample_every = 0
    async for rec in iter_census(sess, country, cap=census_cap):
        dealers += 1
        # sample declared stock from evenly-spaced dealers (1 profile hit each, paced)
        if sampled < stock_sample and (dealers % max(1, sample_every or 1) == 0 or sample_every == 0):
            if sample_every == 0:
                # set spacing once we know the universe size we will traverse
                sample_every = max(1, (census_cap or total or dealers) // max(1, stock_sample))
            pp = await fetch_profile_page(sess, country, rec["slug"], 1)
            if pp is not None:
                nr = pp.get("numberOfResults") or 0
                stock_sum += nr
                sampled += 1
                if nr > PER_DEALER_HARD:
                    over_cap += 1
                print(f"    sample[{sampled}] cid={rec['customerId']} stock={nr} ({rec['slug'][:40]})", flush=True)
            await asyncio.sleep(PAGE_SLEEP + random.uniform(0, PAGE_JITTER))
        if dealers % 500 == 0:
            print(f"  ...census walked {dealers}", flush=True)

    avg = (stock_sum / sampled) if sampled else 0
    universe = total or dealers
    projected = int(avg * universe)
    print(f"\n  dealers counted (walk)  = {dealers}{'  (capped)' if census_cap else ''}", flush=True)
    print(f"  stock sampled           = {sampled} dealers, sum={stock_sum}, avg={avg:.1f}/dealer", flush=True)
    print(f"  over {PER_DEALER_HARD}-cap dealers   = {over_cap}/{sampled} (need in-dealer faceting)", flush=True)
    print(f"  PROJECTED {country} stock     = {universe} dealers x {avg:.1f} = ~{projected:,}", flush=True)
    print(f"  vs AS24-{country} market figure  ~831,000 (DE)  -> coverage potential "
          f"{(100*projected/831000):.0f}%" if country == "DE" and projected else "", flush=True)


async def run_sample(sess: AsyncSession, country: str, n_dealers: int) -> None:
    """E2E proof: enumerate N real dealers' full stock, cage INSERT-only, verify each."""
    pool = await asyncpg.create_pool(DSN, min_size=2, max_size=6)
    rdb = aioredis.from_url(REDIS)
    sealed: list[dict] = []
    try:
        # pull N dealers, preferring small/mid so the pager fully enumerates (100% proof)
        candidates: list[dict] = []
        async for rec in iter_census(sess, country, cap=n_dealers * 6):
            candidates.append(rec)
            if len(candidates) >= n_dealers * 6:
                break
        random.shuffle(candidates)

        done = 0
        for rec in candidates:
            if done >= n_dealers:
                break
            if not await host_budget.wait_until_healthy(max_s=120):
                print("  host pressure; stopping sample", flush=True)
                break
            cid, slug = rec["customerId"], rec["slug"]
            listings, declared = await dealer_stock(sess, country, slug, want=None)
            if not listings:
                continue  # blocked or genuinely empty dealer — skip, try the next
            rich = [li for li in listings if li.get("price") or li.get("year")]
            res = await cage_dealer(pool, rdb, cid, country, listings, complete=False)  # INSERT-only
            api = await verify_dealer_api(pool, res["ent"])
            cov = f"{100*len(listings)/declared:.0f}%" if declared else "n/a"
            print(f"\n  DEALER cid={cid} {slug[:44]}", flush=True)
            print(f"    declared stock={declared} enumerated={len(listings)} ({len(rich)} rich) coverage={cov}", flush=True)
            print(f"    entity domain = {res['domain']}", flush=True)
            print(f"    entity_ulid   = {res['ent']}", flush=True)
            print(f"    cage: new={res['new']} served={res['served']} (reconcile=OFF, INSERT-only sample)", flush=True)
            print(f"    API: kind={api['kind']} served={api['served']} with_price={api['with_price']} with_year={api['with_year']}", flush=True)
            for r in api["sample"][:3]:
                print(f"      [{r['detail_level']}] {str(r['title'])[:40]:<40} {r['year']} {r['price']} {r['currency']} {r['mileage_km']}km", flush=True)
            sealed.append({"cid": cid, "slug": slug, "domain": res["domain"], "ent": res["ent"],
                           "declared": declared, "served": res["served"]})
            done += 1

        print(f"\n========== AS24 PER-DEALER SAMPLE — {done} dealers sealed ({country}) ==========", flush=True)
        print("  verify each (deterministic spine):", flush=True)
        for s in sealed:
            print(f"    GOWORK=off python -m verification.verifier --domain {s['domain']}", flush=True)
    finally:
        await rdb.aclose()
        await pool.close()


async def run_full(sess: AsyncSession, country: str, max_dealers: int) -> None:
    """Every dealer in the country: enumerate full stock -> cage + reconcile (per-dealer)."""
    pool = await asyncpg.create_pool(DSN, min_size=2, max_size=6)
    rdb = aioredis.from_url(REDIS)
    dealers = served_total = new_total = gone_total = 0
    try:
        async for rec in iter_census(sess, country):
            if max_dealers and dealers >= max_dealers:
                break
            if not await host_budget.wait_until_healthy(max_s=180):
                print(f"  host pressure at dealer {dealers}; stopping", flush=True)
                break
            cid, slug = rec["customerId"], rec["slug"]
            listings, declared = await dealer_stock(sess, country, slug)
            dealers += 1
            if not listings:
                continue
            res = await cage_dealer(pool, rdb, cid, country, listings, complete=True)  # reconcile
            served_total += res["served"]; new_total += res["new"]; gone_total += res["gone"]
            if dealers % 25 == 0:
                print(f"  [{dealers}] cid={cid} stock={declared} served={res['served']} "
                      f"(cum new={new_total} gone={gone_total})", flush=True)
        print(f"\n========== AS24 PER-DEALER FULL ({country}) ==========", flush=True)
        print(f"  dealers enumerated = {dealers}", flush=True)
        print(f"  served (sum)       = {served_total}  new={new_total} gone={gone_total}", flush=True)
    finally:
        await rdb.aclose()
        await pool.close()


async def main(country: str, count_only: bool, sample: int, full: bool,
               census_cap: int, max_dealers: int, stock_sample: int) -> None:
    country = country.upper()
    if country not in _COUNTRY:
        print(f"country {country} not served (have {list(_COUNTRY)})")
        return
    if not await host_budget.wait_until_healthy(max_s=60):
        print("HOST under pressure; aborting")
        return
    print(f"AS24 per-dealer seal | country={country} count_only={count_only} sample={sample} "
          f"full={full} RAM={host_budget.available_mb()}MB", flush=True)
    # Session-level impersonate ONLY (JA3 invariant); one session for census + profiles, NET lane.
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2)
    try:
        async with host_budget.slot(pool, "net"):
            async with AsyncSession(impersonate="chrome136") as sess:
                if count_only:
                    await run_count(sess, country, census_cap, stock_sample)
                elif full:
                    await run_full(sess, country, max_dealers)
                else:
                    await run_sample(sess, country, sample)
    finally:
        await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="AS24 per-dealer enumeration seal")
    ap.add_argument("--country", default="DE")
    ap.add_argument("--count-only", action="store_true")
    ap.add_argument("--sample", type=int, default=5)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--census-cap", type=int, default=0, help="cap census walk in --count-only (0=all)")
    ap.add_argument("--max-dealers", type=int, default=0, help="cap dealers in --full (0=all)")
    ap.add_argument("--stock-sample", type=int, default=30, help="dealers to sample stock in --count-only")
    a = ap.parse_args()
    asyncio.run(main(a.country, a.count_only, a.sample, a.full, a.census_cap, a.max_dealers, a.stock_sample))
