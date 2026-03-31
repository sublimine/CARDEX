"""
Heycar — premium certified used car platform (VW Group / Mercedes).
DE focus, also operates in FR and GB.
API: GraphQL / REST JSON search.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper
from scrapers.common.models import RawListing

_API_URL = "https://hey.car/api/vehicles"
_PAGE_SIZE = 24

_MAKE_MAP: dict[str, str] = {
    "Audi": "audi", "BMW": "bmw", "Cupra": "cupra", "Fiat": "fiat",
    "Ford": "ford", "Honda": "honda", "Hyundai": "hyundai", "Jaguar": "jaguar",
    "Jeep": "jeep", "Kia": "kia", "Land Rover": "land_rover", "Mazda": "mazda",
    "Mercedes-Benz": "mercedes_benz", "Mini": "mini", "Mitsubishi": "mitsubishi",
    "Nissan": "nissan", "Opel": "opel", "Peugeot": "peugeot", "Porsche": "porsche",
    "Renault": "renault", "SEAT": "seat", "Skoda": "skoda", "Tesla": "tesla",
    "Toyota": "toyota", "Volkswagen": "volkswagen", "Volvo": "volvo",
}


class HeycarDEScraper(BaseScraper):
    PLATFORM = "heycar_de"
    COUNTRY = "DE"
    BASE_DOMAIN = "hey.car"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        make_slug = _MAKE_MAP.get(make)
        if not make_slug:
            return

        page = await self._get_cursor(make, year) or 0  # heycar is 0-indexed

        while True:
            params = {
                "make": make_slug,
                "firstRegistrationYearFrom": str(year),
                "firstRegistrationYearTo": str(year),
                "page": str(page),
                "size": str(_PAGE_SIZE),
                "sort": "createdAt,desc",
            }
            try:
                data = await self.http.get_json(
                    _API_URL, params=params,
                    headers={"Accept": "application/json", "Accept-Language": "de-DE"},
                )
            except Exception as exc:
                self.logger.warning("heycar_de page %d: %s", page, exc)
                break

            items = data.get("vehicles") or data.get("content") or data.get("results") or []
            if not items:
                break

            for item in items:
                listing = self._parse(item, make, year)
                if listing:
                    yield listing

            cursor_page = page + 1
            await self._set_cursor(make, year, cursor_page)

            total_pages = data.get("totalPages") or data.get("pageCount") or 1
            if page + 1 >= total_pages or len(items) < _PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(self._rate_delay())

    def _parse(self, item: dict, make: str, year: int) -> RawListing | None:
        try:
            vid = str(item.get("id") or item.get("vehicleId", ""))
            price = float(item.get("price") or item.get("consumerPriceGross") or 0)
            km = item.get("mileageInKm") or item.get("mileage")
            mileage = int(km) if km else None

            images = item.get("images") or []
            thumb = images[0].get("url") if images and isinstance(images[0], dict) else None

            return RawListing(
                platform=self.PLATFORM, country=self.COUNTRY, listing_id=vid,
                source_url=item.get("url") or f"https://hey.car/angebote/{vid}",
                make=make, model=item.get("model") or item.get("modelVersion") or "",
                year=int(item.get("firstRegistrationYear") or year),
                price_eur=price if price > 0 else None, mileage_km=mileage,
                fuel_type=item.get("fuel") or item.get("fuelType"),
                body_type=item.get("bodyType"),
                city=item.get("location", {}).get("city") if isinstance(item.get("location"), dict) else None,
                seller_name=item.get("dealer", {}).get("name") if isinstance(item.get("dealer"), dict) else None,
                thumbnail_url=thumb, raw=item,
            )
        except Exception:
            return None
