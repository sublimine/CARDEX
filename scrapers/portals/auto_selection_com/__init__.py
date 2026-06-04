"""
auto-selection.com — France, agrégateur pro multi-marques (~113k annonces).

Backend Meilisearch exposé publiquement sans WAF. Le endpoint
meilisearch.auto-selection.com/multi-search accepte des requêtes POST JSON
avec un apiKey public. Le scraper pagine via offset/limit sur l'index
Meilisearch, partitionné par marque pour rester sous le cap de 1000 hits.

Gold nuggets [VERIFIED 2026-06-04]:

  API         POST https://meilisearch.auto-selection.com/multi-search
  Auth        x-meilisearch-api-key: <public search key in page source>
  Request     {"queries":[{"indexUid":"vehicles","q":"","filter":"brand=BMW",
              "sort":["created_at:desc"],"limit":100,"offset":0}]}
  Response    {"results":[{"hits":[{id, slug, brand, model, ...}], "totalHits": N}]}
  Detail URL  https://www.auto-selection.com/acheter/{slug}
  Pagination  offset/limit dans le body. Cap Meilisearch 1000 hits par query.
  WAF         Aucun (T0)
  Tech        Custom frontend + Meilisearch, Sibdata consent
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

# Top brands on auto-selection.com — partitioned to stay under Meilisearch 1000-hit window
_BRANDS: tuple[str, ...] = (
    "Peugeot", "Renault", "Volkswagen", "BMW", "Mercedes-Benz",
    "Citroen", "Audi", "Dacia", "Toyota", "Ford",
    "Opel", "Fiat", "Nissan", "Hyundai", "Kia",
    "Seat", "Skoda", "Volvo", "Mini", "Suzuki",
    "Mazda", "Jeep", "Land Rover", "Porsche", "DS",
    "Alfa Romeo", "Mitsubishi", "Cupra", "Honda", "Lexus",
)

_PRICE_BANDS: tuple[tuple[int | None, int | None], ...] = (
    (None, 10000), (10000, 20000), (20000, 30000),
    (30000, 50000), (50000, None),
)


class AutoSelectionFRScraper(BasePortalScraper):
    """auto-selection.com via API Meilisearch publique (T0)."""

    DOMAIN = "auto-selection.com"
    COUNTRY = "FR"

    HOST = "www.auto-selection.com"
    MEILI_HOST = "meilisearch.auto-selection.com"
    INDEX_UID = "vehicles"
    PAGE_SIZE = 100
    MAX_PAGES = 10  # 100 * 10 = 1000 = Meilisearch window cap

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    BRANDS: tuple[str, ...] = _BRANDS
    PRICE_BANDS: tuple[tuple[int | None, int | None], ...] = _PRICE_BANDS

    # Meilisearch public search API key — extracted from page source (public, read-only)
    _api_key: str = ""

    # -- primitives ----------------------------------------------------------

    def partition_params(self) -> list[dict[str, Any]]:
        """Partition par marque pour rester sous le cap 1000 hits Meilisearch."""
        return [{"brand": b} for b in self.BRANDS]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Subdiviser par bande de prix quand une marque depasse 1000 hits."""
        if params.get("_fine"):
            return []
        return [
            {
                "brand": params["brand"],
                "price_min": pmin,
                "price_max": pmax,
                "_fine": True,
            }
            for pmin, pmax in self.PRICE_BANDS
        ]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch une page via POST Meilisearch multi-search."""
        offset = (page_num - 1) * self.PAGE_SIZE
        url = f"https://{self.MEILI_HOST}/multi-search"
        body = self._build_body(params, offset)

        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            response = await self._post(session, url, body)
            if response is None:
                await self._retry_backoff(attempt)
                continue

            status = response.status_code
            if status in _BLOCK_STATUSES:
                log.debug("HTTP %d (%d/%d) %s", status, attempt, self.RETRY_ATTEMPTS, url)
                await self._retry_backoff(attempt)
                continue

            if status != 200:
                log.debug("HTTP %d (no retry) %s", status, url)
                return []

            return self._extract(response.text)

        log.warning("les %d tentatives ont echoue: %s", self.RETRY_ATTEMPTS, url)
        return []

    # -- helpers -------------------------------------------------------------

    def _build_filter(self, params: dict[str, Any]) -> str:
        """Construire la clause filter Meilisearch."""
        parts: list[str] = []
        brand = params.get("brand")
        if brand:
            parts.append(f'brand = "{brand}"')
        pmin = params.get("price_min")
        pmax = params.get("price_max")
        if pmin is not None:
            parts.append(f"price >= {pmin}")
        if pmax is not None:
            parts.append(f"price < {pmax}")
        return " AND ".join(parts) if parts else ""

    def _build_body(self, params: dict[str, Any], offset: int) -> str:
        query: dict[str, Any] = {
            "indexUid": self.INDEX_UID,
            "q": "",
            "sort": ["created_at:desc"],
            "limit": self.PAGE_SIZE,
            "offset": offset,
        }
        filt = self._build_filter(params)
        if filt:
            query["filter"] = filt
        return json.dumps({"queries": [query]})

    def _extract(self, body: str) -> list[str]:
        """Extraire URLs de detail du JSON Meilisearch multi-search."""
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            log.debug("corps non-JSON depuis Meilisearch")
            return []

        if not isinstance(payload, dict):
            return []

        results = payload.get("results")
        if not isinstance(results, list) or not results:
            return []

        hits = results[0].get("hits") if isinstance(results[0], dict) else None
        if not isinstance(hits, list):
            return []

        seen: set[str] = set()
        out: list[str] = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            slug = hit.get("slug")
            if not slug or not isinstance(slug, str):
                continue
            url = f"https://{self.HOST}/acheter/{slug}"
            if url not in seen:
                seen.add(url)
                out.append(url)
        return out

    async def _post(self, session: Any, url: str, body: str) -> Any | None:
        """POST avec headers Meilisearch."""
        try:
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            return await session.post(url, data=body, headers=headers, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:
            log.debug("erreur de transport %s: %s", url, exc)
            return None

    async def _get(self, session: Any, url: str) -> Any | None:
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:
            log.debug("erreur de transport %s: %s", url, exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(
                self.RETRY_BACKOFF_BASE ** attempt * factor + random.uniform(0, 0.25)
            )
