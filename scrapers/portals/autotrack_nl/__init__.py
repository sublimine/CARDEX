"""
autotrack.nl — Netherlands aggregator (cars, ~220,054 listings).

autotrack.nl is fronted by Cloudflare with TLS-fingerprint gating but **no JS
challenge**: naked `curl_cffi` `impersonate="chrome"` passes (a plain `requests`
client returns 403 — confirming the JA3 gate is real). Tier.T1. The coordinator
injects a curl_cffi session; this scraper only issues GETs through the duck-typed
`session` and parses `response.text` as HTML, so it imports and unit-tests without
curl_cffi present.

Gold nuggets [VERIFIED 2026-06-03 against the live site — docs/research/autotrack-nl.md]:

  Search URL  GET https://www.autotrack.nl/aanbod?pageNumber={N}
  Listings    Server-rendered HTML, 30 cards per page (2 sponsored-slot dups
              between consecutive early pages — absorbed by the base `seen` set).
  Detail URL  Card markup: <a data-vehicle-id="<NID>" href="/a/<slug>-<NID>?from_srp=true">.
              NID is numeric and matches `cdn.autotrack.nl/<NID>/0-*.jpg`.
              Canonical URL = "https://www.autotrack.nl" + path without the
              ?from_srp=true tracking query (we strip it).            [VERIFIED]
  Pagination  pageNumber=1 .. 7336 (last partial page has 4 ads). pageNumber=7337
              returns 0 ads. The pager covers the entire 220k inventory — NO
              partition required.                                     [VERIFIED]

Filter vocabulary — query-string filter names like priceMin/priceMax, yearMin/
yearMax, buildYearFrom/To were each probed against the live counter and ALL
returned the unfiltered baseline (220k). autotrack.nl encodes filters as URL
path segments (e.g. /aanbod/merk/audi/), not query params. Since the global pager
already reaches the whole inventory, this scraper deliberately uses a single empty
segment — no make-name table dependency, no year×price grid.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from functools import cached_property
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 500, 502, 503})


class AutoTrackNLScraper(BasePortalScraper):
    """autotrack.nl cars via the global SSR pager (T1, no partitioning needed)."""

    DOMAIN = "autotrack.nl"
    COUNTRY = "NL"

    HOST = "www.autotrack.nl"

    # 30 cards/page; pager runs 1..7336 against the 220k inventory (VERIFIED).
    # MAX_PAGES intentionally exceeds the observed last page so the short-page
    # detector (len < PAGE_SIZE) terminates the loop naturally, with margin for
    # inventory growth between research and runtime.
    PAGE_SIZE = 30
    MAX_PAGES = 7500

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    @property
    def _search_base(self) -> str:
        return f"https://{self.HOST}/aanbod"

    @cached_property
    def _listing_re(self) -> re.Pattern[str]:
        """Match `<a … href="/a/<slug>-<NID>?from_srp=true">` detail links."""
        return re.compile(r'href="(/a/[a-z0-9\-]+-(\d+))\?from_srp=true"')

    # ── primitives ─────────────────────────────────────────────────────────────
    def partition_params(self) -> list[dict[str, Any]]:
        """Single empty segment — the global pager covers the entire inventory."""
        return [{}]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch one listing page; retry transient blocks; return canonical ad URLs."""
        url = self._build_url(page_num)
        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            response = await self._get(session, url)
            if response is None:
                await self._retry_backoff(attempt)
                continue

            status = response.status_code
            if status in _BLOCK_STATUSES:
                log.debug("HTTP %d (%d/%d) %s", status, attempt, self.RETRY_ATTEMPTS, url[:90])
                await self._retry_backoff(attempt)
                continue
            if status != 200:
                log.debug("HTTP %d (no retry) %s", status, url[:90])
                return []

            return self._extract(response.text)

        log.warning("all %d attempts failed: %s", self.RETRY_ATTEMPTS, url[:90])
        return []

    # ── helpers ────────────────────────────────────────────────────────────────
    def _build_url(self, page_num: int) -> str:
        return f"{self._search_base}?pageNumber={page_num}"

    def _extract(self, html: str) -> list[str]:
        """Canonical detail URLs from card anchors, within-page deduped on NID."""
        seen: set[str] = set()
        out: list[str] = []
        for match in self._listing_re.finditer(html):
            path = match.group(1)  # /a/<slug>-<NID>  (no ?from_srp=true)
            canonical = f"{self._base_url}{path}"
            if canonical not in seen:
                seen.add(canonical)
                out.append(canonical)
        return out

    async def _get(self, session: Any, url: str) -> Any | None:
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:  # transport-level
            log.debug("transport error %s: %s", url[:90], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(self.RETRY_BACKOFF_BASE**attempt * factor + random.uniform(0, 0.25))
