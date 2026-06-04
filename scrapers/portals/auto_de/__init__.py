"""
auto.de — Germany, dealer portal with Santander Consumer Bank integration.

WordPress-based site with UUID-based vehicle detail URLs. No WAF detected
in earlier probes. Listings from Santander-partnered dealerships.

Gold nuggets [research 2026-06-04]:

  Search base   GET https://www.auto.de/                              [VERIFIED]
  Search page   /gebrauchtwagen/ OR /search/                          [ASSUMED from WordPress pattern]
  Vehicle URL   /search/vehicle/{uuid}                                [VERIFIED from research doc]
  Pagination    ?page=N  (1-indexed, WordPress REST pattern)          [ASSUMED]
  WordPress     /wp-json/ REST API may expose vehicle data            [VERIFIED from research]
  WAF           None detected                                         [VERIFIED from Phase 6 research]
  Tech stack    WordPress + custom frontend, UUID vehicle IDs         [VERIFIED from research]
  Inventory     Unknown (real dealer inventory from multiple brands)   [UNVERIFIED]

Strategy: single-segment global paginator via SSR HTML or WordPress REST API.
Extract vehicle detail URLs from search results page. UUID pattern makes
extraction straightforward.
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

# Match UUID-based vehicle detail URLs: /search/vehicle/{uuid}
_UUID_RE: re.Pattern[str] = re.compile(
    r'href="(/search/vehicle/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}[^"]*)"',
    re.IGNORECASE,
)

# Alternative: some WordPress car sites use /gebrauchtwagen/{slug}/ or /fahrzeug/{id}/
_LISTING_RE_ALT: re.Pattern[str] = re.compile(
    r'href="(/(?:gebrauchtwagen|fahrzeug|auto|angebot)/[a-z0-9][a-z0-9_-]{5,}[^"]*)"',
    re.IGNORECASE,
)

# German car brands for partitioning.
_BRANDS: tuple[str, ...] = (
    "abarth", "alfa-romeo", "audi", "bmw", "citroen", "cupra", "dacia",
    "fiat", "ford", "honda", "hyundai", "jaguar", "jeep", "kia",
    "land-rover", "lexus", "mazda", "mercedes-benz", "mg", "mini",
    "mitsubishi", "nissan", "opel", "peugeot", "porsche", "renault",
    "seat", "skoda", "smart", "subaru", "suzuki", "tesla", "toyota",
    "volkswagen", "volvo",
)


class AutoDEScraper(BasePortalScraper):
    """auto.de vehicles via SSR HTML / WordPress (T1)."""

    DOMAIN = "auto.de"
    COUNTRY = "DE"

    HOST = "www.auto.de"

    PAGE_SIZE = 20
    MAX_PAGES = 100

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
        base = f"https://{self.HOST}/gebrauchtwagen/"
        if brand:
            base = f"{base}{brand}/"
        if page_num > 1:
            return f"{base}?page={page_num}"
        return base

    def _extract(self, html: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for pattern in (_UUID_RE, _LISTING_RE_ALT):
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
