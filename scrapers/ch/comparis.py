"""
Comparis.ch — Switzerland's leading car comparison portal.
API: GraphQL endpoint for car search.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper
from scrapers.common.models import RawListing

_API_URL = "https://www.comparis.ch/api/vehicles/search"
_PAGE_SIZE = 25

_MAKE_MAP: dict[str, str] = {
    "Alfa Romeo": "Alfa Romeo", "Audi": "Audi", "BMW": "BMW",
    "Citroën": "Citroen", "Cupra": "Cupra", "Dacia": "Dacia",
    "Ferrari": "Ferrari", "Fiat": "Fiat", "Ford": "Ford",
    "Honda": "Honda", "Hyundai": "Hyundai", "Jaguar": "Jaguar",
    "Jeep": "Jeep", "Kia": "Kia", "Land Rover": "Land Rover",
    "Lexus": "Lexus", "Maserati": "Maserati", "Mazda": "Mazda",
    "Mercedes-Benz": "Mercedes-Benz", "Mini": "Mini", "Mitsubishi": "Mitsubishi",
    "Nissan": "Nissan", "Opel": "Opel", "Peugeot": "Peugeot",
    "Porsche": "Porsche", "Renault": "Renault", "SEAT": "Seat",
    "Skoda": "Skoda", "Subaru": "Subaru", "Suzuki": "Suzuki",
    "Tesla": "Tesla", "Toyota": "Toyota", "Volkswagen": "Volkswagen",
    "Volvo": "Volvo",
}

# CHF → EUR approximate rate (refreshed from Redis in production)
_CHF_TO_EUR = 0.94


class ComparisChScraper(BaseScraper):
    PLATFORM = "comparis_ch"
    COUNTRY = "CH"
    BASE_DOMAIN = "www.comparis.ch"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        make_label = _MAKE_MAP.get(make)
        if not make_label:
            return

        page = await self._get_cursor(make, year) or 1

        while True:
            payload = {
                "makes": [make_label],
                "yearFrom": year,
                "yearTo": year,
                "pageNumber": page,
                "pageSize": _PAGE_SIZE,
                "sortOrder": "NewestFirst",
            }
            try:
                data = await self.http.post_json(
                    _API_URL,
                    json=payload,
                    headers={"Accept": "application/json", "Accept-Language": "de-CH"},
                )
            except Exception as exc:
                self.logger.warning("comparis_ch page %d: %s", page, exc)
                break

            items = data.get("results") or data.get("vehicles") or []
            if not items:
                break

            for item in items:
                listing = self._parse(item, make, year)
                if listing:
                    yield listing

            await self._set_cursor(make, year, page)

            total = data.get("totalCount") or 0
            total_pages = (total + _PAGE_SIZE - 1) // _PAGE_SIZE
            if page >= total_pages or len(items) < _PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(self._rate_delay())

    def _parse(self, item: dict, make: str, year: int) -> RawListing | None:
        try:
            vid = str(item.get("id") or item.get("vehicleId", ""))
            price_chf = float(item.get("price") or item.get("priceCHF") or 0)
            price_eur = round(price_chf * _CHF_TO_EUR, 2) if price_chf > 0 else None

            km = item.get("mileage") or item.get("km")
            mileage = int(str(km).replace("'", "").replace(" km", "")) if km else None

            images = item.get("images") or item.get("photos") or []
            thumb = images[0].get("url") if images and isinstance(images[0], dict) else (images[0] if images else None)

            return RawListing(
                platform=self.PLATFORM,
                country=self.COUNTRY,
                listing_id=vid,
                source_url=item.get("url") or f"https://www.comparis.ch/auto/marktplatz/details/{vid}",
                make=make,
                model=item.get("model") or item.get("modelName") or "",
                year=int(item.get("year") or year),
                price_eur=price_eur,
                mileage_km=mileage,
                fuel_type=item.get("fuelType") or item.get("energy"),
                city=item.get("city") or item.get("canton"),
                region=item.get("canton"),
                thumbnail_url=thumb if isinstance(thumb, str) else None,
                seller_name=item.get("dealer", {}).get("name") if isinstance(item.get("dealer"), dict) else None,
                raw=item,
            )
        except Exception:
            return None
