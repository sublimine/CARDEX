"""
Dealer scraping — live validation harness (frente C, point: validate + measure).

Reads a real multi-country sample of dealers-with-web from ``discovery_candidates``
(READ-ONLY — another session owns that table), runs each through the full per-dealer
pipeline (detect → config → discover → seam A6+A7 → vehicles), MEASURES what yields
inventory by web-type and country, then PURGES every sample (validate-with-a-limit-
and-purge; the local disk is a test bench). Emits a JSON summary for the report.

RAM-safe: country-homogeneous batches; ONE curl_cffi fetcher + ONE Playwright browser
per batch, closed between batches with a gc; per-dealer streams deleted each dealer;
E07 concurrency capped at 2. Mirrors the proven verify_seam_e07 seam wiring.

    docker run -d --rm -p 56390:6379 --name cardex-redis-throwaway redis:7-alpine
    FX_RATE_CHF=1.05 python -m scripts.run_dealer_scraping --per-country 8 --limit 10
"""
from __future__ import annotations

import argparse
import asyncio
import gc
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis.asyncio as aioredis  # noqa: E402

from scrapers import enrich_worker as a6  # noqa: E402
from scrapers import rich_consumer as a7  # noqa: E402
from scrapers.common import indexer  # noqa: E402
from scrapers.dealer_scraping import harvester as hv  # noqa: E402
from scrapers.dealer_scraping.harvester import DealerHarvestResult, aggregate, harvest_dealer  # noqa: E402
from scrapers.dealer_scraping.remediation import make_remediator  # noqa: E402
from scrapers.pipeline.playwright_extractor import PlaywrightFetcher  # noqa: E402

_DB_URL = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_THROWAWAY_REDIS = os.environ.get("THROWAWAY_REDIS_URL", "redis://localhost:56390")

_LOCALE = {"DE": "de-DE", "FR": "fr-FR", "ES": "es-ES", "NL": "nl-NL", "CH": "de-CH", "BE": "nl-BE"}
_PER_DEALER_TIMEOUT = float(os.environ.get("DEALER_TIMEOUT_S", "150"))


def _parse_domains(spec: str) -> list[tuple[str, str]]:
    """Parse an explicit ``domain:CC,domain2:CC`` list (reproducible yielder validation)."""
    out: list[tuple[str, str]] = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        dom, _, cc = item.partition(":")
        out.append((dom.strip(), (cc or "DE").strip().upper()[:2]))
    return out


def make_live_seam(rdb, static_fetcher, e07_fetcher):
    """Per-dealer seam: seed enrich_pending → A6 (E07 by config) → A7 → return persisted."""
    async def run(domain: str, country: str, urls: list[str], is_e07: bool) -> int:
        for s in (a6.ENRICH_STREAM, a6.INGESTION_STREAM):
            await rdb.delete(s)  # bound RAM + isolate dealers
        for url in urls:
            await rdb.xadd(a6.ENRICH_STREAM, {
                "h": indexer.url_hash(url), "u": url, "s": domain, "c": country,
            })
        conc = hv.E07_CONCURRENCY if is_e07 else hv.STATIC_CONCURRENCY
        await a6.run(
            redis_url=_THROWAWAY_REDIS, fetcher=static_fetcher,
            e07_fetcher=(e07_fetcher if is_e07 else None),
            limit=len(urls), batch_size=len(urls), block_ms=1500,
            concurrency=conc, default_country=country, reclaim_idle_ms=8_000,
        )
        s7 = await a7.run(
            database_url=_DB_URL, redis_url=_THROWAWAY_REDIS,
            limit=len(urls), batch_size=len(urls), block_ms=1500,
        )
        return s7.persisted
    return run


def make_live_purger(pg):
    """Scope-by-platform purge: delete vehicles by source_platform (stable across redirect/
    re-encoding — the source_url that lands in `vehicles` may differ from the discovered URL
    once the site canonicalizes www/percent-encoding, so an exact-URL purge leaks orphans),
    plus the LISTING vin_history for those VINs. Scoped to the dealer(s) just scraped."""
    from urllib.parse import urlparse

    def _platform(u: str) -> str:
        host = urlparse(u).netloc.lower().split("@")[-1].split(":")[0]
        return host[4:] if host.startswith("www.") else host

    async def purge(urls: list[str]) -> int:
        platforms = sorted({p for u in urls if u and (p := _platform(u))})
        if not platforms:
            return 0
        async with pg.acquire() as conn:
            vins = await conn.fetch(
                "SELECT DISTINCT vin FROM vehicles "
                "WHERE source_platform = ANY($1::text[]) AND vin IS NOT NULL",
                platforms,
            )
            tag = await conn.execute(
                "DELETE FROM vehicles WHERE source_platform = ANY($1::text[])", platforms
            )
            if vins:
                vinlist = [r["vin"] for r in vins]
                await conn.execute(
                    "DELETE FROM vin_history_cache WHERE vin = ANY($1::text[])", vinlist
                )
        try:
            return int(tag.split()[-1])
        except (ValueError, IndexError):
            return 0
    return purge


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


async def run_validation(*, per_country: int, limit: int, batch_size: int,
                         domains: list[tuple[str, str]] | None = None,
                         source_like: str | None = None) -> dict:
    pg = await indexer.make_pg(_DB_URL)
    rdb = aioredis.from_url(_THROWAWAY_REDIS, decode_responses=True)
    purger = make_live_purger(pg)
    results: list[DealerHarvestResult] = []
    started = time.time()
    try:
        sample = domains if domains else await hv.fetch_sample_domains(
            pg, per_country=per_country, source_like=source_like
        )
        # Country-homogeneous batches so one browser locale fits the whole batch.
        sample.sort(key=lambda dc: dc[1])
        before_total = None
        async with pg.acquire() as conn:
            before_total = await conn.fetchval("SELECT count(*) FROM vehicles")
        print(f"sample={len(sample)} dealers across {len(set(c for _, c in sample))} countries; "
              f"vehicles before={before_total}")

        for bi, batch in enumerate(_chunks(sample, batch_size)):
            locale = _LOCALE.get(batch[0][1], "en-US")
            # Direct dealer fetcher: arbitrary dealer hosts are fetchable without the
            # anti-detection engine (their sitemaps serve to a plain Chrome-impersonating
            # client). make_engine_fetcher is identity-gated for T0/T1 portals and raises
            # "no eligible identity" on a dealer with no engine.db identity — the full
            # /stock/ enumeration comes from raising discovery_cap (150→5000), not the
            # fetcher: cap=150→17, cap=5000→248 (229 real /stock/ vehicles) for dacia.
            static = hv.make_dealer_fetcher()
            e07 = None
            seam = None
            print(f"\n-- batch {bi + 1} ({len(batch)} dealers, locale={locale}) --")
            try:
                # One browser per batch (reused across the batch's dealers). Opened
                # INSIDE the try so an __aenter__ failure still hits the finally cleanup.
                e07 = PlaywrightFetcher(locale=locale)
                await e07.__aenter__()
                seam = make_live_seam(rdb, static, e07)
                # Auto-remediation: a tripped drift gate re-detects→regenerates→revalidates
                # the dealer in-flow (shares this batch's fetchers/seam/purger).
                remediator = make_remediator(
                    static_fetcher=static, e07_fetcher=e07, seam_runner=seam,
                    purger=purger, limit=limit,
                )
                for domain, country in batch:
                    t0 = time.time()
                    try:
                        r = await asyncio.wait_for(
                            harvest_dealer(
                                domain, country, static_fetcher=static, e07_fetcher=e07,
                                seam_runner=seam, purger=purger, limit=limit,
                                discovery_cap=5000,
                                remediator=remediator,
                            ),
                            timeout=_PER_DEALER_TIMEOUT,
                        )
                    except asyncio.TimeoutError:
                        r = DealerHarvestResult(domain, country.upper()[:2], "timeout", "none",
                                                0, 0, 0, False, error="per_dealer_timeout")
                    results.append(r)
                    print(f"  {domain:<34} {r.web_type:<16} disc={r.discovered:<4} "
                          f"persisted={r.persisted:<3} {'YIELDS' if r.yields_inventory else '-':<6} "
                          f"({time.time() - t0:.1f}s)" + (f" ERR={r.error}" if r.error else ""))
            finally:
                if e07 is not None:
                    await e07.__aexit__(None, None, None)
                aclose = getattr(static, "aclose", None)
                if aclose:
                    await aclose()
                # Drop the caller's own refs BEFORE the GC sweep (see free_batch_memory).
                static = e07 = seam = None
                hv.free_batch_memory()

        async with pg.acquire() as conn:
            after_total = await conn.fetchval("SELECT count(*) FROM vehicles")
        agg = aggregate(results)
        agg["elapsed_s"] = round(time.time() - started, 1)
        agg["vehicles_before"] = before_total
        agg["vehicles_after"] = after_total
        agg["purge_restored"] = (before_total == after_total)
        agg["dealers_detail"] = [vars(r) for r in results]
        return agg
    finally:
        await rdb.aclose()
        await pg.close()


def main() -> None:
    import logging
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "WARNING").upper(),
                        format="%(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-country", type=int, default=8)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--batch-size", type=int, default=12)
    ap.add_argument("--domains", default=None, help="explicit 'domain:CC,domain2:CC' list")
    ap.add_argument("--sources", default=None, help="source ILIKE filter, e.g. 'oem:%%'")
    ap.add_argument("--out", default="dealer_scraping_results.json")
    args = ap.parse_args()
    if args.batch_size < 1:
        ap.error("--batch-size must be >= 1")

    agg = asyncio.run(run_validation(
        per_country=args.per_country, limit=args.limit, batch_size=args.batch_size,
        domains=_parse_domains(args.domains) if args.domains else None,
        source_like=args.sources,
    ))
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(agg, fh, indent=2, ensure_ascii=False, default=str)

    print("\n==================== SUMMARY ====================")
    print(f"dealers={agg['dealers']} yielding={agg['yielding_dealers']} "
          f"yield_rate={agg['yield_rate']} inventory={agg['total_inventory']}")
    print(f"by_web_type={json.dumps(agg['by_web_type'])}")
    print(f"by_country={json.dumps(agg['by_country'])}")
    print(f"vehicles {agg['vehicles_before']} -> {agg['vehicles_after']} "
          f"(purge_restored={agg['purge_restored']}) elapsed={agg['elapsed_s']}s")
    print(f"results written to {args.out}")


if __name__ == "__main__":
    main()
