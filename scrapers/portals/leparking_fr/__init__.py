"""
leparking.fr — France, méta-agrégateur européen (~14.8M annonces, 926 sites).

SSR HTML classique avec jQuery, pagination par paramètre URL ?p=N.
Aucun WAF détecté (ni Cloudflare, Akamai, DataDome, PerimeterX).
Tier T1 — curl_cffi suffit. Le scraper parse le HTML SSR pour extraire
les liens de détail vers les annonces individuelles.

Gold nuggets [VERIFIED 2026-06-04]:

  Search URL  GET https://www.leparking.fr/voiture-occasion/{marque}.html?p={PAGE}
  Alt search  GET https://www.leparking.fr/voiture-occasion.html?p={PAGE}
  Listings    HTML <a class="linkAd" href="/voiture-occasion/{slug}.html">
  Detail URL  https://www.leparking.fr/voiture-occasion/{slug}.html
  Pagination  ?p=1, ?p=2, ... (SSR HTML). Pages vides quand plus de résultats.
  WAF         Aucun (T1)
  Tech        SSR HTML + jQuery, Sibdata consent, Google AdSense
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

# Regex pour extraire les liens de detail des annonces
_AD_LINK_RE = re.compile(
    r'href="(/voiture-occasion/[^"]+\.html)"[^>]*class="[^"]*linkAd[^"]*"'
    r'|class="[^"]*linkAd[^"]*"[^>]*href="(/voiture-occasion/[^"]+\.html)"',
    re.IGNORECASE,
)

# Fallback: tout lien vers une page de detail individuelle
_DETAIL_LINK_RE = re.compile(
    r'href="(/voiture-occasion/[a-z0-9]+-[a-z0-9]+-[^"]+\.html)"',
    re.IGNORECASE,
)

# Brands partitioned pour rester sous le cap de pagination
_BRANDS: tuple[str, ...] = (
    "peugeot", "renault", "volkswagen", "bmw", "mercedes",
    "citroen", "audi", "dacia", "toyota", "ford",
    "opel", "fiat", "nissan", "hyundai", "kia",
    "seat", "skoda", "volvo", "mini", "suzuki",
    "mazda", "jeep", "land-rover", "porsche", "ds",
    "alfa-romeo", "mitsubishi", "honda", "lexus", "tesla",
)


class LeParkingFRScraper(BasePortalScraper):
    """leparking.fr via scraping SSR HTML (T1)."""

    DOMAIN = "leparking.fr"
    COUNTRY = "FR"

    HOST = "www.leparking.fr"
    PAGE_SIZE = 20  # ~20 annonces par page SSR
    MAX_PAGES = 50  # 50 pages par marque

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    BRANDS: tuple[str, ...] = _BRANDS

    # -- primitives ----------------------------------------------------------

    def partition_params(self) -> list[dict[str, Any]]:
        """Partition par marque pour couvrir l'inventaire."""
        return [{"brand": b} for b in self.BRANDS]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Pas de subdivision supplementaire."""
        return []

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch une page HTML et extraire les liens de detail."""
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
        brand = params.get("brand", "")
        if brand:
            path = f"/voiture-occasion/{brand}.html"
        else:
            path = "/voiture-occasion.html"
        return f"https://{self.HOST}{path}?p={page}"

    def _extract(self, body: str) -> list[str]:
        """Extraire les liens de detail depuis le HTML SSR."""
        if not body or not isinstance(body, str):
            return []

        seen: set[str] = set()
        out: list[str] = []

        # Essayer d'abord les liens avec classe linkAd
        for m in _AD_LINK_RE.finditer(body):
            path = m.group(1) or m.group(2)
            if path:
                url = f"https://{self.HOST}{path}"
                if url not in seen:
                    seen.add(url)
                    out.append(url)

        # Fallback sur les liens de detail generiques si aucun linkAd
        if not out:
            for m in _DETAIL_LINK_RE.finditer(body):
                path = m.group(1)
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
