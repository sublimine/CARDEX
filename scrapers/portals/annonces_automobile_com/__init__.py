"""
annonces-automobile.com — France, portail d'annonces premium (~43k annonces).

SSR HTML classique avec jQuery, pagination par parametre URL ?pg=N.
Aucun WAF detecte. Tier T1. Inclut des annonces de concessionnaires
belges egalement.

Gold nuggets [VERIFIED 2026-06-04]:

  Search URL  GET https://www.annonces-automobile.com/acheter?pg={PAGE}
  Alt search  GET https://www.annonces-automobile.com/l-s/occasion
  Listings    HTML links to /acheter/{slug} pages
  Detail URL  https://www.annonces-automobile.com/acheter/{slug}
  Pagination  ?pg=1, ?pg=2, ... (SSR HTML). ~20 annonces par page.
  WAF         Aucun (T1)
  Tech        SSR HTML + jQuery
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 503})

# Regex pour extraire les liens d'annonces individuelles
_AD_LINK_RE = re.compile(
    r'href="(https://www\.annonces-automobile\.com/acheter/[a-zA-Z0-9][^"]*)"',
    re.IGNORECASE,
)

# Categories/segments pour partitionner les resultats
_SEGMENTS: tuple[str, ...] = (
    "occasion",       # toutes occasions
    "collection",     # voitures de collection
)


class AnnoncesAutomobileFRScraper(BasePortalScraper):
    """annonces-automobile.com via scraping SSR HTML (T1)."""

    DOMAIN = "annonces-automobile.com"
    COUNTRY = "FR"

    HOST = "www.annonces-automobile.com"
    PAGE_SIZE = 20  # ~20 annonces par page SSR
    MAX_PAGES = 100  # 20 * 100 = 2000 per segment; subdivide if capped

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    # -- primitives ----------------------------------------------------------

    def partition_params(self) -> list[dict[str, Any]]:
        """Segment unique — toutes occasions."""
        return [{"segment": "occasion"}]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Pas de subdivision."""
        return []

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch une page HTML et extraire les liens."""
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

        log.warning("les %d tentatives ont echoue: %s", self.RETRY_ATTEMPTS, url[:90])
        return []

    # -- helpers -------------------------------------------------------------

    def _build_url(self, params: dict[str, Any], page: int) -> str:
        segment = params.get("segment", "occasion")
        return f"https://{self.HOST}/l-s/{segment}?pg={page}"

    def _extract(self, body: str) -> list[str]:
        """Extraire les liens de detail depuis le HTML SSR."""
        if not body or not isinstance(body, str):
            return []

        seen: set[str] = set()
        out: list[str] = []
        for m in _AD_LINK_RE.finditer(body):
            url = m.group(1)
            # Filtrer les pages de recherche/navigation vs annonces individuelles
            if "/acheter?" in url or url.endswith("/acheter") or url.endswith("/acheter/"):
                continue
            if url not in seen:
                seen.add(url)
                out.append(url)
        return out

    async def _get(self, session: Any, url: str) -> Any | None:
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:
            log.debug("erreur de transport %s: %s", url[:90], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(
                self.RETRY_BACKOFF_BASE ** attempt * factor + random.uniform(0, 0.25)
            )
