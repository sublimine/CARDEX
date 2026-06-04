"""
flexicar.es — Spain, multi-brand dealer chain (~25,000+ vehicles, 180+ concesionarios).

Pure SSR HTML site with query-param pagination (?pagina=N). URL structure:
  /coches-segunda-mano/                          → all listings
  /coches-{city}/segunda-mano/                   → city-filtered
  /coches-segunda-mano/?pagina=N                 → page N
Brand/city facets are path segments; pagination is a query param.
Detail URLs contain a numeric vehicle ID.

Gold nuggets [research 2026-06-04]:

  Search base   GET https://www.flexicar.es/coches-segunda-mano/
  Pagination    ?pagina=N  (1-indexed)                               [VERIFIED via Google index]
  Brand filter  Path-segment based: /coches-segunda-mano/{brand}/     [ASSUMED]
  Detail URL    /coches-segunda-mano/{brand}-{model}-{slug}-{id}      [ASSUMED]
  Listing re    href="/coches-segunda-mano/[^"]+                      [ASSUMED]
  WAF           Unknown — assumed T1 (dealer chain, not heavy WAF)    [NEEDS live probe]
  Inventory     ~25,000 from 180+ concesionarios                     [VERIFIED via search]
  Tech stack    SSR HTML, likely PHP or Node                          [ASSUMED]

Strategy: single-segment global paginator with ?pagina=N. Extract detail
hrefs from the SSR HTML via regex. 24 items/page assumed.
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

# Match detail hrefs in HTML — /coches-segunda-mano/{slug} or deeper paths
# that represent individual vehicle pages (contain alphanumeric ID segments).
_LISTING_RE: re.Pattern[str] = re.compile(
    r'href="(/coches-segunda-mano/[a-z0-9][a-z0-9_-]+-\d{3,}[^"]*)"',
    re.IGNORECASE,
)

# Alternative pattern: some dealer sites use /vehiculo/ or /ficha/ paths.
_LISTING_RE_ALT: re.Pattern[str] = re.compile(
    r'href="(/(?:vehiculo|ficha|coche)/[^"]{8,})"',
    re.IGNORECASE,
)


class FlexicarESScraper(BasePortalScraper):
    """flexicar.es used cars via SSR HTML pagination (T1)."""

    DOMAIN = "flexicar.es"
    COUNTRY = "ES"

    HOST = "www.flexicar.es"

    PAGE_SIZE = 24
    MAX_PAGES = 1100  # 24 × 1100 = 26,400 — margin for ~25k inventory

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    # ── primitives ────────────────────────────────────────────────────────────

    def partition_params(self) -> list[dict[str, Any]]:
        """Single segment — global paginator covers ~25k listings."""
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
        base = f"https://{self.HOST}/coches-segunda-mano/"
        if page_num == 1:
            return base
        return f"{base}?pagina={page_num}"

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
