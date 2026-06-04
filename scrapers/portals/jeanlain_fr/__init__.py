"""
occasions.jeanlain.com -- French regional dealer chain (~1800 vehicles).

Jean Lain Mobilités is a major multi-brand dealer group in the Alpine arc
(Ain, Ardèche, Drôme, Isère, Rhône, Savoie, Haute-Savoie). All used vehicles
are inspected with warranties up to 36 months.

Gold nuggets [research 2026-06-04]:

  Search URL    GET https://occasions.jeanlain.com/voiture                [VERIFIED]
  Alt search    /voiture/occasion                                         [VERIFIED]
  Category      /voiture/faible-km  (low mileage)                         [VERIFIED]
  By city       /voiture/ville-{city}-{code}                              [VERIFIED]
  By type       /voiture/utilitaire  (commercial vehicles)                [VERIFIED]
  Detail URL    /voiture/{brand}/{model}/{slug}-{id}                      [ASSUMED]
  Pagination    ?page=N                                                   [ASSUMED]
  WAF           Unknown                                                   [UNVERIFIED]
  Inventory     ~1,800+ used vehicles of all brands                       [VERIFIED]
  Online sale   96h delivery nationwide, 100% online purchase              [VERIFIED]
  Locations     ~30 dealerships across Alpine arc regions                  [VERIFIED]

Strategy: single-segment paginated sweep. With ~1800 vehicles, moderate
pagination suffices. Listing URLs regex-extracted from SSR HTML.
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

# Match vehicle detail URLs
_LISTING_RE: re.Pattern[str] = re.compile(
    r'href="(/voiture/[a-z0-9-]+/[a-z0-9-]+/[a-z0-9][a-z0-9_-]{5,}[^"]*)"',
    re.IGNORECASE,
)

# Alternative: direct detail link with numeric ID
_DETAIL_RE: re.Pattern[str] = re.compile(
    r'href="(/voiture/[a-z0-9-]+-\d{4,}[^"]*)"',
    re.IGNORECASE,
)

# Price bands for subdivision
_PRICE_BANDS: tuple[tuple[int, int | None], ...] = (
    (0, 10_000), (10_000, 15_000), (15_000, 20_000), (20_000, 25_000),
    (25_000, 30_000), (30_000, 40_000), (40_000, 60_000), (60_000, None),
)


class JeanLainFRScraper(BasePortalScraper):
    """occasions.jeanlain.com vehicles via SSR HTML (T1)."""

    DOMAIN = "occasions.jeanlain.com"
    COUNTRY = "FR"

    HOST = "occasions.jeanlain.com"

    PAGE_SIZE = 20
    MAX_PAGES = 30

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    PRICE_BANDS: tuple[tuple[int, int | None], ...] = _PRICE_BANDS

    def partition_params(self) -> list[dict[str, Any]]:
        return [{"price_min": pmin, "price_max": pmax} for pmin, pmax in self.PRICE_BANDS]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        pmin = params.get("price_min", 0) or 0
        pmax = params.get("price_max")
        if pmax is None:
            return []
        step = (pmax - pmin) // 3
        if step < 1_000:
            return []
        return [
            {"price_min": pmin + i * step, "price_max": pmin + (i + 1) * step}
            for i in range(3)
        ]

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
        base = f"https://{self.HOST}/voiture/occasion"
        qp: list[str] = []
        if params.get("price_min") is not None:
            qp.append(f"budgetLower={params['price_min']}")
        if params.get("price_max") is not None:
            qp.append(f"budgetUpper={params['price_max']}")
        if page_num > 1:
            qp.append(f"page={page_num}")
        if qp:
            return f"{base}?{'&'.join(qp)}"
        return base

    def _extract(self, html: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for pattern in (_LISTING_RE, _DETAIL_RE):
            for match in pattern.finditer(html):
                path = match.group(1)
                # Skip category/filter pages
                if path in ("/voiture/occasion", "/voiture/faible-km", "/voiture/utilitaire"):
                    continue
                if "/ville-" in path:
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
