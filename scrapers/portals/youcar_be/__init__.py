"""
youcar.be — Belgium, classifieds portal for dealers + private sellers.

Multi-language SSR site (NL/FR/EN) with search functionality at /nl/search
and /fr/search. Brand and body-type facets available. Dealers and private
sellers list vehicles.

Gold nuggets [research 2026-06-04]:

  Search base   GET https://www.youcar.be/nl/search  (or /fr/search)  [VERIFIED via Google]
  Brand filter  /fr/search/brand  (brand index page)                   [VERIFIED via Google]
  Body filter   /fr/search/category                                    [VERIFIED via Google]
  Detail URL    /fr/buy/{brand}/{model-slug}  OR  /nl/buy/{slug}       [ASSUMED]
  Pagination    ?page=N  (1-indexed, assumed)                          [ASSUMED]
  Listing re    href="/(?:nl|fr|en)/buy/[^"]+                          [ASSUMED]
  WAF           Unknown — assumed T1 (small Belgian classifieds site)   [NEEDS live probe]
  Inventory     Unknown (multi-brand, dealers + private)               [UNVERIFIED]
  Tech stack    SSR HTML, likely Laravel or Next.js                    [ASSUMED]
  Sitemap       /en/sitemap exists                                     [VERIFIED via Google]

Strategy: single-segment global paginator over /nl/search. Extract detail
hrefs from SSR HTML. Dutch language preferred for consistency with BE scrapers.
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

# Match detail hrefs: /nl/buy/{brand}/{slug} or /fr/buy/{slug}
_LISTING_RE: re.Pattern[str] = re.compile(
    r'href="(/(?:nl|fr|en)/(?:buy|acheter|kopen)/[a-z0-9][a-z0-9_/-]{5,}[^"]*)"',
    re.IGNORECASE,
)

# Alternative: /nl/auto/{id} or /fr/voiture/{slug}
_LISTING_RE_ALT: re.Pattern[str] = re.compile(
    r'href="(/(?:nl|fr|en)/(?:auto|voiture|vehicle|car)/[a-z0-9][a-z0-9_/-]{5,}[^"]*)"',
    re.IGNORECASE,
)


class YoucarBEScraper(BasePortalScraper):
    """youcar.be Belgian classifieds via SSR HTML (T1)."""

    DOMAIN = "youcar.be"
    COUNTRY = "BE"

    HOST = "www.youcar.be"

    PAGE_SIZE = 24
    MAX_PAGES = 200

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    # ── primitives ────────────────────────────────────────────────────────────

    def partition_params(self) -> list[dict[str, Any]]:
        """Single segment — global paginator."""
        return [{}]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        url = self._build_url(params, page_num)
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

    # ── helpers ───────────────────────────────────────────────────────────────

    def _build_url(self, params: dict[str, Any], page_num: int) -> str:
        base = f"https://{self.HOST}/nl/search"
        if page_num > 1:
            return f"{base}?page={page_num}"
        return base

    def _extract(self, html: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for pattern in (_LISTING_RE, _LISTING_RE_ALT):
            for match in pattern.finditer(html):
                path = match.group(1)
                url = f"https://{self.HOST}{path}"
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
