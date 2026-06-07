"""
Domain-resolution worker — multi-via, queue-claimed, RAM-safe, validated.

The scale engine for "dealers WITH web". Consumes the native ``ddg_attempts`` queue
(rows with ``domain IS NULL AND name IS NOT NULL``) with the same atomic
``FOR UPDATE SKIP LOCKED`` claim the legacy ``ddg_worker`` uses — so this coordinates
safely with other sessions/workers, is idempotent, resumable, and bounds memory to one
claim batch. For each dealer it generates candidate domains across vias in COST order
and stops at the first the homepage-validator confirms:

    1. email-domain  — the dealer's own published email apex (zero search cost); a live
                       automotive homepage is enough (the email is the provenance).
    2. directory     — national directory (FR PagesJaunes / CH local.ch); name|city + auto.
    3. web search    — DuckDuckGo → Mojeek; STRICT (distinctive name token on the page).

Outcome routing mirrors ddg_worker:
    resolved   → UPDATE domain,url (+ resolved_via in external_refs); sitemap queue picks up
    collided   → domain already owned (chain/cross-source): merge external_refs, delete row
    failed     → ddg_attempts++ , ddg_error=<reason>  (drops out of queue after MAX_ATTEMPTS)

NOTHING unvalidated is persisted. RAM-safe: low concurrency, gc + RSS-watchdog throttle
between batches, jittered politeness sleep per dealer.

    python -m scrapers.discovery.domain_resolution.worker --countries DE,ES,CH,NL,BE --limit 0
    python -m scrapers.discovery.domain_resolution.worker --countries FR --oneshot
"""
from __future__ import annotations

import argparse
import asyncio
import gc
import json
import logging
import os
import random
import time
from dataclasses import dataclass, field

import asyncpg

from scrapers.discovery.domain_resolution.candidate import email_apex, ranked_candidates
from scrapers.discovery.domain_resolution.directories import directory_candidates
from scrapers.discovery.domain_resolution.search import PROVIDER_ORDER, fetch_search_html
from scrapers.discovery.domain_resolution.validate import (
    _fetch_html,
    validate_automotive,
    validate_domain,
)

# OPT-IN local-LLM verification of validated domains (default OFF → identical behaviour).
# When ``DOMRES_LLM_VERIFY`` is set, a domain that PASSES the heuristic gate is also run
# through the fuzzy decision layer (heuristic-first; the local LLM adjudicates only the
# ambiguous band), catching FPs the keywords misread — motorcycle/tyre/body shops, B2B
# auto-software — before it is persisted. Fail-open: the LLM layer degrades to the
# heuristic if Ollama is unavailable, so enabling this never blocks the worker.
_LLM_VERIFY = os.environ.get("DOMRES_LLM_VERIFY", "").strip().lower() in ("1", "true", "yes", "on")

log = logging.getLogger("domres_worker")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [domres_worker] %(message)s",
)

_DSN = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_BATCH = int(os.environ.get("DOMRES_BATCH", "40"))
_CONC = int(os.environ.get("DOMRES_CONCURRENCY", "3"))
_MAX_ATTEMPTS = int(os.environ.get("DOMRES_MAX_ATTEMPTS", "5"))
_MIN_INTERVAL = os.environ.get("DOMRES_MIN_INTERVAL", "24 hours")
_IDLE_SLEEP = float(os.environ.get("DOMRES_IDLE_SLEEP", "30"))
_SLEEP_BASE = float(os.environ.get("DOMRES_SLEEP_BASE", "1.0"))
_RSS_LIMIT_MB = int(os.environ.get("DOMRES_RSS_LIMIT_MB", "1200"))
_VALIDATE_TOP = int(os.environ.get("DOMRES_VALIDATE_TOP", "3"))

# Atomic claim — bump ddg_last_attempt at claim time (cursor + crash recovery), filtered
# by country so this runs alongside the FR sweep when FR is excluded.
_CLAIM_SQL = f"""
WITH claimed AS (
    SELECT id
    FROM discovery_candidates
    WHERE domain IS NULL
      AND name IS NOT NULL
      AND country = ANY($2::text[])
      AND ddg_attempts < {_MAX_ATTEMPTS}
      AND (ddg_last_attempt IS NULL OR ddg_last_attempt < NOW() - INTERVAL '{_MIN_INTERVAL}')
    ORDER BY ddg_last_attempt NULLS FIRST, first_seen
    LIMIT $1
    FOR UPDATE SKIP LOCKED
)
UPDATE discovery_candidates SET ddg_last_attempt = NOW()
FROM claimed WHERE discovery_candidates.id = claimed.id
RETURNING discovery_candidates.id, discovery_candidates.country,
          discovery_candidates.name, discovery_candidates.city, discovery_candidates.email
"""

_PROMOTE_SQL = """
UPDATE discovery_candidates
SET domain = $2, url = $3, sitemap_status = 'pending', ddg_error = NULL,
    external_refs = external_refs || $4::jsonb
WHERE id = $1 AND domain IS NULL
"""

_MARK_FAIL_SQL = """
UPDATE discovery_candidates
SET ddg_attempts = ddg_attempts + 1, ddg_error = $2, ddg_last_attempt = NOW()
WHERE id = $1
"""

_COLLISION_MERGE_SQL = """
WITH moved AS (
    DELETE FROM discovery_candidates WHERE id = $1 RETURNING external_refs
)
UPDATE discovery_candidates
SET external_refs = discovery_candidates.external_refs || COALESCE(moved.external_refs, '{}'::jsonb)
FROM moved
WHERE discovery_candidates.domain = $2 AND discovery_candidates.country = $3
"""


@dataclass
class Stats:
    claimed: int = 0
    resolved: int = 0
    collided: int = 0
    failed: int = 0
    by_via: dict = field(default_factory=dict)
    by_country: dict = field(default_factory=dict)

    def bump(self, d: dict, key: str) -> None:
        d[key] = d.get(key, 0) + 1


def _rss_mb() -> float | None:
    try:
        import psutil  # type: ignore

        return psutil.Process().memory_info().rss / 1e6
    except Exception:  # noqa: BLE001 — psutil optional; batch+gc already bound RAM
        return None


def _make_session():
    import curl_cffi.requests as cr

    return cr.AsyncSession(impersonate="chrome", timeout=20)


async def _candidates(session, row) -> tuple[list[tuple[str, str, bool]], int]:
    """
    (ordered (via, host, require_name) candidates, search_pages_seen) for one dealer,
    cheapest via first. The search via exhausts providers (DDG → Mojeek): it uses the
    FIRST provider that yields candidates, but counts every provider that returned a
    usable page so the caller can tell "no web found" from "search unreachable".
    require_name drives validation strictness; email is validated automotive-only.
    """
    name, city, country = row["name"], row["city"] or "", row["country"]
    out: list[tuple[str, str, bool]] = []

    e = email_apex(row.get("email") or "")
    if e:
        out.append(("email", e, False))

    # directory candidates carry name+city provenance, but a results page can list
    # several businesses — require the dealer's distinctive name on the candidate's
    # homepage (+ strong automotive signal) so a same-city non-dealer can't slip in.
    _prov, dir_hosts = await directory_candidates(session, name, city, country)
    for h in dir_hosts[:_VALIDATE_TOP]:
        out.append((f"directory:{_prov}", h, True))

    search_pages = 0
    for provider in PROVIDER_ORDER:
        html = await fetch_search_html(session, name, city, provider)
        if not html or len(html) <= 1000:
            continue
        search_pages += 1
        ranked = ranked_candidates(html, name, country, top=_VALIDATE_TOP + 1)[:_VALIDATE_TOP]
        if ranked:
            for h, _score in ranked:
                out.append((f"search:{provider}", h, True))
            break  # got candidates — don't burn the next provider
    return out, search_pages


async def _resolve_one(pool, session, row, stats: Stats) -> None:
    country = row["country"]
    stats.bump(stats.by_country, f"{country}:claimed")

    async def _fetch(url):
        # verify=False: we only READ a candidate homepage to confirm it is the dealer;
        # small dealer sites frequently run expired/self-signed certs and rejecting them
        # would discard real dealers. No secrets are sent. Providers keep cert checks on.
        return await session.get(url, timeout=15, allow_redirects=True, verify=False)

    candidates, search_pages = await _candidates(session, row)
    resolved_host = resolved_via = None
    rejected = 0
    seen: set[str] = set()
    for via, host, require_name in candidates:
        if host in seen:
            continue
        seen.add(host)
        if via == "email":
            ok, _why = await validate_automotive(host, _fetch)
        elif _LLM_VERIFY:
            # Single fetch, then heuristic-first + LLM-on-doubt (fuzzy decision layer).
            html, _why = await _fetch_html(host, _fetch)
            if html is None:
                ok = False
            else:
                from scrapers.llm.decisions import classify_is_car_dealer
                v = classify_is_car_dealer(
                    html, row["name"], row["city"] or "", require_name=require_name)
                ok, _why = v.is_dealer, v.reason
        else:
            ok, _why = await validate_domain(
                host, row["name"], row["city"] or "", _fetch, require_name=require_name)
        if ok:
            resolved_host, resolved_via = host, via
            break
        rejected += 1

    if not resolved_host:
        # Granular reason so progress is auditable (real "no web" vs retryable throttle):
        #   candidates_rejected:N  — sites found but none validated as this dealer
        #   no_results             — search worked but surfaced no dealer site (likely no web)
        #   search_unreachable     — every search provider returned nothing (throttle/transport): retry
        if rejected:
            reason = f"candidates_rejected:{rejected}"
        elif search_pages:
            reason = "no_results"
        else:
            reason = "search_unreachable"
        await pool.execute(_MARK_FAIL_SQL, row["id"], reason)
        stats.failed += 1
        stats.bump(stats.by_via, f"fail:{reason.split(':')[0]}")
        return

    refs = json.dumps({"resolved_via": resolved_via})
    try:
        await pool.execute(_PROMOTE_SQL, row["id"], resolved_host, f"https://{resolved_host}/", refs)
        stats.resolved += 1
        stats.bump(stats.by_via, f"{resolved_via}:resolved")
        stats.bump(stats.by_country, f"{country}:resolved")
        log.info("RESOLVED %s/%s -> %s (%s)", (row["name"] or "")[:38], country, resolved_host, resolved_via)
    except asyncpg.UniqueViolationError:
        try:
            await pool.execute(_COLLISION_MERGE_SQL, row["id"], resolved_host, country)
            stats.collided += 1
            stats.bump(stats.by_via, f"{resolved_via}:collided")
        except Exception as exc:  # noqa: BLE001
            await pool.execute(_MARK_FAIL_SQL, row["id"], f"collision_err:{type(exc).__name__}"[:120])
            stats.failed += 1


async def _maybe_throttle() -> None:
    rss = _rss_mb()
    if rss is not None and rss > _RSS_LIMIT_MB:
        log.warning("RSS %.0fMB > %dMB — throttle (gc + sleep)", rss, _RSS_LIMIT_MB)
        gc.collect()
        await asyncio.sleep(8)


async def run(
    *, countries: list[str], limit: int = 0, oneshot: bool = False,
    batch: int = _BATCH, concurrency: int = _CONC,
    pool: asyncpg.Pool | None = None, session=None,
) -> Stats:
    owns_pool, owns_session = pool is None, session is None
    pool = pool or await asyncpg.create_pool(_DSN, min_size=2, max_size=6)
    session = session or _make_session()
    sem = asyncio.Semaphore(concurrency)
    stats = Stats()
    t0 = time.monotonic()
    try:
        while limit == 0 or stats.claimed < limit:
            take = batch if limit == 0 else min(batch, limit - stats.claimed)
            rows = await pool.fetch(_CLAIM_SQL, take, countries)
            if not rows:
                if oneshot or limit:
                    break
                await asyncio.sleep(_IDLE_SLEEP)
                continue
            stats.claimed += len(rows)
            mutable = [dict(r) for r in rows]

            async def _guarded(r):
                async with sem:
                    await _resolve_one(pool, session, r, stats)
                    await asyncio.sleep(_SLEEP_BASE + random.uniform(0, 0.7))

            await asyncio.gather(*(_guarded(r) for r in mutable))
            del mutable, rows
            gc.collect()
            await _maybe_throttle()
            log.info("batch: claimed=%d resolved=%d collided=%d failed=%d (%.0fs)",
                     stats.claimed, stats.resolved, stats.collided, stats.failed,
                     time.monotonic() - t0)
        log.info("DONE claimed=%d resolved=%d collided=%d failed=%d by_via=%s",
                 stats.claimed, stats.resolved, stats.collided, stats.failed, stats.by_via)
        return stats
    finally:
        if owns_session:
            try:
                await session.close()
            except Exception:  # noqa: BLE001
                pass
        if owns_pool:
            await pool.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default="DE,ES,CH,NL,BE", help="ISO-2 list; exclude FR while its sweep runs")
    ap.add_argument("--limit", type=int, default=0, help="cap claims (0 = until queue drained)")
    ap.add_argument("--batch", type=int, default=_BATCH)
    ap.add_argument("--concurrency", type=int, default=_CONC)
    ap.add_argument("--oneshot", action="store_true", help="exit when queue empties")
    args = ap.parse_args()
    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    asyncio.run(run(countries=countries, limit=args.limit, oneshot=args.oneshot,
                    batch=args.batch, concurrency=args.concurrency))


if __name__ == "__main__":
    main()
