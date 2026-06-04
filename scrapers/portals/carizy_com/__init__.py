"""
carizy.com — France, plateforme P2P de vente auto (~1.2k annonces).

Nuxt.js (Vue SSR) avec __NUXT__ global. Aucun WAF detecte.
Tier T1. Petit inventaire mais donnees P2P interessantes (ventes entre
particuliers securisees).

Gold nuggets [VERIFIED 2026-06-04]:

  Search URL  GET https://www.carizy.com/voiture-occasion?page={PAGE}
  Listings    HTML links to /voiture-occasion/{slug}
  Detail URL  https://www.carizy.com/voiture-occasion/{slug}
  Pagination  ?page=1, ?page=2, ... Nuxt SSR HTML.
  WAF         Aucun (T1)
  Tech        Nuxt.js (Vue SSR), __NUXT__ hydration
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

_AD_LINK_RE = re.compile(
    r'href="(/voiture-occasion/[a-zA-Z0-9][^"?#]*-[a-zA-Z0-9][^"?#]*)"',
    re.IGNORECASE,
)


class CarizyFRScraper(BasePortalScraper):
    """carizy.com via scraping Nuxt SSR HTML (T1)."""

    DOMAIN = "carizy.com"
    COUNTRY = "FR"

    HOST = "www.carizy.com"
    PAGE_SIZE = 20
    MAX_PAGES = 60  # 20 * 60 = 1200 ~ inventaire actuel

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    # -- primitives ----------------------------------------------------------

    def partition_params(self) -> list[dict[str, Any]]:
        return [{}]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        url = self._build_url(page_num)

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

    def _build_url(self, page: int) -> str:
        return f"https://{self.HOST}/voiture-occasion?page={page}"

    def _extract(self, body: str) -> list[str]:
        if not body or not isinstance(body, str):
            return []

        seen: set[str] = set()
        out: list[str] = []
        for m in _AD_LINK_RE.finditer(body):
            path = m.group(1)
            # Filtrer les chemins trop courts (categorie, pas annonce)
            parts = path.strip("/").split("/")
            if len(parts) < 2:
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
            log.debug("erreur de transport %s: %s", url[:90], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(
                self.RETRY_BACKOFF_BASE ** attempt * factor + random.uniform(0, 0.25)
            )
