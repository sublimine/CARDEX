"""
Dealer detection sweep — MEASURE the dealer-with-web population (frente C, measurement).

For a real multi-country (optionally source-biased) sample of dealers, run the detector
(static; ``--e07`` adds browser render+catalog-render) and aggregate the verdict by
strategy and by NON-yield cause (embedded third-party DMS widget / SPA shell /
unreachable / no on-domain inventory). Detection is READ-ONLY — it never writes
``vehicles`` — so this is the cheap, honest census that tells us how many dealers yield
cost-zero and WHY the rest do not. Yielders are listed (with proof) for the seam harness
to then prove end-to-end.

RAM-safe: country-homogeneous batches, ONE curl_cffi fetcher + (optional) ONE browser per
batch, freed between batches; per-dealer timeout.

    python -m scripts.sweep_dealers --per-country 30 --out sweep_random.json
    python -m scripts.sweep_dealers --per-country 20 --sources 'oem:%' --e07 --out sweep_oem.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.common import indexer  # noqa: E402
from scrapers.dealer_scraping import harvester as hv  # noqa: E402
from scrapers.dealer_scraping.detector import detect_web_type  # noqa: E402
from scrapers.pipeline.playwright_extractor import PlaywrightFetcher  # noqa: E402

_DB_URL = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_LOCALE = {"DE": "de-DE", "FR": "fr-FR", "ES": "es-ES", "NL": "nl-NL", "CH": "de-CH", "BE": "nl-BE"}
_TIMEOUT = float(os.environ.get("DETECT_TIMEOUT_S", "45"))


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


async def run_sweep(*, per_country: int, source_like: str | None, use_e07: bool, batch_size: int) -> dict:
    pg = await indexer.make_pg(_DB_URL)
    started = time.time()
    rows: list[dict] = []
    try:
        sample = await hv.fetch_sample_domains(pg, per_country=per_country, source_like=source_like)
        sample.sort(key=lambda dc: dc[1])
        print(f"sweep sample={len(sample)} dealers; e07={use_e07} source={source_like or 'ALL'}")

        for bi, batch in enumerate(_chunks(sample, batch_size)):
            static = hv.make_dealer_fetcher()
            e07 = None
            try:
                if use_e07:
                    # Inside the try so an __aenter__ failure still hits finally cleanup.
                    e07 = PlaywrightFetcher(locale=_LOCALE.get(batch[0][1], "en-US"))
                    await e07.__aenter__()
                for domain, country in batch:
                    t0 = time.time()
                    try:
                        r = await asyncio.wait_for(
                            detect_web_type(domain, country=country, static_fetcher=static,
                                            e07_fetcher=e07, sample_n=2),
                            timeout=_TIMEOUT,
                        )
                        rec = {
                            "domain": domain, "country": r.country, "ok": r.ok,
                            "strategy": r.strategy, "classification": r.classification,
                            "discovery": r.discovery, "discovered": r.discovered, "proof": r.proof,
                        }
                    except asyncio.TimeoutError:
                        rec = {"domain": domain, "country": country.upper()[:2], "ok": False,
                               "strategy": "none", "classification": "timeout",
                               "discovery": "none", "discovered": 0, "proof": None}
                    rows.append(rec)
                    flag = "YIELD" if rec["ok"] else rec["classification"]
                    print(f"  {domain:<36}{rec['strategy']:<16}{flag:<22} d={rec['discovered']:<3} ({time.time()-t0:.1f}s)")
            finally:
                if e07 is not None:
                    await e07.__aexit__(None, None, None)
                ac = getattr(static, "aclose", None)
                if ac:
                    await ac()
                static = e07 = None  # drop refs before the GC sweep
                hv.free_batch_memory()
    finally:
        await pg.close()

    yielders = [r for r in rows if r["ok"]]
    cls_bucket = Counter(r["classification"].split(":")[0] for r in rows)
    dms_providers = Counter(r["classification"].split(":", 1)[1] for r in rows
                            if r["classification"].startswith("embedded_dms:"))
    by_country = Counter(r["country"] for r in rows)
    yield_by_country = Counter(r["country"] for r in yielders)
    strat = Counter(r["strategy"] for r in yielders)
    return {
        "dealers": len(rows),
        "yielding": len(yielders),
        "yield_rate": round(len(yielders) / len(rows), 3) if rows else 0.0,
        "by_classification": dict(cls_bucket.most_common()),
        "embedded_dms_providers": dict(dms_providers.most_common()),
        "yield_by_strategy": dict(strat.most_common()),
        "by_country": dict(by_country),
        "yield_by_country": dict(yield_by_country),
        "elapsed_s": round(time.time() - started, 1),
        "yielders": yielders,
        "rows": rows,
    }


def main() -> None:
    import logging
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "ERROR").upper())
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-country", type=int, default=25)
    ap.add_argument("--sources", default=None, help="source ILIKE filter, e.g. 'oem:%%'")
    ap.add_argument("--e07", action="store_true")
    ap.add_argument("--batch-size", type=int, default=15)
    ap.add_argument("--out", default="dealer_sweep.json")
    args = ap.parse_args()
    if args.batch_size < 1:
        ap.error("--batch-size must be >= 1")

    agg = asyncio.run(run_sweep(per_country=args.per_country, source_like=args.sources,
                                use_e07=args.e07, batch_size=args.batch_size))
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(agg, fh, indent=2, ensure_ascii=False, default=str)
    print("\n==================== SWEEP SUMMARY ====================")
    print(f"dealers={agg['dealers']} yielding={agg['yielding']} yield_rate={agg['yield_rate']}")
    print(f"by_classification={json.dumps(agg['by_classification'])}")
    print(f"embedded_dms_providers={json.dumps(agg['embedded_dms_providers'])}")
    print(f"yield_by_strategy={json.dumps(agg['yield_by_strategy'])}")
    print(f"yield_by_country={json.dumps(agg['yield_by_country'])} of {json.dumps(agg['by_country'])}")
    print(f"elapsed={agg['elapsed_s']}s -> {args.out}")
    if agg["yielders"]:
        print("\nYIELDERS (domain | country | strategy | proof):")
        for y in agg["yielders"]:
            print(f"  {y['domain']:<34} {y['country']} {y['strategy']:<16} {y['proof']}")


if __name__ == "__main__":
    main()
