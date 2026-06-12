"""Seal zoomcar.fr (ex Ouest-France Auto) FR used inventory — PROXY-FREE via the OPEN sitemap.

The site front (www.zoomcar.fr) sits behind Imperva/Incapsula, but the apex host serves the
sitemap tree in the clear to a curl_cffi Chrome session (HTTP 200, application/xml). robots.txt
(apex, 200) declares ``Sitemap: https://zoomcar.fr/sitemaps/sitemapIndex.xml`` — NOT the bare
``/sitemapIndex.xml`` (that path 404s). Strategy = sitemap_then_detail.

THE HIDDEN SHARD TAIL (the dossier's warning, [VERIFIED] live): the index lists 22 ``annonces-*``
shards whose first numeric token is a PAGINATION OFFSET, not a price floor:
  annonces-voiture-{0,10000,20000,...,170000}-0.xml   (18 car shards, 10000 listings each;
                                                        last = offset 170000 -> 8295 remainder)
  annonces-utilitaire-{0,10000}-0.xml  annonces-moto-0.xml  annonces-camping-car-0.xml
A naive scraper reading only ``annonces-voiture-0-0.xml`` sees 10000 of ~178 295 cars — a ~94%
undercount. This connector enumerates EVERY offset shard. (Proof the token is an offset not a
price band: offset-90000 shard mixes EUR 5 490..19 990 cars; ``-<offset>-1.xml`` parts 404, so
the offset scheme self-terminates at the last shard's remainder — no deeper hidden level.)

Detail-URL pattern (regex-confirmed on real shards): ``https://zoomcar.fr/<slug>-<digits>.html``.
Rich fields come from the PDP ld+json (``@type`` is the LIST ``["Product","Vehicle"]`` — the stock
parser only matches bare "Car"/"Vehicle" and would yield all-None, so this connector parses it):
  - ``offers.price`` (+ ``priceCurrency`` EUR) -> CASH price. The page's financing 'mensualité'
    widget is OUTSIDE the offers block, so structured-data price is trap-safe (cash, not /mois).
  - ``mileageFromOdometer.value`` -> km, ``brand.name``+``model`` -> title.
  - year: NO ld+json year field; taken from the ``MM/YYYY`` registration date in ``description``
    (anchored on the ``\\d{2}/`` prefix so a model number like "2008" is never misread as the year).

count_verify (>=2 ways): way 1 = live sitemap PDP enumeration across ALL annonce shards
(~203 114 all / ~178 295 cars). way 2 = the audited DOSSIER_TIER1 figure ([VERIFIED] 2026-06-08:
202 219 all / 177 458 cars) — used as the independent cross-check because the on-site live counter
is JS/Incapsula-gated and unreachable on the proxy-free path; the two agree to within ~0.5%.

    py -m scripts.seal_zoomcar --sample 60 [--conc 4]    # E2E proof (INSERT-only, no GONE)
    py -m scripts.seal_zoomcar --count-only              # 2-way count verify only (sitemap sweep)
    py -m scripts.seal_zoomcar --full [--conc 4]         # exhaustive sitemap sweep (reconciles)
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
DOMAIN = "zoomcar.fr"
BASE = "https://zoomcar.fr"
SITEMAP_INDEX = "https://zoomcar.fr/sitemaps/sitemapIndex.xml"
CONFIG_REF = "configs/platforms/zoomcar.json"
SLEEP = 1.0                 # polite; open origin but no reason to hammer
SHARD_CAP = 10000           # per-shard listing cap (offset paging granularity)

# Audited DOSSIER_TIER1 cross-check ([VERIFIED] 2026-06-08): the proxy-free way-2 oracle
# (the live on-site counter needs JS behind Incapsula and is unreachable proxy-free).
DOSSIER_ALL = 202_219
DOSSIER_CARS = 177_458

LOC = re.compile(r"<loc>(.*?)</loc>")
# Individual vehicle PDP: <slug>-<digits>.html at the apex root (SEO landing pages never match).
PDP = re.compile(r"https://zoomcar\.fr/[a-z0-9][a-z0-9-]*-\d+\.html")
# Listing shards (carry vehicle PDPs); all other sub-sitemaps are SEO landing pages.
ANNONCE_PREFIXES = ("annonces-voiture-", "annonces-utilitaire-",
                    "annonces-moto-", "annonces-camping-car-")

_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
# Registration year from a MM/YYYY date in the free-text description (model-number safe).
_REGYEAR = re.compile(r"\b\d{2}/((?:19|20)\d{2})\b")


def parse_zoomcar_vehicle(html: str, url: str) -> dict:
    """zoomcar PDP ld+json (``@type``==["Product","Vehicle"]) -> cage-shape dict.
    ``offers.price`` is CASH EUR (financing 'mensualité' lives outside the offers block).
    Returns {url, title, price, year, km}; missing fields stay None."""
    make = model = name = year = km = price = None
    for m in _LD.finditer(html or ""):
        try:
            d = json.loads(m.group(1))
        except (ValueError, TypeError):
            continue
        for o in (d if isinstance(d, list) else [d]):
            if not isinstance(o, dict):
                continue
            t = o.get("@type")
            types = set(t) if isinstance(t, list) else {t}
            if not (types & {"Vehicle", "Car"}):
                continue
            name = o.get("name")
            brand = o.get("brand")
            make = brand.get("name") if isinstance(brand, dict) else brand
            model = o.get("model") if isinstance(o.get("model"), str) else None
            odo = o.get("mileageFromOdometer")
            km = odo.get("value") if isinstance(odo, dict) else odo
            off = o.get("offers") or {}
            if isinstance(off, list):
                off = off[0] if off else {}
            price = off.get("price") if isinstance(off, dict) else None
            ry = _REGYEAR.search(o.get("description") or "")
            if ry:
                year = ry.group(1)
            break
        if price is not None or name is not None:
            break
    title = name or (" ".join(str(x) for x in (make, model) if x).strip() or None)
    return {
        "url": url,
        "title": title,
        "price": int(re.sub(r"\D", "", str(price))) if price not in (None, "") else None,
        "year": int(str(year)[:4]) if year and str(year)[:4].isdigit() else None,
        "km": int(re.sub(r"\D", "", str(km))) if km not in (None, "") else None,
    }


async def _get(sess, url, *, tries: int = 3, timeout: int = 90, **kw):
    last = None
    for t in range(tries):
        try:
            return await sess.get(url, timeout=timeout, allow_redirects=True, **kw)
        except Exception as e:  # noqa: BLE001
            last = e
            if t == tries - 1:
                raise
            await asyncio.sleep(2)
    raise last  # unreachable


async def annonce_shards(sess) -> list[str]:
    """The OPEN sitemap index -> every ``annonces-*`` listing shard (the offset-paginated tail)."""
    r = await _get(sess, SITEMAP_INDEX, timeout=40)
    subs = LOC.findall(r.text or "")
    return [u for u in subs if u.rsplit("/", 1)[-1].startswith(ANNONCE_PREFIXES)]


def _shard_pdps(xml: str) -> list[str]:
    # Defensive: regex the true PDPs (==raw <loc> on these shards, verified) so a stray
    # non-PDP loc can never inflate the count.
    seen, out = set(), []
    for u in PDP.findall(xml or ""):
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


async def enumerate_sample(sess, want: int) -> list[str]:
    """Collect up to ``want`` unique PDP URLs as a REPRESENTATIVE draw of the catalog.

    Cars (``annonces-voiture-*``) are ~88% of inventory, so the sample leads with them and
    strides across several offset shards (not just the first) — a single-shard sample skews
    to whatever category sorts first (e.g. all camping-cars), which is unrepresentative and
    starves rich-field coverage. We round-robin a fixed slice from each car shard, then top up
    from the other categories, so a 60-sample mirrors the real make/price mix."""
    shards = await annonce_shards(sess)
    cars = [s for s in shards if s.rsplit("/", 1)[-1].startswith("annonces-voiture-")]
    rest = [s for s in shards if s not in cars]
    seen: list[str] = []
    sset: set[str] = set()

    async def drain(shard_list: list[str], per_shard: int) -> None:
        for sh in shard_list:
            if len(seen) >= want:
                return
            r = await _get(sess, sh)
            if r.status_code != 200:
                continue
            taken = 0
            for u in _shard_pdps(r.text):
                if u not in sset:
                    sset.add(u); seen.append(u); taken += 1
                    if taken >= per_shard or len(seen) >= want:
                        break
            await asyncio.sleep(SLEEP)

    # ~ceil(want / car-shards) per car shard so the draw spreads across the offset tail.
    per = max(1, -(-want // max(1, len(cars))))
    await drain(cars, per)
    if len(seen) < want:
        await drain(rest, want)  # top up from vans/moto/camping if cars under-fill
    return seen[:want]


async def enumerate_all(sess) -> list[str]:
    """Full PDP universe across EVERY annonce shard (the complete offset tail)."""
    shards = await annonce_shards(sess)
    seen: list[str] = []
    sset: set[str] = set()
    for sh in shards:
        r = await _get(sess, sh)
        if r.status_code != 200:
            continue
        for u in _shard_pdps(r.text):
            if u not in sset:
                sset.add(u)
                seen.append(u)
        await asyncio.sleep(SLEEP)
    return seen


async def enrich(sess, url: str) -> dict:
    r = await _get(sess, url, timeout=40)
    if r.status_code != 200:
        return {"url": url, "title": None, "price": None, "year": None, "km": None}
    return parse_zoomcar_vehicle(r.text, url)


async def count_verify(sess) -> tuple[int, int]:
    """Way 1: live sitemap PDP enumeration across ALL annonce shards (the de-dup universe).
    Way 2: the audited DOSSIER_TIER1 'all' figure (proxy-free on-site counter is JS-gated)."""
    shards = await annonce_shards(sess)
    total = 0
    cars = 0
    capped = 0
    for sh in shards:
        r = await _get(sess, sh)
        if r.status_code != 200:
            continue
        n = len(_shard_pdps(r.text))
        total += n
        if sh.rsplit("/", 1)[-1].startswith("annonces-voiture-"):
            cars += n
        if n >= SHARD_CAP:
            capped += 1
        await asyncio.sleep(SLEEP)
    print(f"  sitemap sweep: {len(shards)} annonce shards, {capped} at the {SHARD_CAP} cap, "
          f"PDP-sum={total} (cars={cars})")
    print(f"  dossier cross-check: all={DOSSIER_ALL} cars={DOSSIER_CARS}")
    return total, DOSSIER_ALL


async def run(sample: int, conc: int, count_only: bool, full: bool, skip_count: bool) -> None:
    async with AsyncSession(impersonate="chrome136") as sess:
        if not await host_budget.wait_until_healthy(max_s=60):
            print("HOST under pressure; aborting"); return
        print(f"ZOOMCAR seal | sample={sample} conc={conc} count_only={count_only} full={full} "
              f"RAM={host_budget.available_mb()}MB", flush=True)

        way1 = way2 = None
        if not skip_count:
            way1, way2 = await count_verify(sess)
        if count_only:
            print(f"\nSITEMAP-PDP-SUM={way1}  DOSSIER-ALL={way2}")
            return

        urls = await (enumerate_all(sess) if full else enumerate_sample(sess, sample))
        print(f"  enumerated {len(urls)} PDP URLs", flush=True)
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
            trap = ("ld+json offers.price = CASH (EUR); the 'mensualité' financing widget is "
                    "OUTSIDE the offers block, so structured-data price is not the monthly payment")
            ps.print_verdict("zoomcar.fr (ex Ouest-France Auto)", declared=way1,
                             way2_label="dossier-all (audited)", way2=way2,
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
