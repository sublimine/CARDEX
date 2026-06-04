"""
2dehands.be — Bélgica, portal de clasificados Adevinta (~102k coches).

Comparte backend LRP con marktplaats.nl (misma infraestructura Adevinta). La API
de búsqueda interna es una ruta JSON abierta detrás de CloudFront SIN Cloudflare,
Akamai, DataDome ni gate de autenticación — responde 200 a un cliente desnudo.
Tier.T0. El coordinador inyecta una sesión curl_cffi por higiene; este scraper
solo emite GETs a través del `session` duck-typed y parsea `response.text` como
JSON, así que importa y testea sin curl_cffi presente.

Gold nuggets [VERIFIED 2026-06-04 — docs/research/2dehands-be.md]:

  Search URL  GET https://www.2dehands.be/lrp/api/search
                  ?l1CategoryId=91&offset={O}&limit=30
                  &attributeRanges[]=constructionYear:{Yf}:{Yt}
                  &attributeRanges[]=PriceCents:{Pf*100}:{Pt*100}
  Category    l1CategoryId=91 = "Auto's" (coches), eco idéntico a marktplaats.
  Listings    JSON `listings[]`; per-ad `vipUrl` (relativo) + `itemId` ("m"+dígitos).
  Year filter attributeRanges[]=constructionYear:from:to (inclusivo).
  Price filter attributeRanges[]=PriceCents:from:to — valor en CÉNTIMOS.
  Pagination  offset/limit. `maxAllowedPageNumber=167`; ~5,010 listings alcanzables
              por query (167×30). offset más allá de la ventana devuelve listings[]
              vacío (sin error) → partición search-grid obligatoria (102k ≫ 5k).

Partición: banda de año × banda de precio sobre todas las marcas — sin dependencia
de tabla de make-id. Una celda capada se subdivide en sub-celdas per-year × precio
más fino. Dedup cross-cell por el set `seen` sobre URLs con itemId.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from itertools import product
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

# ── search grid (verificada, idéntica a marktplaats) ─────────────────────────
_YEAR_BANDS: tuple[tuple[int, int], ...] = (
    (1990, 2000), (2000, 2005), (2005, 2008), (2008, 2011),
    (2011, 2014), (2014, 2016), (2016, 2018), (2018, 2020),
    (2020, 2022), (2022, 2024), (2024, 2026),
)
_PRICE_BANDS: tuple[tuple[int, int | None], ...] = (
    (0, 5_000), (5_000, 10_000), (10_000, 15_000), (15_000, 20_000),
    (20_000, 30_000), (30_000, 50_000), (50_000, 100_000), (100_000, None),
)
_OPEN_PRICE_CEILING: int = 1_000_000
_PRICE_SUBSPLITS: int = 5

_CARS_CATEGORY_ID: int = 91  # "Auto's"

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 503})


class TweedehandsBEScraper(BasePortalScraper):
    """2dehands.be coches via la API LRP JSON abierta (T0)."""

    DOMAIN = "2dehands.be"
    COUNTRY = "BE"

    HOST = "www.2dehands.be"

    # offset/limit paging. limit=30 (default del sitio); ventana tope en página 167.
    PAGE_SIZE = 30
    MAX_PAGES = 167

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    YEAR_BANDS: tuple[tuple[int, int], ...] = _YEAR_BANDS
    PRICE_BANDS: tuple[tuple[int, int | None], ...] = _PRICE_BANDS

    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    @property
    def _search_base(self) -> str:
        return f"https://{self.HOST}/lrp/api/search"

    # ── primitivas ─────────────────────────────────────────────────────────────
    def partition_params(self) -> list[dict[str, Any]]:
        return [
            {"year_from": yf, "year_to": yt, "price_from": pf, "price_to": pt}
            for (yf, yt), (pf, pt) in product(self.YEAR_BANDS, self.PRICE_BANDS)
        ]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Explota una celda capada en sub-celdas per-year × precio más fino."""
        if params.get("_fine"):
            return []
        years = range(params["year_from"], params["year_to"] + 1)
        price_bands = self._split_price(params["price_from"], params["price_to"])
        return [
            {"year_from": y, "year_to": y, "price_from": pf, "price_to": pt, "_fine": True}
            for y, (pf, pt) in product(years, price_bands)
        ]

    @staticmethod
    def _split_price(pf: int, pt: int | None) -> list[tuple[int, int | None]]:
        ceiling = pt if pt is not None else _OPEN_PRICE_CEILING
        step = max((ceiling - pf) // _PRICE_SUBSPLITS, 1)
        bands: list[tuple[int, int | None]] = []
        lo = pf
        while lo < ceiling:
            hi = min(lo + step, ceiling)
            bands.append((lo, hi))
            lo = hi
        if not bands:
            return [(pf, pt)]
        if pt is None:
            last_lo, _ = bands[-1]
            bands[-1] = (last_lo, None)
        return bands

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch una ventana de offset; reintentar bloqueos transitorios; retornar URLs de detalle."""
        offset = (page_num - 1) * self.PAGE_SIZE
        url = self._build_url(params, offset)
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

        log.warning("los %d intentos fallaron: %s", self.RETRY_ATTEMPTS, url[:90])
        return []

    # ── helpers ────────────────────────────────────────────────────────────────
    def _build_url(self, params: dict[str, Any], offset: int) -> str:
        pf_cents = params["price_from"] * 100
        pt = params.get("price_to")
        price_to_cents = "" if pt is None else str(pt * 100)
        ranges = (
            f"&attributeRanges[]=constructionYear:{params['year_from']}:{params['year_to']}"
            f"&attributeRanges[]=PriceCents:{pf_cents}:{price_to_cents}"
        )
        return (
            f"{self._search_base}?l1CategoryId={_CARS_CATEGORY_ID}"
            f"&offset={offset}&limit={self.PAGE_SIZE}"
            f"{ranges}&sortBy=SORT_INDEX&sortOrder=DECREASING"
        )

    def _extract(self, body: str) -> list[str]:
        """Extraer links de detalle `vipUrl` del JSON `listings[]`, deduplicados por página."""
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            log.debug("cuerpo no-JSON desde 2dehands LRP")
            return []
        listings = payload.get("listings") if isinstance(payload, dict) else None
        if not isinstance(listings, list):
            return []
        seen: set[str] = set()
        out: list[str] = []
        for ad in listings:
            vip = ad.get("vipUrl") if isinstance(ad, dict) else None
            if not isinstance(vip, str) or not vip:
                continue
            full = vip if vip.startswith("http") else f"{self._base_url}{vip}"
            if full not in seen:
                seen.add(full)
                out.append(full)
        return out

    async def _get(self, session: Any, url: str) -> Any | None:
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:  # nivel transporte
            log.debug("error de transporte %s: %s", url[:90], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(self.RETRY_BACKOFF_BASE**attempt * factor + random.uniform(0, 0.25))
