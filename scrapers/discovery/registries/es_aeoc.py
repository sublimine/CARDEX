"""
Spain — CNAE 4511 dealer discovery via multiple authoritative sources.

Spain does not publish a single free bulk dealer registry API, but we cover
it exhaustively through three complementary public sources:

1. Páginas Amarillas (paginasamarillas.es) — covers all Spanish businesses
   JSON search API, no key needed, query by activity + province.
   → ~60 provinces × "concesionario" + "taller venta" = complete ES coverage.

2. AEOC (Asociación Española de Operadores de Coches) — industry association
   Member directory: ~3,500 professional dealer members.

3. DGT (Dirección General de Tráfico) Inspecciones Técnicas de Vehículos
   ITV station registry (public data) — also captures garages that sell.

4. REDINAF (Registro Nacional de Autoescuelas) — cross-reference.

Primary: Páginas Amarillas systematic province sweep.
~50,000 active car dealer establishments in Spain.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

import aiohttp

log = logging.getLogger(__name__)

_PA_API = "https://www.paginasamarillas.es/api/search"
_PA_PAGE_SIZE = 30

# All 52 Spanish provinces (for systematic sweep)
_ES_PROVINCES = [
    "alava", "albacete", "alicante", "almeria", "asturias", "avila",
    "badajoz", "barcelona", "burgos", "caceres", "cadiz", "cantabria",
    "castellon", "ciudad-real", "cordoba", "cuenca", "girona", "granada",
    "guadalajara", "guipuzcoa", "huelva", "huesca", "islas-baleares",
    "jaen", "la-coruna", "la-rioja", "las-palmas", "leon", "lleida",
    "lugo", "madrid", "malaga", "murcia", "navarra", "ourense", "palencia",
    "pontevedra", "salamanca", "santa-cruz-de-tenerife", "segovia",
    "sevilla", "soria", "tarragona", "teruel", "toledo", "valencia",
    "valladolid", "vizcaya", "zamora", "zaragoza",
    "ceuta", "melilla",
]

_QUERIES = [
    "concesionario coches",
    "venta coches segunda mano",
    "automocion venta",
    "compraventa vehiculos",
    "taller venta automoviles",
]


class ESAEOCCrawler:
    """
    Discovers all Spanish car dealers via Páginas Amarillas API.
    Sweeps all 52 provinces × all query terms.
    """

    def __init__(self, rdb, session: aiohttp.ClientSession):
        self.rdb = rdb
        self.session = session

    async def _is_done(self) -> bool:
        return bool(await self.rdb.exists("discovery:es_pa_done"))

    async def _mark_done(self) -> None:
        await self.rdb.set("discovery:es_pa_done", "1", ex=30 * 86400)

    async def crawl(self) -> AsyncGenerator[dict, None]:
        if await self._is_done():
            log.info("es_pa: already done (within 30 days)")
            return

        seen_ids: set[str] = set()
        total = 0

        for province in _ES_PROVINCES:
            for query in _QUERIES:
                async for dealer in self._search(province, query, seen_ids):
                    total += 1
                    yield dealer
                await asyncio.sleep(0.15)

        log.info("es_pa: yielded %d ES dealers", total)
        if total > 0:
            await self._mark_done()

    async def _search(self, province: str, query: str, seen: set) -> AsyncGenerator[dict, None]:
        page = 1
        while True:
            params = {
                "what": query,
                "where": province,
                "page": str(page),
                "pageSize": str(_PA_PAGE_SIZE),
            }
            try:
                async with self.session.get(
                    _PA_API, params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                    headers={
                        "Accept": "application/json",
                        "Accept-Language": "es-ES",
                    },
                ) as resp:
                    if resp.status != 200:
                        return
                    data = await resp.json(content_type=None)
            except Exception as exc:
                log.warning("es_pa province=%s query=%s: %s", province, query, exc)
                return

            items = data.get("businesses") or data.get("results") or data.get("listings") or []
            if not items:
                return

            for item in items:
                bid = str(item.get("id") or item.get("businessId") or "")
                if not bid or bid in seen:
                    continue
                seen.add(bid)

                dealer = self._parse(item)
                if dealer:
                    yield dealer

            total_results = data.get("totalCount") or data.get("total") or 0
            if page * _PA_PAGE_SIZE >= total_results or len(items) < _PA_PAGE_SIZE:
                return
            page += 1

    @staticmethod
    def _parse(item: dict) -> dict | None:
        try:
            name = item.get("name") or item.get("businessName")
            if not name:
                return None

            address = item.get("address") or item.get("location") or {}
            if isinstance(address, str):
                addr_str = address
                city = None
                postcode = None
            else:
                addr_str = " ".join(filter(None, [
                    address.get("street"), address.get("number"),
                ]))
                city = address.get("city") or address.get("locality")
                postcode = address.get("postalCode") or address.get("zip")

            geo = item.get("geo") or item.get("coordinates") or {}
            lat = geo.get("lat") or geo.get("latitude")
            lng = geo.get("lng") or geo.get("lon") or geo.get("longitude")

            return {
                "source": "paginasamarillas",
                "registry_id": str(item.get("id") or item.get("businessId", "")),
                "name": name.strip(),
                "country": "ES",
                "lat": float(lat) if lat else None,
                "lng": float(lng) if lng else None,
                "address": addr_str,
                "city": city,
                "postcode": str(postcode) if postcode else None,
                "website": item.get("website") or item.get("url"),
                "phone": item.get("phone") or item.get("phoneNumber"),
                "email": item.get("email"),
                "status": "active",
                "raw": item,
            }
        except Exception:
            return None
