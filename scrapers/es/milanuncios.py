"""
Milanuncios — Spain's second-largest classifieds (Adevinta group).
API: JSON search for category "Motor > Coches".
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper
from scrapers.common.models import RawListing

_API_URL = "https://www.milanuncios.com/api/v1/search"
_PAGE_SIZE = 40

_MAKE_MAP: dict[str, str] = {
    "Alfa Romeo": "alfa-romeo", "Audi": "audi", "BMW": "bmw",
    "Citroën": "citroen", "Cupra": "cupra", "Dacia": "dacia",
    "Ferrari": "ferrari", "Fiat": "fiat", "Ford": "ford",
    "Honda": "honda", "Hyundai": "hyundai", "Jaguar": "jaguar",
    "Jeep": "jeep", "Kia": "kia", "Land Rover": "land-rover",
    "Lexus": "lexus", "Maserati": "maserati", "Mazda": "mazda",
    "Mercedes-Benz": "mercedes-benz", "Mini": "mini", "Mitsubishi": "mitsubishi",
    "Nissan": "nissan", "Opel": "opel", "Peugeot": "peugeot",
    "Porsche": "porsche", "Renault": "renault", "SEAT": "seat",
    "Skoda": "skoda", "Smart": "smart", "Subaru": "subaru",
    "Suzuki": "suzuki", "Tesla": "tesla", "Toyota": "toyota",
    "Volkswagen": "volkswagen", "Volvo": "volvo",
}


class MilanunciosESScraper(BaseScraper):
    PLATFORM = "milanuncios_es"
    COUNTRY = "ES"
    BASE_DOMAIN = "www.milanuncios.com"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        make_slug = _MAKE_MAP.get(make)
        if not make_slug:
            return

        page = await self._get_cursor(make, year) or 1

        while True:
            params = {
                "category": "coches",
                "brand": make_slug,
                "year": str(year),
                "numPage": str(page),
                "numItems": str(_PAGE_SIZE),
            }
            try:
                data = await self.http.get_json(
                    _API_URL,
                    params=params,
                    headers={"Accept": "application/json", "Origin": "https://www.milanuncios.com"},
                )
            except Exception as exc:
                self.logger.warning("milanuncios page %d: %s", page, exc)
                break

            items = data.get("items") or data.get("adList") or []
            if not items:
                break

            for item in items:
                listing = self._parse(item, make, year)
                if listing:
                    yield listing

            await self._set_cursor(make, year, page)

            total = data.get("totalPages") or data.get("numPages") or 0
            if page >= total or len(items) < _PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(self._rate_delay())

    def _parse(self, item: dict, make: str, year: int) -> RawListing | None:
        try:
            ad_id = str(item.get("adId") or item.get("id", ""))
            price_raw = item.get("price", {})
            price = float(price_raw.get("value", 0)) if isinstance(price_raw, dict) else float(price_raw or 0)

            km_raw = item.get("km") or item.get("mileage")
            mileage = int(str(km_raw).replace(".", "").replace(" km", "")) if km_raw else None

            images = item.get("images") or item.get("photos") or []
            thumb = images[0].get("url") if images and isinstance(images[0], dict) else (images[0] if images else None)

            return RawListing(
                platform=self.PLATFORM,
                country=self.COUNTRY,
                listing_id=ad_id,
                source_url=item.get("url") or f"https://www.milanuncios.com/anuncio/{ad_id}.htm",
                make=make,
                model=item.get("model") or item.get("version") or "",
                year=year,
                price_eur=price if price > 0 else None,
                mileage_km=mileage,
                fuel_type=item.get("fuelType") or item.get("fuel"),
                city=item.get("province") or item.get("location"),
                thumbnail_url=thumb,
                seller_name=item.get("sellerName"),
                raw=item,
            )
        except Exception:
            return None
