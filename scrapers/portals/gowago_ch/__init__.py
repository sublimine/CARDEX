"""
gowago.ch — Swiss online car leasing marketplace (~10k used cars).

Next.js SPA with SSR listing pages. Multi-language (DE/FR/EN/IT).
Leasing-focused but carries full used vehicle inventory. Accessible via
paginated SSR HTML on /en/explore/vehicleType/used.

Gold nuggets [VERIFIED 2026-06-04]:

  Search URL    GET https://gowago.ch/en/explore/vehicleType/used
  Pagination    ?page=N (1-indexed), 423 pages observed
  Detail URL    /en/listing/{brand}-{model}/{alphanumeric_id}?params
  WAF           None detected (direct SSR response to curl_cffi)
  Inventory     ~10,135 used cars
  Tech          Next.js SSR (/_next/image visible)
  Traffic       Significant CH presence
  Owner         GOWAGO AG, Zürich

Strategy: paginate /en/explore/vehicleType/used?page=N, regex-extract
listing detail URLs from SSR HTML. Single segment (no brand split needed
since all results are accessible via linear pagination).
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 500, 502, 503})

# Match gowago listing detail URLs
_LISTING_RE: re.Pattern[str] = re.compile(
    r'href="(/(?:en|de|fr|it)/listing/[a-z0-9][\w-]*/[A-Za-z0-9]+(?:\?[^"]*)?)"',
    re.IGNORECASE,
)


class GowagoCHScraper(BasePortalScraper):
    """gowago.ch used car listings via SSR HTML pagination (T1)."""

    DOMAIN = "gowago.ch"
    COUNTRY = "CH"

    HOST = "gowago.ch"
    LANG = "en"

    PAGE_SIZE = 24  # observed ~24 listings per page
    MAX_PAGES = 500  # 423 pages at ~24/page ≈ 10k

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    def partition_params(self) -> list[dict[str, Any]]:
        """Single segment — linear pagination covers all used inventory."""
        return [{}]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """No subdivision — pagination is uncapped."""
        return []

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
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

    def _build_url(self, page_num: int) -> str:
        base = f"https://{self.HOST}/{self.LANG}/explore/vehicleType/used"
        if page_num > 1:
            return f"{base}?page={page_num}"
        return base

    def _extract(self, html: str) -> list[str]:
        """Extract listing detail URLs from SSR HTML, dedup within page."""
        seen: set[str] = set()
        out: list[str] = []
        for match in _LISTING_RE.finditer(html):
            path = match.group(1)
            # Strip query params for dedup (financing params vary per render)
            clean_path = path.split("?")[0]
            url = f"https://{self.HOST}{clean_path}"
            if url not in seen:
                seen.add(url)
                out.append(url)
        return out

    async def _get(self, session: Any, url: str) -> Any | None:
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:
            log.debug("transport error %s: %s", url[:90], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(
                self.RETRY_BACKOFF_BASE ** attempt * factor + random.uniform(0, 0.25)
            )
