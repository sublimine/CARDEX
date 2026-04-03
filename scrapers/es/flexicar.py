"""
Flexicar — Spain's largest used car dealer chain (Mobility ADO group).
Dealer-only stock: certified used vehicles from ~100 physical locations.
API: REST JSON catalog.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper
from scrapers.common.models import RawListing

_API_URL = "https://www.flexicar.es/api/v2/cars/search"
_PAGE_SIZE = 24


class FlexicarESScraper(BaseScraper):
    PLATFORM = "flexicar_es"
    COUNTRY = "ES"
    BASE_DOMAIN = "www.flexicar.es"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        page = await self._get_cursor(make, year) or 1

        while True:
            params = {
                "brand": make,
                "yearFrom": str(year),
                "yearTo": str(year),
                "page": str(page),
                "limit": str(_PAGE_SIZE),
                "sort": "date_desc",
            }
            try:
                data = await self.http.get_json(
                    _API_URL, params=params,
                    headers={"Accept": "application/json", "Accept-Language": "es-ES"},
                )
            except Exception as exc:
                self.logger.warning("flexicar page %d: %s", page, exc)
                break

            items = data.get("cars") or data.get("vehicles") or data.get("results") or []
            if not items:
                break

            for item in items:
                listing = self._parse(item, make, year)
                if listing:
                    yield listing

            await self._set_cursor(make, year, page)

            total = data.get("total") or data.get("count") or 0
            total_pages = (total + _PAGE_SIZE - 1) // _PAGE_SIZE
            if page >= total_pages or len(items) < _PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(self._rate_delay())

    def _parse(self, item: dict, make: str, year: int) -> RawListing | None:
        try:
            vid = str(item.get("id") or item.get("carId", ""))
            price = float(item.get("price") or item.get("salePrice") or 0)
            km = item.get("km") or item.get("mileage")
            mileage = int(str(km).replace(".", "").replace(" km", "")) if km else None

            images = item.get("images") or item.get("photos") or []
            thumb = images[0].get("url") if images and isinstance(images[0], dict) else None

            return RawListing(
                platform=self.PLATFORM, country=self.COUNTRY, listing_id=vid,
                source_url=item.get("url") or f"https://www.flexicar.es/coche/{vid}",
                make=make, model=item.get("model") or item.get("version") or "",
                year=int(item.get("year") or year),
                price_eur=price if price > 0 else None, mileage_km=mileage,
                fuel_type=item.get("fuelType") or item.get("combustible"),
                city=item.get("city") or item.get("location") or item.get("dealership"),
                seller_name="Flexicar",
                thumbnail_url=thumb,
                raw=item,
            )
        except Exception:
            return None
