"""
BasePortalScraper — template-method orchestration for every portal scraper.

A concrete scraper declares DOMAIN/COUNTRY and implements two primitives:
  partition_params()                   → non-overlapping segments covering inventory
  fetch_segment(session, params, page) → deep-link URLs for one page of one segment
and optionally overrides:
  subdivide_segment(params)            → finer sub-segments when a segment hits the cap

The result cap is detected structurally: when pagination consumes all MAX_PAGES
without a short page, the portal capped results and the segment is subdivided.
This is dedup-proof — it does not depend on counting URLs, so it stays correct
even for portals whose segments overlap (e.g. cumulative `price_to` filters).

`run()` is the template method the coordinator calls. It owns every cross-cutting
concern so individual scrapers never reimplement them:
  1. tier selection honouring the circuit breaker (escalate past OPEN tiers)
  2. identity allocation (warmed, trusted, domain-affine) + warming guard
  3. segment pagination with result-cap subdivision
  4. zero-URL soft-block detection (3 empty cycles → abort + trust penalty)
  5. trust accounting (+success / −softblock) and Prometheus metrics
  6. handing the collected deep links to an injected sink for delta/persistence

run() never builds the network session, the proxy, or the vehicle-data DB writes:
those are injected (`session`, `on_urls`) so the orchestration is pure and
unit-testable without live curl_cffi / Postgres / Redis. Scrapers MUST NOT
reimplement retry, proxy or identity logic — that is the engine's responsibility.
"""
from __future__ import annotations

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from sqlite3 import Connection
from typing import Any, Awaitable, Callable

from scrapers.engine.identity import store
from scrapers.engine.identity.profile import Identity, ProxyTier
from scrapers.engine.monitoring import metrics
from scrapers.engine.monitoring.softblock import ZeroUrlTracker
from scrapers.engine.proxy.tiers import requires_proxy
from scrapers.engine.router import circuit
from scrapers.engine.router.domain_map import Tier, effective_tier
from scrapers.engine.session.warming import enforce_no_extraction_before_warming

log = logging.getLogger(__name__)

# Trust accounting — SCRAPING_ENGINE.md §A1 invariant 4.
_TRUST_SUCCESS = 0.05
_TRUST_SOFTBLOCK = -1.0
# T3 portals (DataDome) are premium-only: trust_score >= 7.0 (§A1, §B fleet T3).
_PREMIUM_TRUST = 7.0

# Conservative per-request interval floor for DIRECT (no-proxy) identities, by
# portal tier: T0 = 1 req/s, T1 = 0.5 req/s (2s). A direct connection has no
# residential IP to hide behind, so it must be polite per domain. Proxied
# identities keep the jittered SLEEP_BASE rhythm (pace 0.0 → no floor).
_DIRECT_MIN_INTERVAL_S: dict[Tier, float] = {
    Tier.T0: 1.0,
    Tier.T1: 2.0,
}

UrlSink = Callable[[list[str]], Awaitable[None]]


class RunStatus(str, Enum):
    OK = "ok"
    CIRCUIT_OPEN = "circuit_open"
    NO_IDENTITY = "no_identity"
    SOFT_BLOCKED = "soft_blocked"


@dataclass(frozen=True)
class RunResult:
    """
    Outcome of one scrape cycle — what the coordinator needs to schedule next.

    URLs are streamed to the sink during the run, never accumulated here, so a
    multi-million-listing portal does not balloon the result object. `url_count` is the
    total streamed this cycle; `incomplete` flags a harvest that hit a transient
    mid-segment truncation and therefore did NOT observe the whole inventory (the cycle
    still persists what it found, but the stale GONE delete is skipped).
    """

    status: RunStatus
    tier: str
    identity_id: str | None = None
    url_count: int = 0
    segments: int = 0
    incomplete: bool = False


class _SinkBuffer:
    """
    Buffers fresh deep links and flushes them to the sink in fixed-size batches.

    Keeps at most ~`batch_size` URLs in memory at once (plus the caller's `seen` dedup
    set), so streaming a multi-million-listing portal never accumulates its whole
    harvest. `total` is the running count of URLs handed to the sink this cycle. A None
    sink (unit tests without persistence) still counts, it just does not flush.
    """

    def __init__(self, on_urls: UrlSink | None, batch_size: int) -> None:
        self._on_urls = on_urls
        self._batch = max(1, batch_size)
        self._buf: list[str] = []
        self.total = 0

    async def add(self, urls: list[str]) -> None:
        self.total += len(urls)
        if self._on_urls is None:
            return
        self._buf.extend(urls)
        while len(self._buf) >= self._batch:
            chunk = self._buf[: self._batch]
            del self._buf[: self._batch]
            await self._on_urls(chunk)

    async def flush(self) -> None:
        if self._on_urls is None or not self._buf:
            return
        chunk, self._buf = self._buf, []
        await self._on_urls(chunk)


class BasePortalScraper(ABC):

    DOMAIN: str = ""
    COUNTRY: str = ""

    # Pagination shape — overridable per portal. AS24 defaults (20/page).
    # MAX_PAGES=9999 means "exhaust the portal" — no artificial page ceiling for
    # global-pager portals. Grid portals (year x price) MUST keep a finite override:
    # MAX_PAGES is also the structural cap-detection threshold that triggers
    # subdivide_segment(), so raising it on a result-capped search surface would
    # defeat cap recovery. Each concrete scraper sets the value its surface needs.
    PAGE_SIZE: int = 20
    MAX_PAGES: int = 9999

    # Incremental flush: stream URLs to the sink every FLUSH_BATCH_SIZE so a portal
    # with millions of listings never holds its whole harvest in memory.
    FLUSH_BATCH_SIZE: int = 1000

    # Mid-pagination resilience: a full page followed by an empty one is a transient
    # block, not the end of inventory (a real end is a SHORT page). Re-fetch the empty
    # page this many times before concluding the segment truncated.
    ZERO_PAGE_REFETCH: int = 2

    # Jittered sleep: uniform timing is a bot signal (§22). Base ± jitter seconds.
    SLEEP_BASE: float = 1.2
    SLEEP_JITTER: float = 0.4

    # ── primitives the concrete scraper must provide ──────────────────────────
    @abstractmethod
    def partition_params(self) -> list[dict[str, Any]]:
        """
        Return parameter dicts that partition the portal's inventory into segments.
        Each dict is one segment (e.g. year_band + price_ceiling). Segments must be
        non-overlapping and collectively exhaustive; a segment that hits the result
        cap is subdivided via subdivide_segment().
        """
        ...

    @abstractmethod
    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch one page of one segment. Return deep-link URLs only — no root domains."""
        ...

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Finer sub-segments for a capped segment. Default: no further split."""
        return []

    # ── shared transport helper for concrete scrapers ──────────────────────────
    @staticmethod
    def _read_body(response: Any) -> str:
        """
        Materialize a response body as text, tolerating a memory-starved host.

        Reading `.text` decodes the whole body into a str; on a RAM-constrained host
        a large page can raise MemoryError (or a decode error) mid-allocation. That
        is a failed fetch, not an engine crash: returning "" lets the extractor yield
        no URLs and the pagination / soft-block machinery treat it like any empty
        page, instead of the exception unwinding all the way to the coordinator and
        aborting the whole portal harvest as `unhandled_exception`. The partial
        allocation is freed as the exception unwinds, so the next attempt — or the
        supervisor's memory-triggered restart — runs with reclaimed headroom.
        """
        try:
            text = response.text
        except (MemoryError, LookupError, UnicodeError, ValueError):
            log.warning(
                "%s response body unreadable (oversized / decode failure) — "
                "treating page as empty",
                getattr(type(response), "__name__", "response"),
            )
            return ""
        return text if isinstance(text, str) else ""

    # ── template method ───────────────────────────────────────────────────────
    async def run(
        self,
        conn: Connection,
        session: Any,
        *,
        on_urls: UrlSink | None = None,
    ) -> RunResult:
        """
        Full scrape cycle. Called by the coordinator with a built session.

        Do NOT override. Implement partition_params / fetch_segment
        (and optionally subdivide_segment).
        """
        self._validate()
        tier = self._select_tier(conn)

        if circuit.is_open(conn, self.DOMAIN, tier.value):
            log.warning("%s circuit OPEN at tier %s — skipping", self.DOMAIN, tier.value)
            return RunResult(RunStatus.CIRCUIT_OPEN, tier=tier.value)

        identity = store.pick_for_portal(
            conn,
            self.COUNTRY,
            self.DOMAIN,
            min_trust=self._min_trust(tier),
            require_proxy=requires_proxy(tier),
        )
        if identity is None:
            log.warning("%s no eligible identity for %s — needs warming", self.DOMAIN, self.COUNTRY)
            return RunResult(RunStatus.NO_IDENTITY, tier=tier.value)

        # Defensive double-check; pick_for_portal already filters warming_done.
        enforce_no_extraction_before_warming(identity, self.DOMAIN)

        pace = self._direct_pace(tier, identity)
        total, segments, soft_blocked, incomplete = await self._scrape_segments(
            session, pace, on_urls,
        )
        status = RunStatus.SOFT_BLOCKED if soft_blocked else RunStatus.OK
        self._record_outcome(conn, identity, status)

        # Stale GONE reconciliation is valid ONLY for a complete, clean cycle. A soft
        # block or a transient mid-segment truncation means we did not observe the full
        # inventory, so deleting "unseen" rows would wrongly GONE-mark live listings.
        # The INSERTs already streamed incrementally; we just defer the delete to a
        # later clean cycle rather than corrupt the index on a partial view.
        if status is RunStatus.OK and not incomplete:
            await self._finalize_sink(on_urls)
        elif incomplete:
            log.warning(
                "%s/%s incomplete harvest — skipping stale delete (transient truncation)",
                self.DOMAIN, self.COUNTRY,
            )

        log.info(
            "%s/%s done status=%s tier=%s segments=%d urls=%d incomplete=%s",
            self.DOMAIN, self.COUNTRY, status.value, tier.value, segments, total, incomplete,
        )
        return RunResult(
            status, tier=tier.value, identity_id=identity.id,
            url_count=total, segments=segments, incomplete=incomplete,
        )

    # ── orchestration internals ───────────────────────────────────────────────
    def _validate(self) -> None:
        if not self.DOMAIN or not self.COUNTRY:
            raise ValueError(f"{type(self).__name__} must set DOMAIN and COUNTRY")

    def _min_trust(self, tier: Tier) -> float:
        """T3 (DataDome) is premium-only; every other tier accepts any active identity."""
        return _PREMIUM_TRUST if tier is Tier.T3 else 0.0

    def _direct_pace(self, tier: Tier, identity: Identity) -> float:
        """
        Per-request interval floor (seconds) for this run, 0.0 = use SLEEP_BASE.

        A floor applies only to DIRECT (no-proxy) identities — the conservative
        per-domain rate limit for direct connections (1 req/s T0, 0.5 req/s T1).
        Proxied identities rotate IPs and keep the jittered SLEEP_BASE rhythm.
        """
        if identity.proxy_tier is ProxyTier.DIRECT:
            return _DIRECT_MIN_INTERVAL_S.get(tier, 0.0)
        return 0.0

    def _select_tier(self, conn: Connection) -> Tier:
        """Registry baseline, walked up past any OPEN breaker (circuit escalation)."""
        state = {
            (self.DOMAIN, t.value): circuit.get_state(conn, self.DOMAIN, t.value).value
            for t in Tier
        }
        return effective_tier(self.DOMAIN, state)

    async def _scrape_segments(
        self, session: Any, pace: float = 0.0,
        on_urls: UrlSink | None = None,
    ) -> tuple[int, int, bool, bool]:
        """
        Walk every segment, dedup deep links, and STREAM them to the sink in bounded
        batches so a portal with millions of listings never holds its harvest in RAM.

        Returns (total_urls, segments, soft_blocked, incomplete). `incomplete` is True
        when any segment hit a transient mid-pagination truncation (see `_paginate`),
        which tells `run` to skip the stale GONE delete for this cycle.
        """
        seen: set[str] = set()
        sink = _SinkBuffer(on_urls, self.FLUSH_BATCH_SIZE)
        zero = ZeroUrlTracker()
        segments = 0
        incomplete = False

        for params in self.partition_params():
            seg_count, seg_incomplete = await self._collect_segment(session, params, seen, sink, pace)
            segments += 1
            incomplete = incomplete or seg_incomplete
            metrics.record_urls_collected(self.DOMAIN, self.COUNTRY, seg_count)

            zero.record(seg_count)
            if zero.is_soft_blocked:
                log.warning("%s soft block — %d empty cycles", self.DOMAIN, zero.consecutive_empty)
                await sink.flush()
                return sink.total, segments, True, incomplete
            await self._sleep(pace)

        await sink.flush()
        return sink.total, segments, False, incomplete

    async def _collect_segment(
        self, session: Any, params: dict[str, Any], seen: set[str],
        sink: _SinkBuffer, pace: float = 0.0,
    ) -> tuple[int, bool]:
        """Paginate one segment; subdivide and re-paginate when it hits the page cap."""
        count, hit_ceiling, incomplete = await self._paginate(session, params, seen, sink, pace)
        if hit_ceiling:
            for sub in self.subdivide_segment(params):
                sub_count, _, sub_incomplete = await self._paginate(session, sub, seen, sink, pace)
                count += sub_count
                incomplete = incomplete or sub_incomplete
        return count, incomplete

    async def _paginate(
        self, session: Any, params: dict[str, Any], seen: set[str],
        sink: _SinkBuffer, pace: float = 0.0,
    ) -> tuple[int, bool, bool]:
        """
        Page through a segment, deduping against `seen`, streaming fresh links to `sink`.

        Returns (fresh_count, hit_ceiling, incomplete).
          * hit_ceiling — consumed all MAX_PAGES without a short page: the portal capped
            results structurally, so the segment is subdivided.
          * incomplete — a *full* page was followed by a *persistently empty* page mid
            segment. A real end of inventory is a SHORT page, never a sudden zero (a
            single failed fetch returns []), so we re-fetch the empty page; if it stays
            empty we stop but flag the cycle incomplete. Concluding "inventory ended" on
            a transient zero is exactly the bug that truncated 7,336-page portals to a
            few hundred pages.
        """
        fresh_count = 0
        hit_ceiling = False
        incomplete = False
        prev_full = False
        for page in range(1, self.MAX_PAGES + 1):
            page_urls = await self.fetch_segment(session, params, page)
            if not page_urls and prev_full:
                page_urls = await self._refetch_zero_page(session, params, page, pace)
                if not page_urls:
                    incomplete = True
                    break
            fresh = [u for u in page_urls if u not in seen]
            if fresh:
                seen.update(fresh)
                await sink.add(fresh)
                fresh_count += len(fresh)
            if len(page_urls) < self.PAGE_SIZE:
                break
            if page == self.MAX_PAGES:
                hit_ceiling = True
                break
            prev_full = len(page_urls) >= self.PAGE_SIZE
            await self._sleep(pace)
        return fresh_count, hit_ceiling, incomplete

    async def _refetch_zero_page(
        self, session: Any, params: dict[str, Any], page: int, pace: float = 0.0
    ) -> list[str]:
        """
        Re-fetch a page that came back empty straight after a full page.

        ZERO_PAGE_REFETCH extra attempts with a polite delay; the first non-empty result
        wins. The caller only invokes this on a mid-stream zero (never on page 1 nor
        after a short page), so an empty cell at the start of a segment costs nothing.
        """
        for _ in range(self.ZERO_PAGE_REFETCH):
            await self._sleep(pace if pace > 0.0 else self.SLEEP_BASE)
            page_urls = await self.fetch_segment(session, params, page)
            if page_urls:
                return page_urls
        return []

    async def _finalize_sink(self, on_urls: UrlSink | None) -> None:
        """Run the sink's end-of-cycle reconciliation (stale GONE delete), if it has one."""
        finalize = getattr(on_urls, "finalize", None)
        if finalize is not None:
            await finalize()

    def _record_outcome(self, conn: Connection, identity: Identity, status: RunStatus) -> None:
        if status is RunStatus.SOFT_BLOCKED:
            store.update_trust(conn, identity.id, _TRUST_SOFTBLOCK)
        else:
            store.update_trust(conn, identity.id, _TRUST_SUCCESS)
            metrics.record_success(self.DOMAIN)

    async def _sleep(self, pace: float = 0.0) -> None:
        """
        Inter-request delay. A positive `pace` is a DIRECT-connection rate-limit
        floor: jitter is added on top so the floor is never undercut (the 1/0.5
        req/s guarantee holds) while timing stays non-uniform (§22 anti-bot).
        pace 0.0 keeps the original proxied rhythm: SLEEP_BASE ± SLEEP_JITTER.
        """
        if pace > 0.0:
            delay = pace + random.uniform(0.0, self.SLEEP_JITTER)
        else:
            delay = self.SLEEP_BASE + random.uniform(-self.SLEEP_JITTER, self.SLEEP_JITTER)
        await asyncio.sleep(delay)
