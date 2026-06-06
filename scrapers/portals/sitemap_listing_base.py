"""
SitemapListingScraper — harvest deep links straight from a listing-level sitemap.

This engine's discovery job is to emit individual vehicle *detail-page* URLs for a
sink; it never extracts the vehicle data itself (that is the Go extraction stage).
Many T0/T1 portals already publish a sitemap that enumerates exactly those detail
URLs. Harvesting it is strictly better than paginating an HTML search surface or
replaying a JSON search API:

  * one (or a few) GET(s) instead of hundreds of paginated requests,
  * no pagination / search-window cap (LRP-style APIs top out at ~5k per query),
  * no WAF search-rate heuristic to trip — sitemaps are crawler-sanctioned,
  * the most datacenter-IP-friendly route a site offers,
  * and for several portals the published `/lrp/api/search` endpoint they used
    before is itself robots-disallowed, so the sitemap is *more* compliant.

A concrete portal declares only what is portal-specific:

  SITEMAP_URL    entry sitemap — a `<sitemapindex>` or a `<urlset>`
  SITEMAP_URLS   (optional) several entry sitemaps (e.g. one per country); takes
                 precedence over SITEMAP_URL when set
  DETAIL_RE      regex a `<loc>` must match to be emitted as a deep link
  CHILD_RE       (optional) regex an index child `<loc>` must match to be walked;
                 None walks every child. Use it to descend only the vehicle
                 shards and skip noise (e.g. marktplaats' paid `admarkt_*` mirror,
                 or a single language of a multilingual listing sitemap).

The walk recurses through nested `<sitemapindex>` levels (bounded by
MAX_SITEMAP_DEPTH), transparently gunzips `.gz` children (detected by magic
bytes, so it also tolerates transfer-encoded gzip), unescapes XML entities, and
emits every DETAIL_RE-matching `<loc>` exactly once. All of it runs inside
`fetch_segment` on page 1 — the engine only hands a scraper its session there —
so the scraper imports and unit-tests without curl_cffi / a browser present.

A polite delay (SITEMAP_FETCH_DELAY ± jitter) separates sibling sitemap fetches
so harvesting a 100-shard index never bursts a domain.
"""
from __future__ import annotations

import asyncio
import gzip
import logging
import random
import re
from html import unescape as _xml_unescape
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

# Block statuses retried with backoff (mirrors the rest of the fleet's HTTP path).
_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 500, 502, 503})

# Namespace/encoding-agnostic single-line <loc> extraction.
_LOC_RE: re.Pattern[str] = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)

# gzip member magic — distinguishes a `.gz` sitemap body from plain/already-decoded XML.
_GZIP_MAGIC: bytes = b"\x1f\x8b"


class SitemapListingScraper(BasePortalScraper):
    """
    Sitemap-listing discovery base. A portal sets DOMAIN / COUNTRY, a sitemap
    entry point, and the detail/child regexes; it inherits the full index walk,
    gunzip, dedup and politeness. `partition_params` is a single segment whose one
    page is the whole harvest, which the BasePortalScraper template runs unchanged.
    """

    # ── per-portal knobs ───────────────────────────────────────────────────────
    SITEMAP_URL: str = ""
    SITEMAP_URLS: tuple[str, ...] = ()
    DETAIL_RE: re.Pattern[str] | None = None
    CHILD_RE: re.Pattern[str] | None = None

    # ── walk bounds / HTTP behaviour (overridable) ─────────────────────────────
    MAX_SITEMAP_DEPTH: int = 4          # nested <sitemapindex> recursion limit
    MAX_URLS: int = 2_000_000           # hard cap on emitted detail URLs
    REQUEST_TIMEOUT: int = 30
    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 2.0

    # Inter-fetch politeness between sibling sitemap files (one domain, many shards).
    SITEMAP_FETCH_DELAY: float = 1.0
    SITEMAP_FETCH_JITTER: float = 0.4

    # One segment, harvested in a single page-1 call.
    PAGE_SIZE: int = 1
    MAX_PAGES: int = 1

    # ── validation ──────────────────────────────────────────────────────────────
    def _validate(self) -> None:
        super()._validate()
        if not self._entry_sitemaps() or self.DETAIL_RE is None:
            raise ValueError(
                f"{type(self).__name__} must set SITEMAP_URL (or SITEMAP_URLS) and DETAIL_RE"
            )

    def _entry_sitemaps(self) -> tuple[str, ...]:
        if self.SITEMAP_URLS:
            return self.SITEMAP_URLS
        return (self.SITEMAP_URL,) if self.SITEMAP_URL else ()

    # ── BasePortalScraper primitives ────────────────────────────────────────────
    def partition_params(self) -> list[dict[str, Any]]:
        """Single segment — the sitemap walk covers the whole inventory in one pass."""
        return [{}]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """No subdivision — a sitemap has no result cap to recover from."""
        return []

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Page 1 harvests the entire sitemap; later pages are empty (segment done)."""
        if page_num > 1:
            return []
        return await self._harvest(session)

    # ── sitemap harvest ─────────────────────────────────────────────────────────
    async def _harvest(self, session: Any) -> list[str]:
        seen_sitemaps: set[str] = set()
        seen_urls: set[str] = set()
        out: list[str] = []
        for i, entry in enumerate(self._entry_sitemaps()):
            if i:
                await self._sitemap_pause()
            await self._walk(session, entry, 0, seen_sitemaps, seen_urls, out)
            if len(out) >= self.MAX_URLS:
                break
        log.info("%s sitemap harvest → %d detail URLs", self.DOMAIN, len(out))
        return out

    async def _walk(
        self,
        session: Any,
        url: str,
        depth: int,
        seen_sitemaps: set[str],
        seen_urls: set[str],
        out: list[str],
    ) -> None:
        if depth > self.MAX_SITEMAP_DEPTH or url in seen_sitemaps or len(out) >= self.MAX_URLS:
            return
        seen_sitemaps.add(url)

        xml = await self._fetch_sitemap(session, url)
        if not xml:
            return

        is_index = "<sitemapindex" in xml[:4096].lower()
        children: list[str] = []
        assert self.DETAIL_RE is not None  # guaranteed by _validate
        for raw in _LOC_RE.findall(xml):
            loc = _xml_unescape(raw.strip())
            if not loc:
                continue
            if is_index:
                if self.CHILD_RE is None or self.CHILD_RE.search(loc):
                    children.append(loc)
            elif self.DETAIL_RE.search(loc) and loc not in seen_urls:
                seen_urls.add(loc)
                out.append(loc)
                if len(out) >= self.MAX_URLS:
                    return

        for i, child in enumerate(children):
            if i:
                await self._sitemap_pause()
            await self._walk(session, child, depth + 1, seen_sitemaps, seen_urls, out)
            if len(out) >= self.MAX_URLS:
                return

    # ── transport ─────────────────────────────────────────────────────────────
    async def _fetch_sitemap(self, session: Any, url: str) -> str | None:
        """One sitemap URL through the retry loop; returns decoded XML text or None."""
        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            try:
                response = await session.get(url, timeout=self.REQUEST_TIMEOUT)
            except Exception as exc:  # transport-level: DNS, reset, timeout, proxy drop
                log.debug("%s sitemap transport error %s: %s", self.DOMAIN, url[:90], exc)
                response = None

            if response is None:
                await self._retry_backoff(attempt)
                continue

            status = response.status_code
            if status in _BLOCK_STATUSES:
                log.debug("%s sitemap HTTP %d (%d/%d) %s", self.DOMAIN, status, attempt, self.RETRY_ATTEMPTS, url[:90])
                await self._retry_backoff(attempt)
                continue
            if status != 200:
                log.debug("%s sitemap HTTP %d (no retry) %s", self.DOMAIN, status, url[:90])
                return None

            return self._decode_xml(response)

        log.warning("%s sitemap all %d attempts failed: %s", self.DOMAIN, self.RETRY_ATTEMPTS, url[:90])
        return None

    @staticmethod
    def _decode_xml(response: Any) -> str:
        """
        Return the sitemap body as text, transparently gunzipping a `.gz` member.

        gzip is detected by magic bytes on `.content`, so it handles both a gzipped
        sitemap *file* (served raw) and tolerates a non-gzipped body; a response that
        exposes only `.text` (e.g. the unit-test fake) falls straight through.
        """
        content = getattr(response, "content", None)
        if isinstance(content, (bytes, bytearray)) and content[:2] == _GZIP_MAGIC:
            try:
                return gzip.decompress(bytes(content)).decode("utf-8", "replace")
            except (OSError, EOFError):
                pass
        text = getattr(response, "text", "")
        return text if isinstance(text, str) else ""

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        """Exponential backoff, skipped on the final attempt (about to give up)."""
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(self.RETRY_BACKOFF_BASE**attempt * factor + random.uniform(0, 0.25))

    async def _sitemap_pause(self) -> None:
        """Polite, jittered gap between sibling sitemap fetches on one domain."""
        if self.SITEMAP_FETCH_DELAY > 0 or self.SITEMAP_FETCH_JITTER > 0:
            await asyncio.sleep(self.SITEMAP_FETCH_DELAY + random.uniform(0, self.SITEMAP_FETCH_JITTER))
