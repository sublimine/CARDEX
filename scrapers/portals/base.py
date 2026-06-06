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
from dataclasses import dataclass, field
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
    """Outcome of one scrape cycle — what the coordinator needs to schedule next."""

    status: RunStatus
    tier: str
    identity_id: str | None = None
    urls: list[str] = field(default_factory=list)
    segments: int = 0

    @property
    def url_count(self) -> int:
        return len(self.urls)


class BasePortalScraper(ABC):

    DOMAIN: str = ""
    COUNTRY: str = ""

    # Pagination shape — overridable per portal. AS24 defaults (20/page, 20 pages).
    PAGE_SIZE: int = 20
    MAX_PAGES: int = 20

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
        urls, segments, soft_blocked = await self._scrape_segments(session, pace)
        status = RunStatus.SOFT_BLOCKED if soft_blocked else RunStatus.OK
        self._record_outcome(conn, identity, status)

        if on_urls is not None and urls:
            await on_urls(urls)

        log.info(
            "%s/%s done status=%s tier=%s segments=%d urls=%d",
            self.DOMAIN, self.COUNTRY, status.value, tier.value, segments, len(urls),
        )
        return RunResult(status, tier=tier.value, identity_id=identity.id, urls=urls, segments=segments)

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
        self, session: Any, pace: float = 0.0
    ) -> tuple[list[str], int, bool]:
        """Walk every segment, dedup deep links, abort on a zero-URL soft block."""
        seen: set[str] = set()
        collected: list[str] = []
        zero = ZeroUrlTracker()
        segments = 0

        for params in self.partition_params():
            seg_urls = await self._collect_segment(session, params, seen, pace)
            segments += 1
            collected.extend(seg_urls)
            metrics.record_urls_collected(self.DOMAIN, self.COUNTRY, len(seg_urls))

            zero.record(len(seg_urls))
            if zero.is_soft_blocked:
                log.warning("%s soft block — %d empty cycles", self.DOMAIN, zero.consecutive_empty)
                return collected, segments, True
            await self._sleep(pace)

        return collected, segments, False

    async def _collect_segment(
        self, session: Any, params: dict[str, Any], seen: set[str], pace: float = 0.0
    ) -> list[str]:
        """Paginate one segment; subdivide and re-paginate when it hits the page cap."""
        urls, hit_ceiling = await self._paginate(session, params, seen, pace)
        if hit_ceiling:
            for sub in self.subdivide_segment(params):
                sub_urls, _ = await self._paginate(session, sub, seen, pace)
                urls.extend(sub_urls)
        return urls

    async def _paginate(
        self, session: Any, params: dict[str, Any], seen: set[str], pace: float = 0.0
    ) -> tuple[list[str], bool]:
        """
        Page through a segment, deduping against `seen`.

        Returns (fresh_urls, hit_ceiling). hit_ceiling is True when pagination
        consumed all MAX_PAGES without ever seeing a short page — the structural
        signal that the portal capped results and the segment needs subdivision.
        A page shorter than PAGE_SIZE means the segment is exhausted; we stop.
        """
        out: list[str] = []
        hit_ceiling = False
        for page in range(1, self.MAX_PAGES + 1):
            page_urls = await self.fetch_segment(session, params, page)
            fresh = [u for u in page_urls if u not in seen]
            seen.update(fresh)
            out.extend(fresh)
            if len(page_urls) < self.PAGE_SIZE:
                break
            if page == self.MAX_PAGES:
                hit_ceiling = True
                break
            await self._sleep(pace)
        return out, hit_ceiling

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
