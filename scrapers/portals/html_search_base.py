"""
HtmlSearchScraper — shared engine for T1 portals whose listings live behind a
paginated HTML search surface and whose segment universe is enumerable from a
sitemap.

Where AutoScout24Scraper partitions inventory with a synthetic year×price grid,
many national T1 portals instead expose:

  * a paginated *search* surface (brand / category pages whose pager the site
    itself canonicalises — a verified `?page=N` or query param, never assumed), and
  * a *sitemap* that already enumerates every brand / model / category — the
    deterministic, datacenter-IP-friendly way to discover the segment universe
    without inventing endpoints (PLAN §3: verify-before-code).

A concrete portal declares four facts and implements two pure primitives:

  HOST          request hostname (e.g. "www.autotrack.nl")
  SITEMAP_URL   the *verified* sitemap whose <loc>s map to search segments
  DETAIL_RE     compiled regex matching a listing detail path in the search HTML
  PAGE_SIZE     listings per search page (verified live)

  _build_url(params, page_num)   search URL for one page of one segment
  _loc_to_segment(loc)           sitemap <loc> → segment dict (or None to skip)

Segments are seeded by `load_segments_from_sitemap(session)` (async, network) and
cached on the instance; `partition_params()` returns that cache synchronously, so
the scraper is a no-op until seeded — honest, and unit-testable without network.

The retry / soft-block / transport-error GET loop mirrors AutoScout24Scraper so
every T1 portal shares one hardened HTTP path. It is duplicated rather than
shared by a mixin on purpose: the AS24 path is verified and frozen, and the two
bases diverge in URL building and extraction. Robustness over premature reuse.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from abc import abstractmethod
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

# ── HTTP / WAF behaviour (mirrors autoscout24_base) ───────────────────────────
_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 503})
_CF_MARKERS: tuple[str, ...] = (
    "cf-browser-verification",
    "enable javascript and cookies to continue",
    "just a moment",
    "checking your browser",
    "__cf_chl_",
    "jschl-answer",
    "attention required! | cloudflare",
)

# Sitemap <loc> extraction — namespace/encoding-agnostic, single line per URL.
_LOC_RE: re.Pattern[str] = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)


def _is_softblocked(html: str) -> bool:
    """True when a 200 body is actually a challenge page (soft block)."""
    lo = html.lower()
    return any(marker in lo for marker in _CF_MARKERS)


class HtmlSearchScraper(BasePortalScraper):
    """
    Concrete T1 sitemap-seeded search orchestration. A portal subclasses this,
    sets HOST / SITEMAP_URL / DETAIL_RE / PAGE_SIZE, and implements _build_url +
    _loc_to_segment. Pagination cap detection and soft-block handling are inherited.
    """

    # ── per-portal knobs (subclass MUST set) ───────────────────────────────────
    HOST: str = ""                          # request hostname, e.g. "www.autotrack.nl"
    SITEMAP_URL: str = ""                    # verified sitemap enumerating segments
    DETAIL_RE: re.Pattern[str] | None = None  # listing detail path matcher

    # ── sitemap walk bounds (overridable) ──────────────────────────────────────
    MAX_SITEMAP_DEPTH: int = 3               # nested <sitemapindex> recursion limit
    MAX_SEGMENTS: int = 100_000              # hard cap on enumerated segments

    # ── retry (mirrors autoscout24_base verified defaults) ─────────────────────
    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 2.0
    REQUEST_TIMEOUT: int = 20

    def __init__(self, segments: list[dict[str, Any]] | None = None) -> None:
        # Defensive copy so callers cannot mutate our cache through their list.
        self._segments: list[dict[str, Any]] = [dict(s) for s in segments] if segments else []

    # ── validation ──────────────────────────────────────────────────────────────
    def _validate(self) -> None:
        super()._validate()
        if not self.HOST or not self.SITEMAP_URL or self.DETAIL_RE is None:
            raise ValueError(
                f"{type(self).__name__} must set HOST, SITEMAP_URL and DETAIL_RE"
            )

    # ── primitives the concrete portal must provide ────────────────────────────
    @abstractmethod
    def _build_url(self, params: dict[str, Any], page_num: int) -> str:
        """Search URL for one page of one segment. Use the site's *verified* pager."""
        ...

    @abstractmethod
    def _loc_to_segment(self, loc: str) -> dict[str, Any] | None:
        """Map one sitemap <loc> to a segment dict, or None to skip it."""
        ...

    # ── BasePortalScraper primitives ────────────────────────────────────────────
    def partition_params(self) -> list[dict[str, Any]]:
        """Return the sitemap-seeded segment cache (empty until loaded)."""
        return [dict(s) for s in self._segments]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch one search page; return deep-link detail URLs only."""
        html = await self._fetch_html(session, self._build_url(params, page_num))
        if html is None:
            return []
        return self._extract(html)

    # ── sitemap segment enumeration ─────────────────────────────────────────────
    async def load_segments_from_sitemap(self, session: Any) -> list[dict[str, Any]]:
        """
        Walk SITEMAP_URL (recursing through any <sitemapindex>), map each content
        <loc> to a segment via _loc_to_segment, dedupe, and cache on the instance.
        Returns the freshly loaded segments.
        """
        seen_locs: set[str] = set()
        seen_segs: set[tuple[tuple[str, Any], ...]] = set()
        out: list[dict[str, Any]] = []
        await self._walk_sitemap(session, self.SITEMAP_URL, 0, seen_locs, seen_segs, out)
        self._segments = out
        log.info("%s sitemap → %d segments", self.DOMAIN, len(out))
        return out

    async def _walk_sitemap(
        self,
        session: Any,
        url: str,
        depth: int,
        seen_locs: set[str],
        seen_segs: set[tuple[tuple[str, Any], ...]],
        out: list[dict[str, Any]],
    ) -> None:
        if depth > self.MAX_SITEMAP_DEPTH or len(out) >= self.MAX_SEGMENTS or url in seen_locs:
            return
        seen_locs.add(url)

        xml = await self._fetch_html(session, url)
        if not xml:
            return

        is_index = "<sitemapindex" in xml.lower()
        for raw in _LOC_RE.findall(xml):
            loc = raw.strip()
            if not loc:
                continue
            if is_index:
                await self._walk_sitemap(session, loc, depth + 1, seen_locs, seen_segs, out)
            else:
                self._add_segment(loc, seen_segs, out)
            if len(out) >= self.MAX_SEGMENTS:
                return

    def _add_segment(
        self,
        loc: str,
        seen_segs: set[tuple[tuple[str, Any], ...]],
        out: list[dict[str, Any]],
    ) -> None:
        seg = self._loc_to_segment(loc)
        if seg is None:
            return
        key = tuple(sorted(seg.items()))
        if key in seen_segs:
            return
        seen_segs.add(key)
        out.append(seg)

    # ── extraction ──────────────────────────────────────────────────────────────
    def _extract(self, html: str) -> list[str]:
        """Pull listing detail links from search HTML, deduped, prefixed with HOST."""
        seen: set[str] = set()
        out: list[str] = []
        assert self.DETAIL_RE is not None  # guaranteed by _validate
        for match in self.DETAIL_RE.finditer(html):
            full = f"https://{self.HOST}{match.group(0)}"
            if full not in seen:
                seen.add(full)
                out.append(full)
        return out

    # ── hardened GET loop (mirrors autoscout24_base) ────────────────────────────
    async def _fetch_html(self, session: Any, url: str) -> str | None:
        """
        One URL through the retry loop. Returns the 200 body, or None when every
        attempt failed / a non-block non-200 was returned. Block statuses and
        soft-block challenge pages are retried with backoff; other statuses are not.
        """
        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            response = await self._get(session, url)
            if response is None:
                await self._retry_backoff(attempt)
                continue

            status = response.status_code
            if status in _BLOCK_STATUSES:
                log.debug("HTTP %d (%d/%d) %s", status, attempt, self.RETRY_ATTEMPTS, url[:80])
                await self._retry_backoff(attempt)
                continue
            if status != 200:
                log.debug("HTTP %d (no retry) %s", status, url[:80])
                return None

            html = response.text
            if _is_softblocked(html):
                log.warning("softblock (%d/%d) %s", attempt, self.RETRY_ATTEMPTS, url[:80])
                await self._retry_backoff(attempt, factor=2.0)
                continue

            return html

        log.warning("all %d attempts failed: %s", self.RETRY_ATTEMPTS, url[:80])
        return None

    async def _get(self, session: Any, url: str) -> Any | None:
        """One GET; None on transport error so the retry loop can back off."""
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:  # transport-level: DNS, reset, timeout, proxy drop
            log.debug("transport error %s: %s", url[:80], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        """Exponential backoff, skipped on the final attempt (about to give up)."""
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(self.RETRY_BACKOFF_BASE**attempt * factor + random.uniform(0, 0.25))
