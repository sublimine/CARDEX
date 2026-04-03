"""
Autotrack.nl — Netherlands' professional car classifieds.
API: JSON search with brand + year facets.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper
from scrapers.common.models import RawListing

_API_URL = "https://www.autotrack.nl/api/search/cars"
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
    "SEAT": "seat", "Skoda": "skoda", "Subaru": "subaru",
    "Suzuki": "suzuki", "Tesla": "tesla", "Toyota": "toyota",
    "Volkswagen": "volkswagen", "Volvo": "volvo",
}


class AutotrackNLScraper(BaseScraper):
    PLATFORM = "autotrack_nl"
    COUNTRY = "NL"
    BASE_DOMAIN = "www.autotrack.nl"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        make_slug = _MAKE_MAP.get(make)
        if not make_slug:
            return

        page = await self._get_cursor(make, year) or 1

        while True:
            params = {
                "brand": make_slug,
                "yearFrom": str(year),
                "yearTo": str(year),
                "page": str(page),
                "pageSize": str(_PAGE_SIZE),
                "sortType": "DateDesc",
            }
            try:
                data = await self.http.get_json(
                    _API_URL,
                    params=params,
                    headers={"Accept": "application/json", "Accept-Language": "nl-NL"},
                )
            except Exception as exc:
                self.logger.warning("autotrack_nl page %d: %s", page, exc)
                break

            vehicles = data.get("vehicles") or data.get("cars") or data.get("results") or []
            if not vehicles:
                break

            for v in vehicles:
                listing = self._parse(v, make, year)
                if listing:
                    yield listing

            await self._set_cursor(make, year, page)

            total = data.get("totalCount") or data.get("total") or 0
            total_pages = (total + _PAGE_SIZE - 1) // _PAGE_SIZE
            if page >= total_pages or len(vehicles) < _PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(self._rate_delay())

    def _parse(self, v: dict, make: str, year: int) -> RawListing | None:
        try:
            vid = str(v.get("id") or v.get("vehicleId", ""))
            price = float(v.get("price") or v.get("askingPrice") or 0)
            km = v.get("mileage") or v.get("km")
            mileage = int(str(km).replace(".", "").replace(" km", "")) if km else None

            images = v.get("images") or v.get("photos") or []
            thumb = images[0].get("url") if images and isinstance(images[0], dict) else (images[0] if images else None)

            return RawListing(
                platform=self.PLATFORM,
                country=self.COUNTRY,
                listing_id=vid,
                source_url=v.get("url") or f"https://www.autotrack.nl/auto/{vid}",
                make=make,
                model=v.get("model") or "",
                year=int(v.get("year") or year),
                price_eur=price if price > 0 else None,
                mileage_km=mileage,
                fuel_type=v.get("fuelType") or v.get("energy"),
                city=v.get("city") or v.get("location"),
                thumbnail_url=thumb if isinstance(thumb, str) else None,
                seller_name=v.get("dealer", {}).get("name") if isinstance(v.get("dealer"), dict) else v.get("sellerName"),
                raw=v,
            )
        except Exception:
            return None
