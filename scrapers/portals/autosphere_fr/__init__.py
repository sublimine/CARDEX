"""
autosphere.fr — France, concessionnaire multi-marques Emil Frey (~15.6k VO).

API REST interne Next.js exposée sans WAF. Le endpoint /api/stock/vehicles
retourne du JSON paginé (offset/size). Aucun Cloudflare, DataDome ni Akamai
détecté — T0 pur. Le scraper pagine linéairement avec le paramètre size=100
et offset croissant.

Gold nuggets [VERIFIED 2026-06-04]:

  API         GET https://www.autosphere.fr/api/stock/vehicles
                  ?voiture=occasion&sortField=popularity&sortDirection=asc
                  &internal_type=vo,vd&size={S}&from={FROM}
  Response    JSON {results: [{slug, id, brand, model, ...}], total: N}
  Detail URL  https://www.autosphere.fr/recherche/{slug}
  Pagination  from/size (0-indexed). No server cap detected.
  WAF         Aucun (T0)
  Tech        Next.js App Router, AWS S3 pour images
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 503})


class AutosphereFRScraper(BasePortalScraper):
    """autosphere.fr VO via API REST interne Next.js (T0)."""

    DOMAIN = "autosphere.fr"
    COUNTRY = "FR"

    HOST = "www.autosphere.fr"
    PAGE_SIZE = 100
    MAX_PAGES = 200  # 100 * 200 = 20,000 > inventaire actuel (~15.6k)

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    # -- primitives ----------------------------------------------------------

    def partition_params(self) -> list[dict[str, Any]]:
        """Segment unique — API sans filtrage obligatoire."""
        return [{}]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Pas de subdivision — pagination lineaire couvre tout l'inventaire."""
        return []

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch une page de resultats via from/size."""
        offset = (page_num - 1) * self.PAGE_SIZE
        url = self._build_url(offset)

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

    def _build_url(self, offset: int) -> str:
        return (
            f"https://{self.HOST}/api/stock/vehicles"
            f"?voiture=occasion&sortField=popularity&sortDirection=asc"
            f"&internal_type=vo,vd&size={self.PAGE_SIZE}&from={offset}"
        )

    def _extract(self, body: str) -> list[str]:
        """Extraire URLs de detail du JSON API."""
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            log.debug("corps non-JSON depuis autosphere.fr API")
            return []

        if not isinstance(payload, dict):
            return []

        results = payload.get("results")
        if not isinstance(results, list):
            return []

        seen: set[str] = set()
        out: list[str] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            slug = item.get("slug")
            if not slug or not isinstance(slug, str):
                continue
            url = f"https://{self.HOST}/recherche/{slug}"
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
