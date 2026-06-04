"""
clicars.com — Spain, online dealer platform (~2,000+ vehicles in stock).

SSR HTML site with path-based filtering (brand, location, fuel type) and
query-param pagination. Europe's leading digital dealership (Spain-focused).

Gold nuggets [research 2026-06-04]:

  Search base   GET https://www.clicars.com/coches-segunda-mano-ocasion
  Brand filter  /coches-segunda-mano-ocasion/{brand}                  [VERIFIED via Google index]
                e.g. /coches-segunda-mano-ocasion/ds
  Location      /coches-segunda-mano-ocasion/{city}                   [VERIFIED]
                e.g. /coches-segunda-mano-ocasion/madrid
  Fuel type     /coches-segunda-mano-ocasion/{fuel}                   [VERIFIED]
                e.g. /coches-segunda-mano-ocasion/gasolina, /electrico
  Pagination    ?page=N  (assumed 1-indexed)                          [ASSUMED]
  Detail URL    /coches-segunda-mano-ocasion/{brand}/{model}-{id}     [ASSUMED]
  WAF           Unknown — assumed T1 (funded startup, no heavy WAF)   [NEEDS live probe]
  Inventory     ~2,000+ vehicles in stock at any time                 [VERIFIED via search]
  Tech stack    SSR HTML, likely Next.js or Nuxt.js                   [ASSUMED]

Strategy: partition by brand slug. Small enough inventory that a single
global paginator also works, but brand partitioning is more robust for
future growth. Extract vehicle detail hrefs from SSR HTML.
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

# Match detail hrefs: /coches-segunda-mano-ocasion/{brand}/{model-slug...}
_LISTING_RE: re.Pattern[str] = re.compile(
    r'href="(/coches-segunda-mano-ocasion/[a-z0-9-]+/[a-z0-9][a-z0-9_-]{5,}[^"]*)"',
    re.IGNORECASE,
)

# Common Spanish brands for partitioning.
_BRANDS: tuple[str, ...] = (
    "abarth", "alfa-romeo", "audi", "bmw", "citroen", "cupra", "dacia",
    "ds", "fiat", "ford", "honda", "hyundai", "jaguar", "jeep", "kia",
    "land-rover", "lexus", "mazda", "mercedes-benz", "mg", "mini",
    "mitsubishi", "nissan", "opel", "peugeot", "porsche", "renault",
    "seat", "skoda", "smart", "subaru", "suzuki", "tesla", "toyota",
    "volkswagen", "volvo",
)


class ClicarsESScraper(BasePortalScraper):
    """clicars.com used cars via SSR HTML with brand partitioning (T1)."""

    DOMAIN = "clicars.com"
    COUNTRY = "ES"

    HOST = "www.clicars.com"

    PAGE_SIZE = 24
    MAX_PAGES = 100  # 24 × 100 = 2,400 per brand — enough for any single brand

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    BRANDS: tuple[str, ...] = _BRANDS

    # ── primitives ────────────────────────────────────────────────────────────

    def partition_params(self) -> list[dict[str, Any]]:
        """One segment per brand — covers the full inventory."""
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

    # ── helpers ───────────────────────────────────────────────────────────────

    def _build_url(self, params: dict[str, Any], page_num: int) -> str:
        brand = params.get("brand", "")
        base = f"https://{self.HOST}/coches-segunda-mano-ocasion"
        if brand:
            base = f"{base}/{brand}"
        if page_num > 1:
            return f"{base}?page={page_num}"
        return base

    def _extract(self, html: str) -> list[str]:
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
