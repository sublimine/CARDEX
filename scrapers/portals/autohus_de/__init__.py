"""
autohus.de -- DAT AUTOHUS AG, one of Europe's largest used car dealers (~3000 vehicles).

Large single-dealer operation with multiple locations (Bremen, Bockel, Verden, etc.).
Over 300,000 vehicles sold historically. Search page at /de/fahrzeugsuche/.

Gold nuggets [research 2026-06-04]:

  Search page   GET https://www.autohus.de/de/fahrzeugsuche/              [VERIFIED]
  Detail URL    /de/fahrzeug/{slug}/  or  /de/fahrzeugsuche/{slug}/       [ASSUMED]
  Pagination    ?page=N or AJAX/API call                                  [ASSUMED]
  Brand filter  Query param or path-based brand filtering                 [ASSUMED]
  WAF           Unknown — large commercial site, possibly Cloudflare      [UNVERIFIED]
  Inventory     ~3000 vehicles daily                                      [VERIFIED]
  Locations     Bremen, Bockel, Verden, Achim, Oyten                      [VERIFIED]
  Tech stack    Modern web app (likely React/Next.js)                     [ASSUMED]

Strategy: single-segment paginated sweep of /de/fahrzeugsuche/. With ~3000
vehicles, moderate pagination suffices. Listing URLs regex-extracted from HTML.
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

# Match vehicle detail links: /de/fahrzeug/{slug}/ or /de/fahrzeugsuche/{slug}/
_LISTING_RE: re.Pattern[str] = re.compile(
    r'href="(/de/(?:fahrzeug|fahrzeugsuche)/[a-z0-9][a-z0-9_-]{5,}[^"]*)"',
    re.IGNORECASE,
)

# Alternative: href containing numeric vehicle IDs
_DETAIL_ID_RE: re.Pattern[str] = re.compile(
    r'href="(/de/[a-z]+/[a-z0-9-]+-\d{4,}[^"]*)"',
    re.IGNORECASE,
)

# Price bands for subdivision of ~3000 inventory
_PRICE_BANDS: tuple[tuple[int, int | None], ...] = (
    (0, 5_000), (5_000, 10_000), (10_000, 15_000), (15_000, 20_000),
    (20_000, 30_000), (30_000, 50_000), (50_000, None),
)


class AutohusDEScraper(BasePortalScraper):
    """autohus.de vehicles via SSR HTML (T1)."""

    DOMAIN = "autohus.de"
    COUNTRY = "DE"

    HOST = "www.autohus.de"

    PAGE_SIZE = 20
    MAX_PAGES = 50

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
        step = (pmax - pmin) // 4
        if step < 500:
            return []
        return [
            {"price_min": pmin + i * step, "price_max": pmin + (i + 1) * step}
            for i in range(4)
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
        base = f"https://{self.HOST}/de/fahrzeugsuche/"
        qp: list[str] = []
        if params.get("price_min") is not None:
            qp.append(f"price_from={params['price_min']}")
        if params.get("price_max") is not None:
            qp.append(f"price_to={params['price_max']}")
        if page_num > 1:
            qp.append(f"page={page_num}")
        if qp:
            return f"{base}?{'&'.join(qp)}"
        return base

    def _extract(self, html: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for pattern in (_LISTING_RE, _DETAIL_ID_RE):
            for match in pattern.finditer(html):
                path = match.group(1)
                if "fahrzeugsuche/" == path.rstrip("/").split("/")[-1]:
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
