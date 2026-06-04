"""
gueudet.fr — Gueudet 1880, major French multi-brand dealer group (~5,257 VO).

SSR HTML marketplace. Extensive network of dealerships across northern France
(Renault, Peugeot, Citroën, Dacia, etc.). Paginated via ?page=N query param.

Gold nuggets [VERIFIED 2026-06-04]:

  Search URL    GET https://www.gueudet.fr/voiture/occasion
  Pagination    ?page=N (1-indexed)
  Detail URL    /voiture/occasion/{brand}-{model}-{trim}-{numeric_id}
  Alt Detail    /voiture/{slug}-{numeric_id}
  WAF           None detected (direct SSR response)
  Inventory     ~5,257 used vehicles (4,737 occasion + stock)
  Tech          SSR HTML (server-rendered, no SPA framework detected)
  Traffic       Major regional dealer group, 140+ years

Strategy: brand-level partitioning via /voiture/occasion?marque={brand}&page=N.
Listing URLs extracted from SSR HTML via regex. Subdivision not needed — no brand
exceeds the page cap at these inventory levels.
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

# Match vehicle detail page links: /voiture/occasion/... or /voiture/...
_LISTING_RE: re.Pattern[str] = re.compile(
    r'href="(/voiture/(?:occasion/)?[a-z0-9][\w-]*-\d{4,}[^"]*)"',
    re.IGNORECASE,
)

_BRANDS: tuple[str, ...] = (
    "abarth", "alfa-romeo", "audi", "bmw", "citroen", "cupra", "dacia",
    "ds", "fiat", "ford", "honda", "hyundai", "jaguar", "jeep", "kia",
    "land-rover", "mazda", "mercedes", "mg", "mini", "mitsubishi",
    "nissan", "opel", "peugeot", "porsche", "renault", "seat", "skoda",
    "smart", "suzuki", "tesla", "toyota", "volkswagen", "volvo",
)


class GueudetFRScraper(BasePortalScraper):
    """gueudet.fr used vehicles via SSR HTML (T1)."""

    DOMAIN = "gueudet.fr"
    COUNTRY = "FR"

    HOST = "www.gueudet.fr"

    PAGE_SIZE = 16  # observed listing count per page
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
        base = f"https://{self.HOST}/voiture/occasion"
        parts = [f"marque={brand}"]
        if page_num > 1:
            parts.append(f"page={page_num}")
        return f"{base}?{'&'.join(parts)}"

    def _extract(self, html: str) -> list[str]:
        """Extract vehicle detail URLs from SSR HTML."""
        seen: set[str] = set()
        out: list[str] = []
        for match in _LISTING_RE.finditer(html):
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
