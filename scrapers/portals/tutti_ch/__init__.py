"""
tutti.ch — Suiza, portal de clasificados (~83k coches).

Frontend Next.js con SSR. Cloudflare Free tier. Los resultados de búsqueda se
sirven via una data route Next.js que acepta un token de búsqueda codificado en
MessagePack. El token encapsula categoría + filtros aplicados. El scraper
construye tokens por marca para particionar el inventario y superar el cap de
101 páginas (3,030 items) por consulta.

Gold nuggets [VERIFIED 2026-06-04 — docs/research/tutti-ch.md]:

  Data route  GET /_next/data/{buildId}/de/q/autos/{token}.json?page={N}
  Token       'A' + base64url(msgpack([None, 'cars', [brand_filters, None, range_filters, None]]))
  Brand       [['carsAutoScoutBrand', slug]]  — slot 0 del array de filtros
  Price       ['price', False, min_or_None, max_or_None]  — slot 2
  Listings    .pageProps.dehydratedState.queries[0].state.data.listings.edges[].node
  Detail URL  https://www.tutti.ch/de/vi/{listingID}/{deSlug}
  Pagination  ?page=N; cap en 101 (30 items/pag = 3,030 max por token)
  Slug URL    cosmético — el token determina los filtros, no el path
  buildId     cambia con deploys; extraer de __NEXT_DATA__ en HTML SSR
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
import re
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

# ── msgpack inline — solo empaquetado, sin dependencia externa ──────────────
# El scraper solo PRODUCE tokens (packb), nunca los desempaqueta. Implementar
# el subset mínimo de msgpack evita la dependencia de pip en el runtime del
# engine (el msgpack de PyPI no es estándar en todos los entornos Docker).

def _mp_pack(obj: Any) -> bytes:
    """Empaqueta un subconjunto de tipos Python a MessagePack binario."""
    if obj is None:
        return b"\xc0"
    if obj is True:
        return b"\xc3"
    if obj is False:
        return b"\xc2"
    if isinstance(obj, int):
        if 0 <= obj <= 0x7F:
            return bytes([obj])
        if 0 <= obj <= 0xFF:
            return b"\xcc" + obj.to_bytes(1, "big")
        if 0 <= obj <= 0xFFFF:
            return b"\xcd" + obj.to_bytes(2, "big")
        if 0 <= obj <= 0xFFFFFFFF:
            return b"\xce" + obj.to_bytes(4, "big")
        if -32 <= obj < 0:
            return (obj & 0xFF).to_bytes(1, "big")
        if -128 <= obj < 0:
            return b"\xd0" + obj.to_bytes(1, "big", signed=True)
        if -32768 <= obj < 0:
            return b"\xd1" + obj.to_bytes(2, "big", signed=True)
        raise ValueError(f"entero fuera de rango: {obj}")
    if isinstance(obj, str):
        raw = obj.encode()
        n = len(raw)
        if n <= 31:
            return bytes([0xA0 | n]) + raw
        if n <= 0xFF:
            return b"\xd9" + bytes([n]) + raw
        if n <= 0xFFFF:
            return b"\xda" + n.to_bytes(2, "big") + raw
        raise ValueError(f"cadena demasiado larga: {n}")
    if isinstance(obj, (list, tuple)):
        n = len(obj)
        if n <= 15:
            header = bytes([0x90 | n])
        elif n <= 0xFFFF:
            header = b"\xdc" + n.to_bytes(2, "big")
        else:
            raise ValueError(f"array demasiado largo: {n}")
        return header + b"".join(_mp_pack(item) for item in obj)
    raise TypeError(f"tipo no soportado: {type(obj)}")


def _encode_token(category: str, brand: str | None = None,
                  price_min: int | None = None,
                  price_max: int | None = None) -> str:
    """Construye un search token tutti.ch a partir de filtros."""
    brand_slot: list | None = None
    if brand is not None:
        brand_slot = [["carsAutoScoutBrand", brand]]

    range_slot: list | None = None
    if price_min is not None or price_max is not None:
        range_slot = [["price", False, price_min, price_max]]

    payload = [None, category, [brand_slot, None, range_slot, None]]
    raw = _mp_pack(payload)
    b64 = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return "A" + b64


# ── constantes ──────────────────────────────────────────────────────────────

_BUILD_ID_RE = re.compile(r'"buildId"\s*:\s*"([^"]+)"')

# Top marcas en Suiza — cubren >95% del inventario. Cada marca se convierte
# en un segmento independiente en partition_params(). El valor es el slug
# exacto del filtro carsAutoScoutBrand tal como lo espera el backend.
_BRANDS: tuple[str, ...] = (
    "alfa-romeo", "audi", "bmw", "chevrolet", "chrysler", "citroen", "cupra",
    "dacia", "dodge", "ds", "fiat", "ford", "honda", "hyundai", "jaguar",
    "jeep", "kia", "land-rover", "lexus", "mazda", "mercedes-benz", "mini",
    "mitsubishi", "nissan", "opel", "peugeot", "porsche", "renault", "seat",
    "skoda", "smart", "subaru", "suzuki", "tesla", "toyota", "volvo", "vw",
)

# Bandas de precio para sub-particion de marcas que superan el cap de 3,030.
_PRICE_BANDS: tuple[tuple[int | None, int | None], ...] = (
    (None, 5_000), (5_000, 10_000), (10_000, 20_000), (20_000, 30_000),
    (30_000, 50_000), (50_000, 100_000), (100_000, None),
)

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 503})


class TuttiCHScraper(BasePortalScraper):
    """tutti.ch coches via Next.js data route + tokens msgpack (T1)."""

    DOMAIN = "tutti.ch"
    COUNTRY = "CH"

    HOST = "www.tutti.ch"
    PAGE_SIZE = 30
    MAX_PAGES = 101

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    BRANDS: tuple[str, ...] = _BRANDS
    PRICE_BANDS: tuple[tuple[int | None, int | None], ...] = _PRICE_BANDS

    def __init__(self) -> None:
        super().__init__()
        self._build_id: str | None = None

    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    # ── primitivas ─────────────────────────────────────────────────────────

    def partition_params(self) -> list[dict[str, Any]]:
        return [{"brand": b} for b in self.BRANDS]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Explota una marca capada en sub-segmentos por banda de precio."""
        if params.get("_fine"):
            return []
        brand = params["brand"]
        return [
            {"brand": brand, "price_min": pmin, "price_max": pmax, "_fine": True}
            for pmin, pmax in self.PRICE_BANDS
        ]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch una pagina de resultados filtrados por marca (y precio)."""
        if self._build_id is None:
            self._build_id = await self._resolve_build_id(session)
            if self._build_id is None:
                return []

        token = _encode_token(
            category="cars",
            brand=params.get("brand"),
            price_min=params.get("price_min"),
            price_max=params.get("price_max"),
        )
        url = self._build_data_url(token, page_num)

        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            response = await self._get(session, url)
            if response is None:
                await self._retry_backoff(attempt)
                continue

            status = response.status_code
            if status == 404:
                # buildId cambio (deploy mid-scrape) — reintentar
                log.info("404 en data route, re-resolviendo buildId")
                self._build_id = await self._resolve_build_id(session)
                if self._build_id is None:
                    return []
                url = self._build_data_url(token, page_num)
                continue

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

    # ── helpers ────────────────────────────────────────────────────────────

    def _build_data_url(self, token: str, page_num: int) -> str:
        base = f"{self._base_url}/_next/data/{self._build_id}/de/q/autos/{token}.json"
        if page_num > 1:
            return f"{base}?page={page_num}"
        return base

    def _extract(self, body: str) -> list[str]:
        """Extrae URLs de detalle del JSON de la data route."""
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            log.debug("cuerpo no-JSON desde tutti.ch data route")
            return []
        try:
            edges = (
                payload["pageProps"]["dehydratedState"]["queries"][0]
                ["state"]["data"]["listings"]["edges"]
            )
        except (KeyError, IndexError, TypeError):
            # Respuesta sin listings — podria ser redirect o error
            return []
        if not isinstance(edges, list):
            return []

        seen: set[str] = set()
        out: list[str] = []
        for edge in edges:
            node = edge.get("node") if isinstance(edge, dict) else None
            if not isinstance(node, dict):
                continue
            listing_id = node.get("listingID")
            seo = node.get("seoInformation")
            slug = seo.get("deSlug") if isinstance(seo, dict) else None
            if not listing_id:
                continue
            if slug:
                url = f"{self._base_url}/de/vi/{listing_id}/{slug}"
            else:
                url = f"{self._base_url}/de/vi/{listing_id}"
            if url not in seen:
                seen.add(url)
                out.append(url)
        return out

    async def _resolve_build_id(self, session: Any) -> str | None:
        """Extrae el buildId de Next.js desde el HTML de la pagina principal."""
        response = await self._get(session, f"{self._base_url}/de")
        if response is None or response.status_code != 200:
            log.error("no se pudo resolver buildId de tutti.ch")
            return None
        match = _BUILD_ID_RE.search(response.text)
        if not match:
            log.error("buildId no encontrado en HTML de tutti.ch")
            return None
        build_id = match.group(1)
        log.info("tutti.ch buildId resuelto: %s", build_id)
        return build_id

    async def _get(self, session: Any, url: str) -> Any | None:
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:
            log.debug("error de transporte %s: %s", url[:90], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(
                self.RETRY_BACKOFF_BASE ** attempt * factor + random.uniform(0, 0.25)
            )
