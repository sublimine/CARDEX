"""
Inventory harvest at scale — measure real + potential car inventory (frente C).

Stratifies a sample across dealer SEGMENTS (brand/OEM dealers, dealer associations,
directories, OSM long-tail), harvests each dealer through the proven pipeline
(detect -> config -> discover -> seam A6+A7 -> vehicles), and reports, per segment and
country: how many dealers YIELD inventory, the real inventory SIZE per dealer
(``discovered``, capped high), a purged persistence PROOF, and an honest extrapolation
of POTENTIAL inventory = yield_rate x segment_total x avg_inventory_per_yielding_dealer.

validate-with-a-limit-and-purge: discovery measures real inventory size (cap high, just
sitemap/link enumeration — cheap), but only a small sample is persisted to ``vehicles``
to prove the seam works, then purged (the local disk is a bench; the full dump is the
VPS's job). RAM-safe: country-sorted batches, ONE browser per batch (only with --e07),
closed between batches; gc between batches; per-dealer timeout.

    docker run -d --rm -p 56390:6379 --name cardex-redis-throwaway redis:7-alpine
    python -m scripts.harvest_inventory --per-segment 6 --out inventory_scale.json
"""
from __future__ import annotations

import argparse
import asyncio
import gc
import json
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis.asyncio as aioredis  # noqa: E402

from scrapers.common import indexer  # noqa: E402
from scrapers.dealer_scraping import harvester as hv  # noqa: E402
from scrapers.dealer_scraping.discovery import discover_detail_urls  # noqa: E402
from scrapers.dealer_scraping.dms_connector import harvest_inventory_multi  # noqa: E402
from scrapers.dealer_scraping.harvester import DealerHarvestResult, harvest_dealer  # noqa: E402
from scrapers.pipeline.playwright_xhr import PlaywrightXHRFetcher  # noqa: E402
from scripts.run_dealer_scraping import _LOCALE, make_live_purger, make_live_seam  # noqa: E402

_DB_URL = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_THROWAWAY_REDIS = os.environ.get("THROWAWAY_REDIS_URL", "redis://localhost:56390")
_TIMEOUT = float(os.environ.get("DEALER_TIMEOUT_S", "90"))

# Segments ordered by expected yield: brand/OEM (homogeneous CMS) -> dealer
# associations (genuine dealers) -> directories -> OSM long-tail (noisy).
_SEGMENTS = [
    ("oem:audi", "brand:audi"), ("oem:renault", "brand:renault"),
    ("oem:seat", "brand:seat"), ("oem:dacia", "brand:dacia"),
    ("oem:vw", "brand:vw"), ("oem:hyundai", "brand:hyundai"),
    ("bovag", "assoc:bovag(NL)"), ("agvs", "assoc:agvs(CH)"),
    ("gelbeseiten", "dir:gelbeseiten(DE)"), ("osm", "osm-longtail"),
]


async def _segment_total(conn, source_like: str) -> int:
    return await conn.fetchval(
        "SELECT count(*) FROM discovery_candidates "
        "WHERE source ILIKE $1 AND domain IS NOT NULL AND domain<>''",
        source_like,
    )


async def _sample_segment(conn, source_like: str, n: int) -> list[tuple[str, str]]:
    rows = await conn.fetch(
        "SELECT domain, country FROM discovery_candidates "
        "WHERE source ILIKE $1 AND domain IS NOT NULL AND domain<>'' "
        "ORDER BY md5(domain) LIMIT $2",
        source_like, n,
    )
    return [(r["domain"], r["country"]) for r in rows]


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


async def run(*, per_segment: int, limit: int, discovery_cap: int, batch_size: int,
              use_e07: bool) -> dict:
    pg = await indexer.make_pg(_DB_URL)
    rdb = aioredis.from_url(_THROWAWAY_REDIS, decode_responses=True)
    purger = make_live_purger(pg)
    started = time.time()
    # (segment_label, (domain, country)) flat list + segment totals
    work: list[tuple[str, str, str]] = []
    totals: dict[str, int] = {}
    try:
        async with pg.acquire() as conn:
            before = await conn.fetchval("SELECT count(*) FROM vehicles")
            for source_like, label in _SEGMENTS:
                totals[label] = await _segment_total(conn, source_like)
                for dom, cc in await _sample_segment(conn, source_like, per_segment):
                    work.append((label, dom, cc))
        work.sort(key=lambda t: t[2])  # country-homogeneous batches
        print(f"sample={len(work)} dealers across {len(_SEGMENTS)} segments; "
              f"vehicles before={before}; e07={use_e07}")

        results: list[tuple[str, DealerHarvestResult, int]] = []
        for bi, batch in enumerate(_chunks(work, batch_size)):
            static = hv.make_dealer_fetcher()
            e07 = None
            seam = None
            try:
                if use_e07:
                    e07 = PlaywrightXHRFetcher(locale=_LOCALE.get(batch[0][2], "en-US"))
                    await e07.__aenter__()
                seam = make_live_seam(rdb, static, e07)
                print(f"\n-- batch {bi + 1} ({len(batch)} dealers) --")
                for label, domain, country in batch:
                    t0 = time.time()
                    try:
                        r = await asyncio.wait_for(
                            harvest_dealer(domain, country, static_fetcher=static,
                                           e07_fetcher=e07, seam_runner=seam, purger=purger,
                                           limit=limit, discovery_cap=discovery_cap),
                            timeout=_TIMEOUT,
                        )
                    except asyncio.TimeoutError:
                        r = DealerHarvestResult(domain, country.upper()[:2], "timeout", "none",
                                                0, 0, 0, False, error="timeout")
                    # DMS/XHR fallback: a dealer whose stock is an embedded widget yields
                    # nothing via detail URLs — render its catalog and capture the feed XHR.
                    dms_inv = 0
                    if e07 is not None and not r.yields_inventory and r.web_type != "timeout":
                        try:
                            _d, _m, _h, catalog = await asyncio.wait_for(
                                discover_detail_urls(domain, static_fetcher=static, cap=15), timeout=45)
                            recs = await asyncio.wait_for(
                                harvest_inventory_multi(domain, e07, country=country,
                                                        catalog_url=catalog or "", max_tries=3),
                                timeout=_TIMEOUT * 2)
                            dms_inv = len(recs)
                        except Exception:  # noqa: BLE001
                            dms_inv = 0
                    results.append((label, r, dms_inv))
                    yld = "YIELD" if r.yields_inventory else (f"DMS:{dms_inv}" if dms_inv else "-")
                    print(f"  [{label:<18}] {domain:<32} {r.web_type:<15} "
                          f"inv={r.discovered:<4} persisted={r.persisted:<3} "
                          f"{yld:<9} ({time.time()-t0:.0f}s)")
            finally:
                if e07 is not None:
                    await e07.__aexit__(None, None, None)
                ac = getattr(static, "aclose", None)
                if ac:
                    await ac()
                static = e07 = seam = None
                gc.collect()

        async with pg.acquire() as conn:
            after = await conn.fetchval("SELECT count(*) FROM vehicles")
        return _aggregate(results, totals, before, after, started)
    finally:
        await rdb.aclose()
        await pg.close()


def _aggregate(results, totals, before, after, started) -> dict:
    """Per-segment yield (static + DMS/XHR), measured inventory, and POTENTIAL extrapolation."""
    seg: dict = defaultdict(lambda: {"dealers": 0, "yielding": 0, "inv_found": 0,
                                     "persisted": 0, "dms_yielding": 0, "dms_inv": 0})
    country: dict = defaultdict(lambda: {"dealers": 0, "yielding": 0, "inv_found": 0})
    yielders = []
    for label, r, dms_inv in results:
        s = seg[label]
        s["dealers"] += 1
        any_yield = r.yields_inventory or dms_inv > 0
        s["yielding"] += int(r.yields_inventory)
        s["inv_found"] += r.discovered if r.yields_inventory else 0
        s["persisted"] += r.persisted
        s["dms_yielding"] += int(dms_inv > 0 and not r.yields_inventory)
        s["dms_inv"] += dms_inv
        c = country[r.country]
        c["dealers"] += 1
        c["yielding"] += int(any_yield)
        c["inv_found"] += (r.discovered if r.yields_inventory else 0) + dms_inv
        if r.yields_inventory or dms_inv:
            yielders.append({"segment": label, "domain": r.domain, "country": r.country,
                             "web_type": r.web_type if r.yields_inventory else "dms_xhr",
                             "inventory": r.discovered if r.yields_inventory else dms_inv,
                             "persisted": r.persisted, "proof": r.proof})

    seg_report = {}
    potential_total = 0
    for label, s in seg.items():
        n = s["dealers"]
        # combined yield = static detail yielders + DMS/widget yielders
        comb_yield = s["yielding"] + s["dms_yielding"]
        rate = round(comb_yield / n, 3) if n else 0.0
        inv_sum = s["inv_found"] + s["dms_inv"]
        avg_inv = round(inv_sum / comb_yield, 1) if comb_yield else 0.0
        total = totals.get(label, 0)
        potential = int(rate * total * avg_inv)
        potential_total += potential
        seg_report[label] = {
            "segment_total": total, "sampled": n,
            "static_yielding": s["yielding"], "dms_yielding": s["dms_yielding"],
            "combined_yield_rate": rate, "avg_inventory_per_yielder": avg_inv,
            "inventory_measured_in_sample": inv_sum, "persisted_proof": s["persisted"],
            "potential_inventory_extrapolated": potential,
        }
    return {
        "elapsed_s": round(time.time() - started, 1),
        "vehicles_before": before, "vehicles_after": after,
        "purge_restored": before == after,
        "dealers_sampled": sum(s["dealers"] for s in seg.values()),
        "static_yielding_dealers": sum(s["yielding"] for s in seg.values()),
        "dms_yielding_dealers": sum(s["dms_yielding"] for s in seg.values()),
        "inventory_measured_total": sum(s["inv_found"] + s["dms_inv"] for s in seg.values()),
        "potential_inventory_total": potential_total,
        "by_segment": seg_report,
        "by_country": {k: dict(v) for k, v in country.items()},
        "yielders": yielders,
    }


def main() -> None:
    import logging
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "ERROR").upper())
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-segment", type=int, default=6)
    ap.add_argument("--limit", type=int, default=3, help="detail pages persisted+purged per dealer (proof)")
    ap.add_argument("--discovery-cap", type=int, default=250, help="inventory-size measurement cap")
    ap.add_argument("--batch-size", type=int, default=12)
    ap.add_argument("--e07", action="store_true")
    ap.add_argument("--out", default="inventory_scale.json")
    args = ap.parse_args()
    if args.batch_size < 1:
        ap.error("--batch-size must be >= 1")

    agg = asyncio.run(run(per_segment=args.per_segment, limit=args.limit,
                          discovery_cap=args.discovery_cap, batch_size=args.batch_size,
                          use_e07=args.e07))
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(agg, fh, indent=2, ensure_ascii=False, default=str)
    print("\n==================== INVENTORY SCALE SUMMARY ====================")
    print(f"dealers_sampled={agg['dealers_sampled']} static_yield={agg['static_yielding_dealers']} "
          f"dms_xhr_yield={agg['dms_yielding_dealers']}")
    print(f"inventory_measured_in_samples={agg['inventory_measured_total']} cars")
    print(f"POTENTIAL inventory (extrapolated)={agg['potential_inventory_total']:,} cars")
    print(f"vehicles {agg['vehicles_before']}->{agg['vehicles_after']} "
          f"(purge_restored={agg['purge_restored']}) elapsed={agg['elapsed_s']}s")
    print("\nBy segment:")
    for label, s in sorted(agg["by_segment"].items(), key=lambda kv: -kv[1]["potential_inventory_extrapolated"]):
        print(f"  {label:<20} total={s['segment_total']:<6} "
              f"yield(static+dms)={s['static_yielding']}+{s['dms_yielding']}/{s['sampled']} "
              f"({s['combined_yield_rate']}) avg_inv={s['avg_inventory_per_yielder']:<6} "
              f"potential={s['potential_inventory_extrapolated']:,}")
    print(f"\nresults -> {args.out}")


if __name__ == "__main__":
    main()
