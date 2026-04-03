"""
Gocar.be — Belgium's dedicated car classifieds portal.
API: JSON search endpoint.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper
from scrapers.common.models import RawListing

_API_URL = "https://www.gocar.be/api/search/vehicles"
_PAGE_SIZE = 24


class GocarBEScraper(BaseScraper):
    PLATFORM = "gocar_be"
    COUNTRY = "BE"
    BASE_DOMAIN = "www.gocar.be"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        page = await self._get_cursor(make, year) or 1

        while True:
            params = {
                "make": make,
                "yearMin": str(year),
                "yearMax": str(year),
                "page": str(page),
                "limit": str(_PAGE_SIZE),
                "sort": "date_desc",
            }
            try:
                data = await self.http.get_json(
                    _API_URL, params=params, headers={"Accept": "application/json"},
                )
            except Exception as exc:
                self.logger.warning("gocar_be page %d: %s", page, exc)
                break

            items = data.get("vehicles") or data.get("results") or []
            if not items:
                break

            for item in items:
                listing = self._parse(item, make, year)
                if listing:
                    yield listing

            await self._set_cursor(make, year, page)

            total = data.get("total") or 0
            total_pages = (total + _PAGE_SIZE - 1) // _PAGE_SIZE
            if page >= total_pages or len(items) < _PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(self._rate_delay())

    def _parse(self, item: dict, make: str, year: int) -> RawListing | None:
        try:
            vid = str(item.get("id", ""))
            price = float(item.get("price") or 0)
            km = item.get("mileage") or item.get("km")
            mileage = int(str(km).replace(".", "").replace(" km", "")) if km else None
            images = item.get("images") or []
            thumb = images[0].get("url") if images and isinstance(images[0], dict) else None

            return RawListing(
                platform=self.PLATFORM, country=self.COUNTRY, listing_id=vid,
                source_url=item.get("url") or f"https://www.gocar.be/vehicle/{vid}",
                make=make, model=item.get("model") or "", year=int(item.get("year") or year),
                price_eur=price if price > 0 else None, mileage_km=mileage,
                fuel_type=item.get("fuelType"), city=item.get("city"),
                thumbnail_url=thumb, raw=item,
            )
        except Exception:
            return None
