"""
Dealer harvester (frente C, point 3) — RAM-safe batch runner over dealers-with-web.

Cursors id/hash-paged over ``discovery_candidates`` (READ-ONLY; another session owns
that table), and for each dealer: resolve-or-detect its ExtractionConfig, discover a
bounded set of listing URLs, run a LIMITED sample through the existing L1→L2 seam
(``enrich_worker`` A6 + ``rich_consumer`` A7 → ``vehicles``), measure what yielded,
then PURGE the sample (validate-with-a-limit-and-purge — the local disk is a test
bench; the full dump is the VPS's job).

RAM-safety (non-negotiable — the host OOMs cumulatively, memory note 2026-06):
  * E07/Playwright concurrency is capped at 2-4 and ONE browser is reused per batch
    and closed between batches (the driver scripts own the browser lifecycle).
  * The DB is walked with a keyset cursor (id-paged), never ``fetchall`` over 30k rows.
  * Fetchers and the browser are dropped and ``gc.collect()``-ed between batches.
  * Per-dealer Redis streams are deleted before each dealer so nothing accumulates.

The orchestration is injectable (``seam_runner`` / ``purger`` / fetchers) so the
control flow is unit-testable against in-memory fakes — no network, Redis or Postgres
in the test hot path — exactly like ``generic_extractor``.
"""
from __future__ import annotations

import asyncio
import dataclasses
import gc
import logging
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Sequence

from scrapers.dealer_scraping.detector import DetectionResult, build_config, detect_web_type
from scrapers.dealer_scraping.discovery import discover_detail_urls
from scrapers.pipeline.generic_extractor import Fetcher, FetchResult
from scrapers.portals import config as portal_config
from scrapers.portals.config import PLAYWRIGHT_STRATEGIES, ExtractionConfig

log = logging.getLogger(__name__)

# ── tuning ──────────────────────────────────────────────────────────────────────
DISCOVERY_CAP = 150          # listing URLs enumerated per dealer (volume signal; cheap)
SAMPLE_LIMIT = 12            # detail pages actually extracted+persisted in validate mode
E07_CONCURRENCY = 2          # browser renders in flight — the OOM footgun ceiling
STATIC_CONCURRENCY = 4       # static curl_cffi fetches in flight
BATCH_SIZE = 20              # dealers per RAM batch (fetchers/browser reused, then freed)

# In-fetcher retry on transient throttle. Dealers rate-limit under load and return
# curl transport faults / 429 / 5xx; recovering here (sub-second backoff) is far cheaper
# than letting the enrich reclaim re-deliver after reclaim_idle_ms (~8 s/URL) — that
# 8 s-per-transient round-trip is what blew the full-dealer enumeration past its timeout.
_FETCH_RETRIES = 3
_FETCH_BACKOFF_S = 0.5       # base; doubled per attempt (0.5 / 1 / 2 s)
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})

# A persist callback: (domain, country, urls, is_e07) -> rows persisted to `vehicles`.
SeamRunner = Callable[[str, str, list[str], bool], Awaitable[int]]
# A purge callback: (urls) -> rows deleted from `vehicles` (scope-exact, by source_url).
Purger = Callable[[list[str]], Awaitable[int]]
# A remediation callback: (domain, country) -> outcome object (a RemediationResult). It is
# INJECTED rather than imported so the harvester stays free of a remediation→harvester
# import cycle, and so remediation's own revalidation harvest (which passes no remediator)
# cannot recurse. The default driver binds it to ``functools.partial(remediate, ...)``.
Remediator = Callable[[str, str], Awaitable[object]]


@dataclass
class DealerHarvestResult:
    """Per-dealer outcome — the row the report aggregates by web-type and country."""

    domain: str
    country: str
    web_type: str                 # config strategy, or "none"
    discovery: str                # sitemap | wp_rest | catalog | none
    discovered: int               # listing URLs found (capped)
    attempted: int                # sample size actually run through the seam
    persisted: int                # rows that reached `vehicles` (REAL inventory)
    yields_inventory: bool
    success_rate: float = 0.0
    drift_ok: bool = True
    newly_detected: bool = False
    purged: bool = False
    proof: dict | None = None
    error: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)
    remediation: object | None = None   # RemediationResult when drift triggered auto-repair


# ── dealer fetcher (approved stack: curl_cffi impersonate, JA3-coherent per domain) ─
def make_dealer_fetcher(*, impersonate: str = "chrome131", timeout: float = 20.0) -> Fetcher:
    """
    A ``Fetcher`` over curl_cffi with one ``AsyncSession`` per domain.

    Dealers are long-tail T0/T1 sites, so no proxy/identity rotation is needed — a
    Chrome-impersonated TLS session per domain keeps the JA3 fingerprint coherent
    page-1→N (the invariant the engine enforces) without the engine.db identity
    store. Session-level ``impersonate`` only (never per-request). Body reads are
    MemoryError-guarded — the cffi buffer OOM is unrecoverable, so degrade to an
    empty body (transient) instead of killing the host.
    """
    from curl_cffi.requests import AsyncSession

    sessions: dict[str, AsyncSession] = {}

    from scrapers.pipeline.generic_extractor import _host

    async def fetch(url: str) -> FetchResult:
        domain = _host(url)
        session = sessions.get(domain)
        if session is None:
            session = AsyncSession(impersonate=impersonate)
            sessions[domain] = session
        last_exc: Exception | None = None
        for attempt in range(_FETCH_RETRIES + 1):
            try:
                resp = await session.get(url, timeout=timeout, allow_redirects=True)
            except Exception as exc:  # noqa: BLE001 — curl transport faults are retryable
                last_exc = exc
                if attempt < _FETCH_RETRIES:
                    await asyncio.sleep(_FETCH_BACKOFF_S * (2 ** attempt))
                    continue
                raise
            # Retry transient throttle statuses in-place; on the last attempt fall
            # through and return whatever status came back (caller classifies it).
            if resp.status_code in _RETRY_STATUS and attempt < _FETCH_RETRIES:
                await asyncio.sleep(_FETCH_BACKOFF_S * (2 ** attempt))
                continue
            try:
                body = resp.content or b""
            except MemoryError:  # pragma: no cover - host-pressure only
                log.warning("MemoryError materializing %s — degrading to empty body", url)
                body = b""
            return FetchResult(url=str(getattr(resp, "url", url)), status_code=int(resp.status_code), body=body)
        raise last_exc if last_exc else RuntimeError(f"fetch failed: {url}")

    async def aclose() -> None:
        for s in list(sessions.values()):
            try:
                await s.close()
            except Exception:  # noqa: BLE001
                pass
        sessions.clear()

    fetch.aclose = aclose  # type: ignore[attr-defined]
    return fetch


# ── config resolution (point 1+2): load curated/dealer recipe, else detect+save ───
async def resolve_or_detect_config(
    domain: str,
    country: str,
    *,
    static_fetcher: Fetcher,
    e07_fetcher: Fetcher | None = None,
    save: bool = True,
) -> tuple[ExtractionConfig | None, DetectionResult | None, bool]:
    """
    Return ``(config, detection, newly_detected)`` for a dealer.

    A curated portal recipe or a previously-saved dealer recipe wins (no re-probe).
    Otherwise probe STATIC first (cheap); only if that yields nothing AND a browser
    is available do we re-probe with render — so detection pays for E07 only when it
    must. A proven config is persisted to the versioned dealer store (point 2).
    """
    cfg = portal_config.load(domain)
    if cfg is not None:
        return cfg, None, False

    detection = await detect_web_type(domain, country=country, static_fetcher=static_fetcher, e07_fetcher=None)
    if not detection.ok and e07_fetcher is not None:
        detection = await detect_web_type(
            domain, country=country, static_fetcher=static_fetcher, e07_fetcher=e07_fetcher
        )
    cfg = build_config(detection)
    if cfg is not None and save:
        portal_config.save(cfg, kind="dealer")
    return cfg, detection, True


async def discover_dealer_urls(
    domain: str,
    cfg: ExtractionConfig,
    *,
    static_fetcher: Fetcher,
    e07_fetcher: Fetcher | None = None,
    cap: int = DISCOVERY_CAP,
) -> list[str]:
    """
    Enumerate a dealer's vehicle DETAIL URLs (catalog-aware, render-fallback).

    Delegates to ``discovery.discover_detail_urls`` so harvest reaches the same real
    detail pages detection proved on: sitemap → wp → catalog → catalog-follow →
    render-follow. The browser (when supplied) is reused, bounded by ``cap``.
    """
    details, method, _home, _catalog = await discover_detail_urls(
        domain, static_fetcher=static_fetcher, e07_fetcher=e07_fetcher, cap=cap
    )
    # Recipe-driven detail filter: when the entity's recipe pins a ``detail_url_re``, keep only
    # URLs matching it — separating real vehicle PDPs from the catalog/category index pages the
    # sitemap also lists (e.g. dacia ``/stock/…-fr-fr.htm`` PDP vs ``/occasion-{make}-`` index).
    # Additive: an empty detail_url_re (the default) preserves the prior heuristic behavior.
    pattern = (cfg.endpoints.detail_url_re or "").strip()
    if pattern:
        try:
            rx = re.compile(pattern)
        except re.error as exc:
            log.warning("discover %s: invalid detail_url_re %r (%s) — skipping filter", domain, pattern, exc)
        else:
            kept = [u for u in details if rx.search(u)]
            if kept:
                log.info("discover %s: detail_url_re kept %d/%d (method=%s)", domain, len(kept), len(details), method)
                details = kept
            elif details:
                # Fail-loud, never silent: a recipe regex matching nothing is broken. Keep the
                # unfiltered set so a live dealer is never zeroed, but make the fault visible.
                log.warning("discover %s: detail_url_re %r matched 0/%d — recipe regex likely broken, using unfiltered",
                            domain, pattern, len(details))
    return details


def _refine_baseline(cfg: ExtractionConfig, discovered: int) -> ExtractionConfig:
    """Raise the drift floor to the real (uncapped-ish) discovered volume, once known."""
    if discovered <= cfg.drift_baseline.expected_min_volume:
        return cfg
    new_baseline = dataclasses.replace(cfg.drift_baseline, expected_min_volume=discovered)
    return dataclasses.replace(cfg, drift_baseline=new_baseline)


# ── per-dealer harvest (point 3+4) ───────────────────────────────────────────────
async def harvest_dealer(
    domain: str,
    country: str,
    *,
    static_fetcher: Fetcher,
    e07_fetcher: Fetcher | None,
    seam_runner: SeamRunner,
    purger: Purger,
    limit: int = SAMPLE_LIMIT,
    discovery_cap: int = DISCOVERY_CAP,
    save_config: bool = True,
    purge: bool = True,
    remediator: Remediator | None = None,
) -> DealerHarvestResult:
    """
    Detect → discover → seam (limited sample) → measure → drift → (remediate) → purge.

    When the volume drift gate trips (the saved recipe no longer matches the live site)
    and a ``remediator`` is wired, auto-remediation fires: re-detect → regenerate recipe
    → revalidate. The outcome is recorded on ``result.remediation``. ``remediator`` is
    ``None`` inside remediation's own revalidation harvest, so it never recurses.

    Returns a ``DealerHarvestResult``. Never raises for an ordinary dealer failure
    (dead site, no inventory) — those are recorded so the batch never aborts.
    """
    country = (country or "").upper()[:2]
    try:
        cfg, detection, newly = await resolve_or_detect_config(
            domain, country, static_fetcher=static_fetcher, e07_fetcher=e07_fetcher, save=save_config
        )
        if cfg is None:
            notes = detection.notes if detection else ()
            return DealerHarvestResult(
                domain=domain, country=country, web_type="none",
                discovery=(detection.discovery if detection else "none"),
                discovered=(detection.discovered if detection else 0),
                attempted=0, persisted=0, yields_inventory=False,
                newly_detected=newly, notes=notes,
            )

        is_e07 = cfg.strategy in PLAYWRIGHT_STRATEGIES
        urls = await discover_dealer_urls(
            domain, cfg, static_fetcher=static_fetcher, e07_fetcher=e07_fetcher, cap=discovery_cap
        )
        discovered = len(urls)
        if discovered == 0:
            return DealerHarvestResult(
                domain=domain, country=country, web_type=cfg.strategy,
                discovery=(detection.discovery if detection else "config"),
                discovered=0, attempted=0, persisted=0, yields_inventory=False,
                newly_detected=newly, notes=("no_listing_urls",),
            )

        # Refine the production drift floor now that we know real volume, then persist.
        if newly:
            refined = _refine_baseline(cfg, discovered)
            if refined is not cfg and save_config:
                portal_config.save(refined, kind="dealer")
                cfg = refined

        sample = urls[:limit]
        persisted = await seam_runner(domain, country, sample, is_e07)
        attempted = len(sample)
        success = persisted / attempted if attempted else 0.0

        # Drift (point 4): volume-only verdict against this source's baseline. On the
        # first run discovered == baseline → ok; a later run where the site breaks and
        # discovered collapses trips it, alerting by-source (remediation in §remediation).
        from scrapers.intelligence import drift_gate
        drift = drift_gate.evaluate_volume(cfg, discovered)

        # Auto-remediation (point 5): a tripped drift gate means the saved recipe no
        # longer matches the live site — re-detect → regenerate → revalidate. Dormant
        # until a remediator is wired; the remediator runs its OWN harvest with no
        # remediator, so this never recurses.
        remediation = None
        if not drift.ok and remediator is not None:
            log.warning(
                "drift on %s (discovered=%d < floor=%d) — triggering remediation",
                domain, discovered, cfg.drift_baseline.expected_min_volume,
            )
            remediation = await remediator(domain, country)

        # Bloque D recipe contract: on a verified success, refresh the per-entity recipe —
        # version-bump + raise the learned drift floor to the proven volume, never clobbering
        # operator edits (detail_url_re, field_map). Runs AFTER the drift verdict so a real
        # collapse is still caught against the established floor; newly-detected sources were
        # already written above with their first baseline, so only established recipes refresh.
        if save_config and persisted > 0 and not newly and discovered > cfg.drift_baseline.expected_min_volume:
            proven = dataclasses.replace(
                cfg, drift_baseline=dataclasses.replace(cfg.drift_baseline, expected_min_volume=discovered)
            )
            cfg = portal_config.emit(proven, kind="dealer")

        purged = False
        if purge:
            await purger(sample)
            purged = True
        else:
            # Not a silent accumulation: validation always purges; purge=False is a
            # deliberate production/debug mode and is logged so leftover rows are visible.
            log.info("purge skipped for %s (purge=False) — %d rows kept", domain, persisted)

        return DealerHarvestResult(
            domain=domain, country=country, web_type=cfg.strategy,
            discovery=(detection.discovery if detection else "config"),
            discovered=discovered, attempted=attempted, persisted=persisted,
            yields_inventory=persisted > 0, success_rate=round(success, 3),
            drift_ok=drift.ok, newly_detected=newly, purged=purged,
            proof=(detection.proof if detection else None),
            remediation=remediation,
        )
    except Exception as exc:  # noqa: BLE001 — one bad dealer must not abort the batch
        log.exception("harvest_dealer failed domain=%s", domain)
        return DealerHarvestResult(
            domain=domain, country=country, web_type="error", discovery="none",
            discovered=0, attempted=0, persisted=0, yields_inventory=False,
            error=f"{type(exc).__name__}: {exc}",
        )


# ── aggregation for the report ───────────────────────────────────────────────────
def aggregate(results: Sequence[DealerHarvestResult]) -> dict:
    """Roll a batch of per-dealer results into the report's headline numbers."""
    total = len(results)
    yielding = [r for r in results if r.yields_inventory]
    by_type: dict[str, dict] = {}
    by_country: dict[str, dict] = {}
    for r in results:
        t = by_type.setdefault(r.web_type, {"dealers": 0, "yielding": 0, "inventory": 0})
        t["dealers"] += 1
        t["yielding"] += int(r.yields_inventory)
        t["inventory"] += r.persisted
        c = by_country.setdefault(r.country, {"dealers": 0, "yielding": 0, "inventory": 0})
        c["dealers"] += 1
        c["yielding"] += int(r.yields_inventory)
        c["inventory"] += r.persisted
    return {
        "dealers": total,
        "yielding_dealers": len(yielding),
        "yield_rate": round(len(yielding) / total, 3) if total else 0.0,
        "total_inventory": sum(r.persisted for r in results),
        "by_web_type": by_type,
        "by_country": by_country,
    }


def free_batch_memory(*objs) -> None:
    """
    Force a collection between batches (host is RAM-bound).

    A function cannot release a CALLER's binding — ``del`` on a parameter only drops the
    local alias. So callers MUST set their own large references (``static``/``e07``/
    ``seam``) to ``None`` BEFORE calling this; here we only trigger the GC sweep that
    then reclaims the now-unreferenced curl_cffi sessions and Chromium process.
    """
    gc.collect()


# ── dealer sampling (READ-ONLY on discovery_candidates) ──────────────────────────
_COUNTRIES = ("DE", "FR", "NL", "ES", "CH", "BE")


def _sample_sql(with_source: bool) -> str:
    """SQL for a deterministic per-country dealer sample (``md5`` spread, reproducible)."""
    sql = (
        "SELECT domain, country FROM discovery_candidates "
        "WHERE country=$1 AND domain IS NOT NULL AND domain <> '' "
    )
    if with_source:
        sql += "AND source ILIKE $3 "
    sql += "ORDER BY md5(domain) LIMIT $2"
    return sql


async def fetch_sample_domains(
    pg,
    *,
    per_country: int,
    countries: Sequence[str] = _COUNTRIES,
    source_like: str | None = None,
) -> list[tuple[str, str]]:
    """
    A balanced, reproducible multi-country sample of dealers WITH a domain.

    READ-ONLY on ``discovery_candidates`` (another session owns writes). ``source_like``
    (e.g. ``'oem:%'``) biases the pick toward genuine-dealer sources for a quality
    sample; omit it for a population-representative random spread.
    """
    out: list[tuple[str, str]] = []
    async with pg.acquire() as conn:
        for c in countries:
            if source_like:
                rows = await conn.fetch(_sample_sql(True), c, per_country, source_like)
            else:
                rows = await conn.fetch(_sample_sql(False), c, per_country)
            out.extend((r["domain"], r["country"]) for r in rows)
    return out
