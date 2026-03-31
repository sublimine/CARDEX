"""
Coches.com — Spanish used car classifieds (Grupo Vocento).
API: JSON search endpoint.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper
from scrapers.common.models import RawListing

_API_URL = "https://www.coches.com/api/search"
_PAGE_SIZE = 30

_MAKE_MAP: dict[str, str] = {
    "Alfa Romeo": "alfa-romeo", "Audi": "audi", "BMW": "bmw",
    "Citroën": "citroen", "Cupra": "cupra", "Dacia": "dacia",
    "Fiat": "fiat", "Ford": "ford", "Honda": "honda",
    "Hyundai": "hyundai", "Jaguar": "jaguar", "Jeep": "jeep",
    "Kia": "kia", "Land Rover": "land-rover", "Lexus": "lexus",
    "Mazda": "mazda", "Mercedes-Benz": "mercedes-benz", "Mini": "mini",
    "Mitsubishi": "mitsubishi", "Nissan": "nissan", "Opel": "opel",
    "Peugeot": "peugeot", "Porsche": "porsche", "Renault": "renault",
    "SEAT": "seat", "Skoda": "skoda", "Tesla": "tesla",
    "Toyota": "toyota", "Volkswagen": "volkswagen", "Volvo": "volvo",
}


class CochesCOMScraper(BaseScraper):
    PLATFORM = "coches_com"
    COUNTRY = "ES"
    BASE_DOMAIN = "www.coches.com"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        make_slug = _MAKE_MAP.get(make)
        if not make_slug:
            return

        page = await self._get_cursor(make, year) or 1

        while True:
            params = {
                "marca": make_slug,
                "anio_desde": str(year),
                "anio_hasta": str(year),
                "pagina": str(page),
                "resultados": str(_PAGE_SIZE),
                "orden": "fecha",
            }
            try:
                data = await self.http.get_json(
                    _API_URL, params=params,
                    headers={"Accept": "application/json", "Accept-Language": "es-ES"},
                )
            except Exception as exc:
                self.logger.warning("coches_com page %d: %s", page, exc)
                break

            items = data.get("anuncios") or data.get("vehicles") or data.get("results") or []
            if not items:
                break

            for item in items:
                listing = self._parse(item, make, year)
                if listing:
                    yield listing

            await self._set_cursor(make, year, page)

            total = data.get("totalResultados") or data.get("total") or 0
            total_pages = (total + _PAGE_SIZE - 1) // _PAGE_SIZE
            if page >= total_pages or len(items) < _PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(self._rate_delay())

    def _parse(self, item: dict, make: str, year: int) -> RawListing | None:
        try:
            aid = str(item.get("id") or item.get("anuncioId", ""))
            price = float(item.get("precio") or item.get("price") or 0)
            km = item.get("km") or item.get("kilometros") or item.get("mileage")
            mileage = int(str(km).replace(".", "").replace(" km", "")) if km else None

            images = item.get("fotos") or item.get("images") or []
            thumb = images[0] if images and isinstance(images[0], str) else (
                images[0].get("url") if images else None
            )

            return RawListing(
                platform=self.PLATFORM, country=self.COUNTRY, listing_id=aid,
                source_url=item.get("url") or f"https://www.coches.com/coches-segunda-mano/{aid}.htm",
                make=make, model=item.get("modelo") or item.get("model") or "",
                year=int(item.get("ano") or item.get("year") or year),
                price_eur=price if price > 0 else None, mileage_km=mileage,
                fuel_type=item.get("combustible") or item.get("fuel"),
                city=item.get("provincia") or item.get("localidad"),
                thumbnail_url=thumb if isinstance(thumb, str) else None,
                raw=item,
            )
        except Exception:
            return None
