"""
viabovag.nl -- red de concesionarios BOVAG, Paises Bajos (~129k coches).

viaBOVAG.nl es una plataforma Next.js SSR respaldada por IIS sin WAF. Los datos de
busqueda se sirven via la ruta de datos Next.js interna en formato JSON. La paginacion
funciona via el parametro `selectedFilters=pagina-N`; los filtros server-side (marca,
anho, precio) NO funcionan — son client-side only. Tier.T1.

Gold nuggets [VERIFIED 2026-06-04 -- docs/research/viabovag-nl.md]:

  Data route  GET https://www.viabovag.nl/_next/data/{buildId}/srp.json
                  ?mobilityType=auto&selectedFilters=pagina-{N}
  buildId     Cambia con cada deploy; se extrae del __NEXT_DATA__ JSON en el HTML.
  Items       JSON `results[]`; per-ad `url` (absoluto), `vehicle.brand/model/year`,
              `price`, `friendlyUriPart`.
  Pagination  selectedFilters=pagina-{1..4167}. Cap en pagina 4167; paginas posteriores
              devuelven datos identicos (stale). 24 items/pagina.
  Coverage    4167 x 24 = ~100,008 URLs (~77% de ~129k). Filtros no disponibles SSR.

Estrategia: single-segment global paginator (como gaspedaal.nl). El buildId se
resuelve en la primera request via HTML SSR y se cachea para el ciclo completo.
Deteccion de cap: cuando fetch_segment devuelve solo URLs ya vistas en el seen set
del paginador base, el scraper no acumula nuevas URLs. Se establece MAX_PAGES=4200
(ligeramente por encima del cap verificado) para permitir crecimiento de inventario.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 500, 502, 503})

# Regex para extraer buildId del __NEXT_DATA__ embebido en HTML
_BUILD_ID_RE: re.Pattern[str] = re.compile(
    r'"buildId"\s*:\s*"([A-Za-z0-9_-]+)"',
)


class ViaBovagNLScraper(BasePortalScraper):
    """viabovag.nl coches via la data route Next.js (T1)."""

    DOMAIN = "viabovag.nl"
    COUNTRY = "NL"

    HOST = "www.viabovag.nl"

    # 24 items por pagina; cap verificado en pagina 4167.
    # MAX_PAGES con margen para crecimiento de inventario.
    PAGE_SIZE = 24
    MAX_PAGES = 4200

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 25

    def __init__(self) -> None:
        super().__init__()
        self._build_id: str | None = None

    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    # -- primitivas ----------------------------------------------------------
    def partition_params(self) -> list[dict[str, Any]]:
        """Segmento unico vacio -- el paginador global cubre el inventario."""
        return [{}]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch una pagina via la data route Next.js; retry transient blocks."""
        # Resolver buildId en la primera llamada
        if self._build_id is None:
            resolved = await self._resolve_build_id(session)
            if resolved is None:
                log.warning("no se pudo resolver buildId para viabovag.nl")
                return []
            self._build_id = resolved

        url = self._build_data_url(page_num)
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
            if status == 404:
                # buildId expirado (nuevo deploy). Intentar re-resolver una vez.
                if attempt == 1:
                    log.info("buildId expirado (404), re-resolviendo...")
                    resolved = await self._resolve_build_id(session)
                    if resolved is not None:
                        self._build_id = resolved
                        url = self._build_data_url(page_num)
                        continue
                return []
            if status != 200:
                log.debug("HTTP %d (no retry) %s", status, url[:90])
                return []

            return self._extract(response.text)

        log.warning("los %d intentos fallaron: %s", self.RETRY_ATTEMPTS, url[:90])
        return []

    # -- helpers --------------------------------------------------------------
    def _build_data_url(self, page_num: int) -> str:
        base = f"{self._base_url}/_next/data/{self._build_id}/srp.json"
        return f"{base}?mobilityType=auto&selectedFilters=pagina-{page_num}"

    def _extract(self, body: str) -> list[str]:
        """Extraer URLs de detalle del JSON de la data route Next.js."""
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            log.debug("cuerpo no-JSON desde viabovag data route")
            return []
        sr = payload.get("pageProps", {}).get("serverSearchResults", {})
        if not isinstance(sr, dict):
            return []
        results = sr.get("results")
        if not isinstance(results, list):
            return []
        seen: set[str] = set()
        out: list[str] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url:
                continue
            # URLs son absolutas en la respuesta
            if url not in seen:
                seen.add(url)
                out.append(url)
        return out

    async def _resolve_build_id(self, session: Any) -> str | None:
        """Fetch HTML de /auto para extraer el buildId de __NEXT_DATA__."""
        html_url = f"{self._base_url}/auto"
        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            response = await self._get(session, html_url)
            if response is None:
                await self._retry_backoff(attempt)
                continue
            if response.status_code != 200:
                await self._retry_backoff(attempt)
                continue
            match = _BUILD_ID_RE.search(response.text)
            if match:
                bid = match.group(1)
                log.info("viabovag buildId resuelto: %s", bid)
                return bid
            log.debug("buildId no encontrado en HTML de /auto")
            return None
        return None

    async def _get(self, session: Any, url: str) -> Any | None:
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:
            log.debug("error de transporte %s: %s", url[:90], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(self.RETRY_BACKOFF_BASE**attempt * factor + random.uniform(0, 0.25))
