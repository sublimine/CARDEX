"""
autohaus24.de -- German dealer platform (~1000+ vehicles, all brands).

Owned by Allane SE (formerly Sixt Neuwagen). Offers both new cars (configurator)
and used cars with guarantee. Used car search at /gebrauchtwagen path.

Gold nuggets [research 2026-06-04]:

  Search base   GET https://www.autohaus24.de/gebrauchtwagen              [VERIFIED]
  Brand page    /gebrauchtwagen?brand={brand-slug}                        [ASSUMED]
  Alt brand     /{brand-slug}  (e.g. /audi, /skoda)                       [VERIFIED from site:search]
  Detail URL    /gebrauchtwagen/{slug}  or  /gebrauchtwagen/{id}          [ASSUMED]
  Pagination    ?page=N (1-indexed)                                       [ASSUMED]
  WAF           Unknown — research suggests none for SSR pages            [UNVERIFIED]
  Inventory     ~1000+ across 30+ brands                                  [VERIFIED]
  Locations     Munich, Frankfurt, Berlin, Wuppertal                      [VERIFIED]

Strategy: single-segment global search with pagination. Small inventory (~1000)
means a single paginated sweep suffices. Listing URLs are regex-extracted from
SSR HTML.
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

# Match used car detail links
_LISTING_RE: re.Pattern[str] = re.compile(
    r'href="(/gebrauchtwagen/[a-z0-9][a-z0-9_-]{5,}[^"]*)"',
    re.IGNORECASE,
)

# Alternative: brand-model-city slug pattern
_DETAIL_RE: re.Pattern[str] = re.compile(
    r'href="(/gebrauchtwagen/[a-z]+-[a-z]+-[a-z0-9-]+-\d+[^"]*)"',
    re.IGNORECASE,
)

_BRANDS: tuple[str, ...] = (
    "audi", "bmw", "citroen", "cupra", "dacia", "fiat", "ford",
    "hyundai", "kia", "mazda", "mercedes-benz", "mini", "nissan",
    "opel", "peugeot", "renault", "seat", "skoda", "toyota",
    "volkswagen", "volvo",
)


class Autohaus24DEScraper(BasePortalScraper):
    """autohaus24.de vehicles via SSR HTML (T1)."""

    DOMAIN = "autohaus24.de"
    COUNTRY = "DE"

    HOST = "www.autohaus24.de"

    PAGE_SIZE = 20
    MAX_PAGES = 20

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    BRANDS: tuple[str, ...] = _BRANDS

    def partition_params(self) -> list[dict[str, Any]]:
        return [{"brand": b} for b in self.BRANDS]

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

    def _build_url(self, params: dict[str, Any], page_num: int) -> str:
        brand = params.get("brand", "")
        base = f"https://{self.HOST}/gebrauchtwagen"
        qs = f"?brand={brand}"
        if page_num > 1:
            qs += f"&page={page_num}"
        return f"{base}{qs}"

    def _extract(self, html: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for pattern in (_LISTING_RE, _DETAIL_RE):
            for match in pattern.finditer(html):
                path = match.group(1)
                # Skip pagination / filter links
                if "?" in path or path.endswith("/gebrauchtwagen/"):
                    continue
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
