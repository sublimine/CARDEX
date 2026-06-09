"""
Giant (Tier-1) harvest harness — faceted_ssr, proxy-free, slice-then-purge.

Wires the proven proxy-free giant pieces into one runnable E2E for the Next.js giants
(AutoScout24 ×6 TLDs today; any ``__NEXT_DATA__.props.pageProps.listings`` source):

  facet-partition (plan_price_partitions, beat the 4000/seg cap, HALF-OPEN ranges to avoid
  boundary double-count) -> enumerate each segment's pages (curl_cffi Chrome, JA3-coherent,
  proxy-free) -> parse_listings -> persist_one (PG L2, dedup by fingerprint) -> count_verify
  gate (persisted-deduped vs the site's own numberOfResults) -> PURGE (slice-then-purge; the
  local DB is a test bench, the recipe + proof are what we keep; mass fill runs on the VPS).

Verified live 2026-06-09 on AS24-FR: access/pagination/count/extraction/partition all proxy-free;
a 3-page slice persisted 60 -> 51 deduped -> purged clean. See CARDEX-COMMAND/recipes/PROOF_TIER1_PROXYFREE.md.

    python -m scripts.run_giant_scraping --domain autoscout24.fr --country FR --limit 100
    python -m scripts.run_giant_scraping --domain autoscout24.fr --country FR --full --keep   # VPS-style
"""
from __future__ import annotations

import argparse
import asyncio
import os
from decimal import Decimal

import asyncpg

from scrapers import rich_consumer as rc
from scrapers.dealer_scraping.harvester import make_dealer_fetcher
from scrapers.intelligence import count_verify as cv
from scrapers.pipeline.generic_extractor import _safe_fetch
from scrapers.portals import as24_listings as a24

_DSN = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_PAGE_SIZE = 20          # AS24 listings per page
_MAX_PAGE = 200          # AS24 hard cap: 200 pages/segment


def _lst(base: str, *, lo: int | None = None, hi: int | None = None, page: int | None = None) -> str:
    q = []
    if lo is not None:
        q.append(f"pricefrom={lo}")
    if hi is not None:
        q.append(f"priceto={hi}")           # HALF-OPEN: caller passes hi-1 to avoid overlap
    if page is not None:
        q.append(f"page={page}")
    return f"{base}/lst" + ("?" + "&".join(q) if q else "")


async def harvest(domain: str, country: str, *, base: str, currency: str,
                  limit: int, cap: int, max_price: int, keep: bool) -> int:
    fetcher = make_dealer_fetcher()
    platform = domain

    async def count_fn_async(lo: int, hi: int) -> int:
        r = await _safe_fetch(fetcher, _lst(base, lo=lo, hi=hi - 1))   # half-open
        await asyncio.sleep(0.6)
        return a24.number_of_results(a24.extract_next_data(r.text or "")) if r else 0

    base_total = await count_fn_async(0, max_price + 1)
    print(f"{domain}: base numberOfResults={base_total}")

    # Plan partitions (async bisection mirroring plan_price_partitions, with a live count_fn).
    segments: list[tuple[int, int, int]] = []
    stack = [(0, max_price)]
    while stack and len(segments) < 4000:
        a, b = stack.pop()
        if b <= a:
            continue
        c = await count_fn_async(a, b)
        if c <= 0:
            continue
        if c < cap or (b - a) <= 250:
            segments.append((a, b, c))
        else:
            mid = a + (b - a) // 2
            stack.append((mid, b))
            stack.append((a, mid))
    segments.sort()
    print(f"{domain}: {len(segments)} segments (all <{cap}), planned sum={sum(c for *_, c in segments)}")

    pool = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    persisted = 0
    rejected: dict[str, int] = {}
    try:
        for (lo, hi, seg_count) in segments:
            pages = min(_MAX_PAGE, (seg_count // _PAGE_SIZE) + 1)
            for page in range(1, pages + 1):
                if not keep and limit and persisted >= limit:
                    break
                r = await _safe_fetch(fetcher, _lst(base, lo=lo, hi=hi - 1, page=page))
                if r is None or r.status_code != 200:
                    break
                rows = a24.parse_listings(a24.extract_next_data(r.text or ""),
                                          base_url=base, currency=currency)
                if not rows:
                    break
                for p in rows:
                    p["source_country"] = country
                    res, reason = await rc.persist_one(
                        pool, p, source=platform, channel="SCRAPER", rates={"EUR": Decimal(1)})
                    if res:
                        persisted += 1
                    else:
                        rejected[reason] = rejected.get(reason, 0) + 1
                await asyncio.sleep(0.6)
            if not keep and limit and persisted >= limit:
                break

        async with pool.acquire() as conn:
            in_db = await conn.fetchval(
                "SELECT count(*) FROM vehicles WHERE source_platform=$1", platform)
        verdict = cv.cross_check(base_total, {"persisted_deduped": in_db}) if keep else None
        print(f"{domain}: persisted={persisted} deduped_in_db={in_db} rejected={rejected}")
        if verdict:
            coverage = (in_db / base_total) if base_total else 0.0
            # Show COVERAGE (in_db/declared), not just the divergence in detail — anti-lie clarity.
            print(f"{domain}: GATE base={base_total} deduped={in_db} -> "
                  f"coverage={coverage:.1%} "
                  f"{'TRUSTWORTHY' if verdict.trustworthy else 'PARTIAL/CHECK'} "
                  f"(divergence {verdict.max_divergence * 100:.1f}%)")
            if not verdict.trustworthy:
                print(f"{domain}: SHORTFALL {base_total - in_db} listings ({(1 - coverage) * 100:.1f}%) — "
                      f"deep-pagination drift on a live list; needs multi-pass union + stable sort to close.")

        if not keep:
            async with pool.acquire() as conn:
                tag = await conn.execute(
                    "DELETE FROM vehicles WHERE source_platform=$1", platform)
            print(f"{domain}: PURGED ({tag}) — slice-then-purge (recipe + proof kept)")
        return in_db
    finally:
        await pool.close()


async def _main() -> None:
    ap = argparse.ArgumentParser(description="Giant Tier-1 harvest (faceted_ssr, proxy-free, slice-then-purge)")
    ap.add_argument("--domain", required=True, help="e.g. autoscout24.fr")
    ap.add_argument("--country", required=True, help="e.g. FR")
    ap.add_argument("--base-url", default=None, help="default https://www.<domain>")
    ap.add_argument("--currency", default="EUR")
    ap.add_argument("--limit", type=int, default=100, help="slice cap (ignored with --full)")
    ap.add_argument("--cap", type=int, default=4000, help="per-segment result cap")
    ap.add_argument("--max-price", type=int, default=1_000_000)
    ap.add_argument("--full", action="store_true", help="enumerate everything (VPS); implies no slice cap")
    ap.add_argument("--keep", action="store_true", help="do NOT purge (production fill); also enables the gate")
    args = ap.parse_args()
    base = args.base_url or f"https://www.{args.domain}"
    await harvest(args.domain, args.country.upper()[:2], base=base, currency=args.currency,
                  limit=0 if args.full else args.limit, cap=args.cap, max_price=args.max_price,
                  keep=args.keep)


if __name__ == "__main__":
    asyncio.run(_main())
