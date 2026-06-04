"""
buscocoches.com -- Spanish national used car classifieds portal.

PHP/SSR site with .html extension URL pattern. Listings organized by region,
brand, and price. Real, non-duplicated ads from professional dealers across Spain.

Gold nuggets [research 2026-06-04]:

  Search base   GET https://www.buscocoches.com/                         [VERIFIED]
  Brand page    /{brand-slug}-de-segunda-mano.html                       [VERIFIED]
  Region page   /coches-de-segunda-mano-en-{region}.html                 [VERIFIED]
  Detail URL    /coche-segunda-mano/{slug}-{id}.html                     [ASSUMED]
  Alt detail    /ficha/{brand}/{model}/{id}.html                         [ASSUMED]
  Pagination    ?pagina=N or /pagina-N/                                  [ASSUMED]
  WAF           None detected                                            [ASSUMED]
  Inventory     Unknown exact, national coverage from dealers            [UNVERIFIED]
  Prof tools    Dashboard for dealer metrics, financing checks           [VERIFIED]

Strategy: brand-level partitioning. Listing URLs are regex-extracted from
server-rendered HTML. The .html extension pattern makes extraction clean.
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

# Match vehicle detail URLs with .html extension
_LISTING_RE: re.Pattern[str] = re.compile(
    r'href="(/(?:coche-segunda-mano|ficha|vehiculo|anuncio)/[a-z0-9][a-z0-9_-]{5,}\.html[^"]*)"',
    re.IGNORECASE,
)

# Alternative: direct detail links with numeric ID
_DETAIL_RE: re.Pattern[str] = re.compile(
    r'href="(/[a-z0-9-]+-\d{4,}\.html)"',
    re.IGNORECASE,
)

_BRANDS: tuple[str, ...] = (
    "abarth", "alfa-romeo", "audi", "bmw", "citroen", "cupra", "dacia",
    "fiat", "ford", "honda", "hyundai", "jaguar", "jeep", "kia",
    "land-rover", "lexus", "mazda", "mercedes-benz", "mg", "mini",
    "mitsubishi", "nissan", "opel", "peugeot", "porsche", "renault",
    "seat", "skoda", "smart", "suzuki", "tesla", "toyota",
    "volkswagen", "volvo",
)


class BuscocochesESScraper(BasePortalScraper):
    """buscocoches.com vehicles via SSR HTML (T1)."""

    DOMAIN = "buscocoches.com"
    COUNTRY = "ES"

    HOST = "www.buscocoches.com"

    PAGE_SIZE = 20
    MAX_PAGES = 50

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
        base = f"https://{self.HOST}/{brand}-de-segunda-mano.html"
        if page_num > 1:
            return f"{base}?pagina={page_num}"
        return base

    def _extract(self, html: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for pattern in (_LISTING_RE, _DETAIL_RE):
            for match in pattern.finditer(html):
                path = match.group(1)
                # Skip navigation/category pages
                if "segunda-mano-en-" in path or "segunda-mano.html" == path.split("/")[-1]:
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
