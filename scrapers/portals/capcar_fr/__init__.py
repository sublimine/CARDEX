"""
capcar.fr — France, P2P platform with 350+ agents (~200 cars/month turnover).

Secure peer-to-peer car selling platform where each vehicle is inspected
by one of 350+ agents across France. Vehicles come with warranty, secure
payment, financing, and delivery. Relatively small but curated inventory.

Gold nuggets [research 2026-06-04]:

  Search base   GET https://www.capcar.fr/voiture-occasion              [VERIFIED via Google]
  Brand filter  /voiture-occasion/{brand}                               [ASSUMED from SSR path]
                e.g. /voiture-occasion/peugeot
  Detail URL    /voiture-occasion/{brand}-{model}-occasion-{slug}       [VERIFIED via Google index]
                e.g. /voiture-occasion/vinfast-vf8-r0057965
  Pagination    ?page=N  (1-indexed, assumed)                           [ASSUMED]
  WAF           Unknown — assumed T1 (startup, no heavy WAF detected)   [NEEDS live probe]
  Inventory     ~200 cars/month turnover (curated, smaller volume)      [VERIFIED via search]
  Tech stack    SSR HTML, likely Next.js or Ruby on Rails               [ASSUMED]
  Services      Warranty, secure payment, financing, delivery           [VERIFIED]

Strategy: single-segment global paginator. Small inventory (~200/month)
means simple global pager is sufficient. Extract detail hrefs from SSR HTML.
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

# Match detail hrefs: /voiture-occasion/{brand-model-slug}
_LISTING_RE: re.Pattern[str] = re.compile(
    r'href="(/voiture-occasion/[a-z0-9][a-z0-9_-]+-[a-z0-9]{4,}[^"]*)"',
    re.IGNORECASE,
)

# Alternative: /annonce/{slug} or /vehicule/{slug}
_LISTING_RE_ALT: re.Pattern[str] = re.compile(
    r'href="(/(?:annonce|vehicule|fiche)/[a-z0-9][a-z0-9_-]{5,}[^"]*)"',
    re.IGNORECASE,
)


class CapCarFRScraper(BasePortalScraper):
    """capcar.fr P2P used cars via SSR HTML (T1)."""

    DOMAIN = "capcar.fr"
    COUNTRY = "FR"

    HOST = "www.capcar.fr"

    PAGE_SIZE = 24
    MAX_PAGES = 50  # Small inventory; 24 × 50 = 1,200 — generous margin

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    # ── primitives ────────────────────────────────────────────────────────────

    def partition_params(self) -> list[dict[str, Any]]:
        """Single segment — global paginator covers small curated inventory."""
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
        base = f"https://{self.HOST}/voiture-occasion"
        if page_num > 1:
            return f"{base}?page={page_num}"
        return base

    def _extract(self, html: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for pattern in (_LISTING_RE, _LISTING_RE_ALT):
            for match in pattern.finditer(html):
                path = match.group(1)
                # Skip the search page itself
                if path == "/voiture-occasion" or path == "/voiture-occasion/":
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
