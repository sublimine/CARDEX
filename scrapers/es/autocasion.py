"""
Autocasión — Spain professional car classifieds.
API: JSON search endpoint.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper
from scrapers.common.models import RawListing

_API_URL = "https://www.autocasion.com/api/cars/search"
_PAGE_SIZE = 30


class AutocasionESScraper(BaseScraper):
    PLATFORM = "autocasion_es"
    COUNTRY = "ES"
    BASE_DOMAIN = "www.autocasion.com"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        page = await self._get_cursor(make, year) or 1

        while True:
            params = {
                "brand": make.lower().replace(" ", "-").replace("é", "e").replace("ë", "e"),
                "yearMin": str(year),
                "yearMax": str(year),
                "page": str(page),
                "pageSize": str(_PAGE_SIZE),
            }
            try:
                data = await self.http.get_json(
                    _API_URL, params=params, headers={"Accept": "application/json"},
                )
            except Exception as exc:
                self.logger.warning("autocasion page %d: %s", page, exc)
                break

            items = data.get("cars") or data.get("results") or []
            if not items:
                break

            for item in items:
                listing = self._parse(item, make, year)
                if listing:
                    yield listing

            await self._set_cursor(make, year, page)

            total = data.get("total") or data.get("totalCount") or 0
            if page >= (total + _PAGE_SIZE - 1) // _PAGE_SIZE or len(items) < _PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(self._rate_delay())

    def _parse(self, item: dict, make: str, year: int) -> RawListing | None:
        try:
            cid = str(item.get("id", ""))
            price = float(item.get("price") or 0)
            km = item.get("km") or item.get("mileage")
            mileage = int(str(km).replace(".", "").replace(" km", "")) if km else None
            images = item.get("images") or []
            thumb = images[0] if images and isinstance(images[0], str) else None

            return RawListing(
                platform=self.PLATFORM, country=self.COUNTRY, listing_id=cid,
                source_url=item.get("url") or f"https://www.autocasion.com/coches-segunda-mano/{cid}",
                make=make, model=item.get("model") or "", year=int(item.get("year") or year),
                price_eur=price if price > 0 else None, mileage_km=mileage,
                fuel_type=item.get("fuel"), city=item.get("province"),
                thumbnail_url=thumb, raw=item,
            )
        except Exception:
            return None
