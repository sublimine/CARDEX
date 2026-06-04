"""
autolina.ch — Suiza, portal de coches de ocasión (~94k coches).

API REST abierta en m.autolina.ch sin WAF. Paginación offset/limit sin tope
server-side ni filtrado por marca — el scraper pagina linealmente sobre todo
el inventario.

Gold nuggets [VERIFIED 2026-06-04 — docs/research/autolina-ch.md]:

  API         GET https://m.autolina.ch/api/v2/searchcars?limit={L}&offset={O}
  Response    {status: 1, data: {count: "N", cars: [{carId, slug, ...}]}}
  Detail URL  https://www.autolina.ch/auto/{slug}/{carId}
  Pagination  offset/limit, sin cap; offset > count → cars: []
  WAF         m.autolina.ch: ninguno (T0); www: Cloudflare managed
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


class AutolinaCHScraper(BasePortalScraper):
    """autolina.ch coches via API REST abierta (T0)."""

    DOMAIN = "autolina.ch"
    COUNTRY = "CH"

    API_HOST = "m.autolina.ch"
    DETAIL_HOST = "www.autolina.ch"
    PAGE_SIZE = 100
    MAX_PAGES = 1000  # 100 × 1000 = 100,000 > inventario actual

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    # ── primitivas ─────────────────────────────────────────────────────────

    def partition_params(self) -> list[dict[str, Any]]:
        """Segmento único — API sin filtrado server-side."""
        return [{}]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Sin subdivisión — paginación lineal cubre todo el inventario."""
        return []

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch una página de resultados via offset/limit."""
        offset = (page_num - 1) * self.PAGE_SIZE
        url = self._build_url(offset)

        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            response = await self._get(session, url)
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

        log.warning("los %d intentos fallaron: %s", self.RETRY_ATTEMPTS, url)
        return []

    # ── helpers ────────────────────────────────────────────────────────────

    def _build_url(self, offset: int) -> str:
        return (
            f"https://{self.API_HOST}/api/v2/searchcars"
            f"?limit={self.PAGE_SIZE}&offset={offset}"
        )

    def _extract(self, body: str) -> list[str]:
        """Extrae URLs de detalle del JSON de la API."""
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            log.debug("cuerpo no-JSON desde autolina.ch API")
            return []

        data = payload.get("data")
        if not isinstance(data, dict):
            return []

        cars = data.get("cars")
        if not isinstance(cars, list):
            return []

        seen: set[str] = set()
        out: list[str] = []
        for car in cars:
            if not isinstance(car, dict):
                continue
            car_id = car.get("carId")
            slug = car.get("slug")
            if not car_id:
                continue
            if slug:
                url = f"https://{self.DETAIL_HOST}/auto/{slug}/{car_id}"
            else:
                url = f"https://{self.DETAIL_HOST}/auto/{car_id}"
            if url not in seen:
                seen.add(url)
                out.append(url)
        return out

    async def _get(self, session: Any, url: str) -> Any | None:
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:
            log.debug("error de transporte %s: %s", url, exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(
                self.RETRY_BACKOFF_BASE ** attempt * factor + random.uniform(0, 0.25)
            )
