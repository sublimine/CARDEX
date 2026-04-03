"""
Autohero — online-only used car retailer (AUTO1 Group).
Fixed-price, no negotiation. Pan-European, DE stronghold.
API: REST JSON catalog.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper
from scrapers.common.models import RawListing

_API_URL = "https://www.autohero.com/de/api/v2/vehicles"
_PAGE_SIZE = 24


class AutoheroDEScraper(BaseScraper):
    PLATFORM = "autohero_de"
    COUNTRY = "DE"
    BASE_DOMAIN = "www.autohero.com"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        page = await self._get_cursor(make, year) or 0  # 0-indexed

        while True:
            params = {
                "make": make.upper().replace(" ", "_").replace("-", "_"),
                "registrationYearFrom": str(year),
                "registrationYearTo": str(year),
                "page": str(page),
                "pageSize": str(_PAGE_SIZE),
                "sort": "LISTED_AT_DESC",
                "country": "DE",
            }
            try:
                data = await self.http.get_json(
                    _API_URL, params=params,
                    headers={
                        "Accept": "application/json",
                        "Accept-Language": "de-DE",
                        "X-Country": "DE",
                    },
                )
            except Exception as exc:
                self.logger.warning("autohero page %d: %s", page, exc)
                break

            items = data.get("items") or data.get("vehicles") or data.get("content") or []
            if not items:
                break

            for item in items:
                listing = self._parse(item, make, year)
                if listing:
                    yield listing

            cursor = page + 1
            await self._set_cursor(make, year, cursor)

            total_pages = data.get("totalPages") or 1
            if page + 1 >= total_pages or len(items) < _PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(self._rate_delay())

    def _parse(self, item: dict, make: str, year: int) -> RawListing | None:
        try:
            vid = str(item.get("id") or item.get("stockItemId", ""))
            price = float(item.get("price") or item.get("retailPrice") or 0)
            km = item.get("mileage") or item.get("mileageKm")
            mileage = int(km) if km else None

            images = item.get("images") or []
            thumb = images[0].get("url") if images and isinstance(images[0], dict) else None
            photo_urls = [img.get("url") for img in images[:8] if isinstance(img, dict) and img.get("url")]

            vin = item.get("vin") or item.get("vehicleIdentificationNumber")

            return RawListing(
                platform=self.PLATFORM, country=self.COUNTRY, listing_id=vid,
                source_url=f"https://www.autohero.com/de/gebrauchtwagen/{vid}",
                make=make, model=item.get("model") or item.get("modelVersion") or "",
                year=int(item.get("registrationYear") or year),
                price_eur=price if price > 0 else None, mileage_km=mileage,
                fuel_type=item.get("fuelType"), body_type=item.get("bodyType"),
                vin=vin, seller_name="Autohero",
                thumbnail_url=thumb, photo_urls=photo_urls, raw=item,
            )
        except Exception:
            return None
