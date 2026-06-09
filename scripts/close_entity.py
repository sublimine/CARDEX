"""
Close ONE entity end-to-end at 100% — the template, done right (no sampling).

The unit of mission progress is a fully-closed entity: discover ALL its PDPs (not a
12-url toy), extract EVERY one through the production seam into ``vehicles`` (cage),
cross-check the count against the dealer's OWN declared total (anti-lie), show real
rows, then PURGE (slice-then-purge; the recipe + this proof are what we keep). The
retry/backoff fetcher absorbs the dealer's throttling so the full set completes.

    python -m scripts.close_entity --domain dacia-meaux.fr --country FR --pdp-re "/stock/.*-fr-fr\\.htm"
    python -m scripts.close_entity --domain X --country FR --keep   # leave caged (no purge)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis.asyncio as aioredis  # noqa: E402

from scrapers.common import indexer  # noqa: E402
from scrapers.dealer_scraping import harvester as hv  # noqa: E402
from scrapers.dealer_scraping.discovery import discover_detail_urls  # noqa: E402
from scrapers.dealer_scraping.seam import make_live_purger, make_live_seam  # noqa: E402

_DB_URL = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_THROWAWAY_REDIS = os.environ.get("THROWAWAY_REDIS_URL", "redis://localhost:56390")

# The dealer's own declared used-stock total appears as a JSON-LD numberOfItems / a
# result-count on the catalog page — the independent number to cross-check against.
_DECLARED_RES = [
    re.compile(r'"numberOfItems"\s*:\s*(\d+)'),
    re.compile(r'(\d+)\s*(?:v[ée]hicules?|annonces?|r[ée]sultats?)', re.I),
]


async def _declared_total(static, catalog_url: str | None, home_url: str) -> int | None:
    for url in (catalog_url, home_url):
        if not url:
            continue
        try:
            r = await static(url)
        except Exception:
            continue
        html = r.text or ""
        for rx in _DECLARED_RES:
            m = rx.search(html)
            if m:
                return int(m.group(1))
    return None


async def close_entity(domain: str, country: str, *, pdp_re: str, cap: int, keep: bool) -> dict:
    rx = re.compile(pdp_re)
    static = hv.make_dealer_fetcher()
    rdb = aioredis.from_url(_THROWAWAY_REDIS, decode_responses=True)
    pg = await indexer.make_pg(_DB_URL)
    t0 = time.time()
    out: dict = {"domain": domain, "country": country}
    try:
        # 1. DISCOVER ALL
        details, method, home, catalog = await discover_detail_urls(
            domain, static_fetcher=static, e07_fetcher=None, cap=cap)
        pdps = sorted({u for u in details if rx.search(u)})
        declared = await _declared_total(static, catalog, home)
        out.update(discovery_method=method, discovered_total=len(details),
                   pdps=len(pdps), declared_total=declared)
        print(f"[{domain}] discover: method={method} pdps={len(pdps)} declared={declared} ({time.time()-t0:.0f}s)")
        if not pdps:
            out["error"] = "no PDPs discovered"
            return out

        # 2. EXTRACT ALL -> cage in vehicles
        seam = make_live_seam(rdb, static, None, redis_url=_THROWAWAY_REDIS, db_url=_DB_URL, isolate=True)
        purger = make_live_purger(pg)
        t1 = time.time()
        persisted = await seam(domain, country, pdps, False)
        async with pg.acquire() as conn:
            caged = await conn.fetchval(
                "SELECT count(*) FROM vehicles WHERE source_platform=$1", domain)
            sample = await conn.fetch(
                "SELECT make,model,year,price_raw,mileage_km FROM vehicles "
                "WHERE source_platform=$1 ORDER BY price_raw DESC NULLS LAST LIMIT 6", domain)
        out.update(persisted=persisted, caged=caged, extract_s=round(time.time()-t1, 0))
        print(f"[{domain}] extract: persisted={persisted} caged={caged} ({out['extract_s']:.0f}s)")
        for r in sample:
            print(f"    {r['make']} {r['model']} {r['year']}  {r['price_raw']}EUR  {r['mileage_km']}km")

        # 3. COUNT CROSS-CHECK (anti-lie): caged vs discovered vs the site's declared total
        ratio_disc = caged / len(pdps) if pdps else 0
        ratio_decl = (caged / declared) if declared else None
        out["coverage_vs_pdps"] = round(ratio_disc, 3)
        out["coverage_vs_declared"] = round(ratio_decl, 3) if ratio_decl is not None else None
        out["sample"] = [{"make": r["make"], "model": r["model"], "year": r["year"],
                          "price_raw": r["price_raw"]} for r in sample]
        verdict = "FULL" if ratio_disc >= 0.95 else ("PARTIAL" if ratio_disc >= 0.5 else "POOR")
        out["verdict"] = verdict
        print(f"[{domain}] count-check: caged {caged} / pdps {len(pdps)} "
              f"({ratio_disc:.0%}) / declared {declared} -> {verdict}")

        # 4. PURGE (unless --keep) -> verify clean
        if keep:
            out["purged"] = 0
            out["kept"] = True
            print(f"[{domain}] KEPT caged (no purge) — {caged} vehicles live in `vehicles`")
        else:
            purged = await purger(pdps)
            async with pg.acquire() as conn:
                after = await conn.fetchval(
                    "SELECT count(*) FROM vehicles WHERE source_platform=$1", domain)
            out.update(purged=purged, after_purge=after, purge_clean=(after == 0))
            print(f"[{domain}] purge: {purged} deleted, remaining={after} (clean={after == 0})")
        out["elapsed_s"] = round(time.time() - t0, 0)
        return out
    finally:
        ac = getattr(static, "aclose", None)
        if ac:
            await ac()
        await rdb.aclose()
        await pg.close()


async def _main() -> None:
    ap = argparse.ArgumentParser(description="Close one entity end-to-end at 100%")
    ap.add_argument("--domain", required=True)
    ap.add_argument("--country", required=True)
    ap.add_argument("--pdp-re", required=True, help="regex selecting real PDP urls")
    ap.add_argument("--cap", type=int, default=2000)
    ap.add_argument("--keep", action="store_true", help="leave inventory caged (no purge)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    res = await close_entity(args.domain, args.country.upper()[:2],
                             pdp_re=args.pdp_re, cap=args.cap, keep=args.keep)
    print("\nRESULT " + json.dumps(res, ensure_ascii=False, default=str))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=2, ensure_ascii=False, default=str)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "WARNING").upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(_main())
