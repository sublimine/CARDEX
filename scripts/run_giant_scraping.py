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
from scrapers.common import indexer
from scrapers.dealer_scraping.harvester import make_dealer_fetcher
from scrapers.intelligence import count_verify as cv
from scrapers.pipeline.generic_extractor import _safe_fetch
from scrapers.portals import as24_listings as a24

_DSN = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_PAGE_SIZE = 20          # AS24 listings per page
_MAX_PAGE = 200          # AS24 hard cap: 200 pages/segment

# Concurrent page fetching makes the big TLDs tractable (AS24-DE=833k is ~7h/pass sequential).
# A GLOBAL token-bucket caps aggregate req/s regardless of concurrency (lesson from the gov-API
# throttle). AS24 (commercial, curl_cffi) tolerates more than the gov API, but stay bounded.
_GIANT_CONC = int(os.environ.get("GIANT_CONC", "6"))     # concurrent page fetches in flight
_GIANT_RATE = float(os.environ.get("GIANT_RATE", "8.0")) # global requests/sec ceiling


class _RateLimiter:
    """Global async token bucket — serializes the START of every request to <= rate/sec."""

    def __init__(self, rate: float):
        self._min_interval = 1.0 / rate if rate > 0 else 0.0
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def acquire(self) -> None:
        import time
        async with self._lock:
            now = time.monotonic()
            wait = self._next - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
            self._next = max(now, self._next) + self._min_interval


def _lst(base: str, *, lo: int | None = None, hi: int | None = None, page: int | None = None) -> str:
    # sort=age&desc=0 (oldest-first) is the STABLE order for deep pagination: new listings
    # append at the end, so paging from page 1 doesn't reshuffle under us (the relevance/
    # default sort reshuffles every refresh -> drift -> missed listings). Cuts the single-pass
    # shortfall that the count gate flagged on AS24-FR (82230/93841 = 87.6%).
    q = ["sort=age", "desc=0"]
    if lo is not None:
        q.append(f"pricefrom={lo}")
    if hi is not None:
        q.append(f"priceto={hi}")           # HALF-OPEN: caller passes hi-1 to avoid overlap
    if page is not None:
        q.append(f"page={page}")
    return f"{base}/lst?" + "&".join(q)


async def reconcile_events(pool, domain: str, country: str, harvested_urls: set[str]) -> dict[str, int]:
    """Diff-based SEEN/GONE delta for the giant path — the living layer the bulk-fill skips.

    ``run_giant_scraping`` persists rich rows to ``vehicles`` (via ``rich_consumer.persist_one``)
    but never fired ``vehicle_events``, so the verifier's ``delta`` dimension (which reads
    ``vehicle_events WHERE source_domain=$1`` and demands SEEN>0) failed for the giants. This
    closes that gap with the SAME snapshot-diff every other CARDEX delta path uses
    (``indexer`` / ``cage_platform`` / ``delta_worker``): current harvested URL set vs the prior
    SERVED set → INSERT SEEN for the new, INSERT GONE for the vanished. PG doctrine preserved:
    we only INSERT into the append-only event log here; the row mirror is ``persist_one``'s job.

    The event ledger IS the snapshot store, exactly as ``vehicle_index`` is for the seal path's
    ``insert_batch``/``delete_stale``: the prior served set is the ledger-live set for this
    domain — URL-hashes whose most-recent ``vehicle_events`` row is SEEN (not yet GONE). So:
      - first complete cycle (empty ledger): SEEN for every harvested URL, GONE for none — this
        is the snapshot being established, nothing has "vanished" against a prior that doesn't
        exist yet (the giant path's 540k served rows had ZERO ledger events; this seeds them).
      - every later complete cycle: SEEN for genuinely-new URLs, GONE for ledger-live URLs absent
        from the fresh harvest (sold/removed) — the true alta/baja.
    A URL is hashed exactly as everywhere else (``indexer.url_hash``; root-domain URLs dropped by
    ``_hash_urls``), so SEEN here and the indexer's/seal's SEEN are the same identity.

    MUST be called only on a COMPLETE cycle (gated behind ``--keep`` by the caller): a partial
    slice would GONE-mark live listings it simply did not reach — the exact trap
    ``indexer.delete_stale`` / ``cage_platform(complete=...)`` guard against.
    """
    cc = (country or "")[:2]
    harvested = indexer._hash_urls(list(harvested_urls))   # hash → url, drops root URLs
    async with pool.acquire() as conn:
        # No partition bootstrap here: the DEFAULT partition is the designed safety net (it
        # catches any ts), so an INSERT never needs a month partition to pre-exist — exactly how
        # ``indexer.insert_batch`` / ``cage_platform`` write events. Force-creating the month
        # partition would in fact FAIL when rows for that month already sit in DEFAULT.
        # Prior served set = the ledger-live set: latest event per url_hash is SEEN, not GONE.
        live_rows = await conn.fetch(
            "SELECT url_hash, url_original FROM ("
            "  SELECT DISTINCT ON (url_hash) url_hash, url_original, event_type "
            "  FROM vehicle_events WHERE source_domain=$1 "
            "  ORDER BY url_hash, ts DESC, event_id DESC"
            ") last WHERE event_type <> 'GONE'",
            domain)
    served: dict[str, str] = {r["url_hash"]: r["url_original"] for r in live_rows}

    seen_hashes = [h for h in harvested if h not in served]          # new → SEEN
    gone_hashes = [h for h in served if h not in harvested]          # vanished → GONE
    if not seen_hashes and not gone_hashes:
        return {"seen": 0, "gone": 0}

    # CHUNKED inserts (``indexer._PG_BATCH``=500), exactly like ``insert_batch``/``delete_stale``:
    # the giants run at 540k-class scale, where a single unnest of a 540k-element text[] stalls
    # for minutes (PG materializes the whole array + asyncpg serializes every URL into one bind).
    # Each chunk is its own statement; no surrounding mega-transaction so a giant seed streams in
    # bounded, restartable steps (re-running is naturally idempotent — a re-seen URL is already
    # ledger-live next time, so it is not re-SEEN'd).
    async def _emit(hash_list: list[str], url_of: dict[str, str], etype: str) -> None:
        sql = ("INSERT INTO vehicle_events (url_hash,url_original,source_domain,country,event_type) "
               f"SELECT h,u,$3,$4,'{etype}' FROM unnest($1::text[],$2::text[]) AS t(h,u)")
        for i in range(0, len(hash_list), indexer._PG_BATCH):
            chunk = hash_list[i:i + indexer._PG_BATCH]
            async with pool.acquire() as conn:
                await conn.execute(sql, chunk, [url_of[h] for h in chunk], domain, cc)

    await _emit(seen_hashes, harvested, "SEEN")
    await _emit(gone_hashes, served, "GONE")
    return {"seen": len(seen_hashes), "gone": len(gone_hashes)}


async def harvest(domain: str, country: str, *, base: str, currency: str,
                  limit: int, cap: int, max_price: int, keep: bool, passes: int = 1) -> int:
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
        c = await count_fn_async(a, b) or 0   # tolerate a transient None count (skip the segment)
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

    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=8)
    persisted = 0
    rejected: dict[str, int] = {}
    limiter = _RateLimiter(_GIANT_RATE)
    sem = asyncio.Semaphore(_GIANT_CONC)

    async def _fetch_page_rows(lo: int, hi: int, page: int):
        """Rate-limited + concurrency-bounded fetch+parse of one listing page."""
        await limiter.acquire()
        async with sem:
            r = await _safe_fetch(fetcher, _lst(base, lo=lo, hi=hi - 1, page=page))
        if r is None or r.status_code != 200:
            return None
        return a24.parse_listings(a24.extract_next_data(r.text or ""),
                                  base_url=base, currency=currency)

    try:
        # Multi-pass union: deep pagination of a LIVE list drifts (~12% missed in one pass).
        # Persist is idempotent (ON CONFLICT by URL fingerprint), so re-enumerating unions the
        # drift-missed listings. Stop when a pass adds < 0.5% (converged -> "no falta ni uno").
        # Within a segment, pages are fetched CONCURRENTLY (page count is known from seg_count),
        # bounded by the global rate limiter — makes 833k-class TLDs tractable.
        prev_in_db = 0
        in_db = 0
        # Accumulate the COMPLETE harvested URL set across all passes/segments (the snapshot for
        # the SEEN/GONE diff). Bounded by inventory size — a URL string per listing, only kept
        # when keep=True (a partial slice must never feed the reconcile and GONE-mark live rows).
        harvested_urls: set[str] = set()
        for pass_no in range(1, passes + 1):
            for (lo, hi, seg_count) in segments:
                if not keep and limit and persisted >= limit:
                    break
                pages = min(_MAX_PAGE, (seg_count // _PAGE_SIZE) + 1)
                page_results = await asyncio.gather(
                    *[_fetch_page_rows(lo, hi, pg) for pg in range(1, pages + 1)])
                for rows in page_results:
                    if not rows:
                        continue
                    for p in rows:
                        p["source_country"] = country
                        if keep and p.get("source_url"):
                            harvested_urls.add(p["source_url"])
                        res, reason = await rc.persist_one(
                            pool, p, source=platform, channel="SCRAPER", rates={"EUR": Decimal(1)},
                            entity_kind="platform")
                        if res:
                            persisted += 1
                        else:
                            rejected[reason] = rejected.get(reason, 0) + 1
                    if not keep and limit and persisted >= limit:
                        break
            async with pool.acquire() as conn:
                in_db = await conn.fetchval(
                    "SELECT count(*) FROM vehicles WHERE source_platform=$1", platform)
            new = in_db - prev_in_db
            print(f"{domain}: pass {pass_no}/{passes} -> in_db={in_db} (+{new})")
            prev_in_db = in_db
            if not keep and limit and persisted >= limit:
                break
            if pass_no > 1 and new < max(1, int(base_total * 0.005)):
                print(f"{domain}: converged (pass added <0.5%) — stopping at pass {pass_no}")
                break
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

        # Living layer: on a COMPLETE (--keep) cycle, diff the harvested snapshot against the
        # prior served set and emit SEEN (new) / GONE (vanished) into vehicle_events. Gated behind
        # keep so a partial slice never GONE-marks; the bulk-fill path above is untouched.
        if keep:
            delta = await reconcile_events(pool, domain, country, harvested_urls)
            print(f"{domain}: DELTA harvested={len(harvested_urls)} "
                  f"SEEN={delta['seen']} GONE={delta['gone']} (vehicle_events)")

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
    ap.add_argument("--passes", type=int, default=1, help="multi-pass union to beat pagination drift (converges, stops <0.5% new)")
    args = ap.parse_args()
    base = args.base_url or f"https://www.{args.domain}"
    await harvest(args.domain, args.country.upper()[:2], base=base, currency=args.currency,
                  passes=args.passes,
                  limit=0 if args.full else args.limit, cap=args.cap, max_price=args.max_price,
                  keep=args.keep)


if __name__ == "__main__":
    asyncio.run(_main())
