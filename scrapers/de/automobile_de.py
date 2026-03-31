"""
Automobile.de — German used car portal (Axel Springer group).
API: JSON search endpoint.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper
from scrapers.common.models import RawListing

_API_URL = "https://www.automobile.de/api/v2/search/vehicles"
_PAGE_SIZE = 24


class AutomobileDEScraper(BaseScraper):
    PLATFORM = "automobile_de"
    COUNTRY = "DE"
    BASE_DOMAIN = "www.automobile.de"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        page = await self._get_cursor(make, year) or 1

        while True:
            params = {
                "make": make,
                "yearFrom": str(year),
                "yearTo": str(year),
                "page": str(page),
                "pageSize": str(_PAGE_SIZE),
                "sort": "createdAt_desc",
                "channel": "DE",
            }
            try:
                data = await self.http.get_json(
                    _API_URL, params=params,
                    headers={"Accept": "application/json", "Accept-Language": "de-DE"},
                )
            except Exception as exc:
                self.logger.warning("automobile_de page %d: %s", page, exc)
                break

            items = data.get("vehicles") or data.get("ads") or data.get("results") or []
            if not items:
                break

            for item in items:
                listing = self._parse(item, make, year)
                if listing:
                    yield listing

            await self._set_cursor(make, year, page)

            total = data.get("totalCount") or data.get("total") or 0
            total_pages = (total + _PAGE_SIZE - 1) // _PAGE_SIZE
            if page >= total_pages or len(items) < _PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(self._rate_delay())

    def _parse(self, item: dict, make: str, year: int) -> RawListing | None:
        try:
            vid = str(item.get("id") or item.get("adId", ""))
            price = float(item.get("price") or item.get("consumerPrice") or 0)
            km = item.get("mileage") or item.get("km")
            mileage = int(str(km).replace(".", "").replace(" km", "")) if km else None

            images = item.get("images") or item.get("photos") or []
            thumb = images[0].get("url") if images and isinstance(images[0], dict) else None

            return RawListing(
                platform=self.PLATFORM, country=self.COUNTRY, listing_id=vid,
                source_url=item.get("detailUrl") or f"https://www.automobile.de/gebrauchtwagen/{vid}",
                make=make, model=item.get("model") or "",
                year=int(item.get("year") or item.get("firstRegistrationYear") or year),
                price_eur=price if price > 0 else None, mileage_km=mileage,
                fuel_type=item.get("fuelType") or item.get("fuel"),
                body_type=item.get("bodyType"),
                city=item.get("location", {}).get("city") if isinstance(item.get("location"), dict) else None,
                seller_name=item.get("seller", {}).get("name") if isinstance(item.get("seller"), dict) else None,
                thumbnail_url=thumb, raw=item,
            )
        except Exception:
            return None
