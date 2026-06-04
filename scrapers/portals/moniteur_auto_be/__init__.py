"""
moniteurautomobile.be — Belgique, reference automobile belge (~120k annonces).

Le plus grand portail d'annonces auto en Belgique (hors AutoScout24/2dehands).
SSR HTML avec pagination par parametre URL. Tier T1.

Gold nuggets [VERIFIED 2026-06-04]:

  Search URL  GET https://www.moniteurautomobile.be/acheter-auto/occasion.html?page={P}
  Alt search  GET https://www.moniteurautomobile.be/marque--{brand}/acheter-auto/occasion.html
  Listings    HTML links vers /voitures-occasion/{slug}.html
  Detail URL  https://www.moniteurautomobile.be/voitures-occasion/{slug}.html
  Pagination  ?page=1, ?page=2, ... SSR HTML.
  WAF         Non detecte (T1)
  Tech        SSR HTML
  Volume      ~114,628 occasions + 4,072 neufs
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

# Liens de detail: /voitures-occasion/{slug}.html ou lien absolu
_AD_LINK_RE = re.compile(
    r'href="(/voitures-occasion/[a-zA-Z0-9][^"?#]*\.html)"',
    re.IGNORECASE,
)

# Marques pour partitionner (top marques belges)
_BRANDS: tuple[str, ...] = (
    "volkswagen", "bmw", "mercedes", "audi", "peugeot",
    "renault", "citroen", "opel", "ford", "toyota",
    "hyundai", "kia", "skoda", "volvo", "nissan",
    "fiat", "dacia", "seat", "mini", "mazda",
    "suzuki", "land-rover", "porsche", "ds", "jeep",
    "alfa-romeo", "mitsubishi", "honda", "lexus", "tesla",
)


class MoniteurAutoBEScraper(BasePortalScraper):
    """moniteurautomobile.be via scraping SSR HTML (T1)."""

    DOMAIN = "moniteurautomobile.be"
    COUNTRY = "BE"

    HOST = "www.moniteurautomobile.be"
    PAGE_SIZE = 20
    MAX_PAGES = 50  # par marque

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    BRANDS: tuple[str, ...] = _BRANDS

    # -- primitives ----------------------------------------------------------

    def partition_params(self) -> list[dict[str, Any]]:
        """Partition par marque pour couvrir le volume ~120k."""
        return [{"brand": b} for b in self.BRANDS]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        return []

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

        log.warning("les %d tentatives ont echoue: %s", self.RETRY_ATTEMPTS, url[:90])
        return []

    # -- helpers -------------------------------------------------------------

    def _build_url(self, params: dict[str, Any], page: int) -> str:
        brand = params.get("brand", "")
        if brand:
            return (
                f"https://{self.HOST}/marque--{brand}/acheter-auto/occasion.html"
                f"?page={page}"
            )
        return f"https://{self.HOST}/acheter-auto/occasion.html?page={page}"

    def _extract(self, body: str) -> list[str]:
        if not body or not isinstance(body, str):
            return []

        seen: set[str] = set()
        out: list[str] = []
        for m in _AD_LINK_RE.finditer(body):
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
