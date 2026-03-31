"""
Wallapop — Spain's mobile-first C2C marketplace.
API: REST JSON /api/v3/general/search with category_id=100 (Cars).
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper
from scrapers.common.models import RawListing

_API_URL = "https://api.wallapop.com/api/v3/cars/search"
_PAGE_SIZE = 40

_MAKE_MAP: dict[str, str] = {
    "Audi": "audi", "BMW": "bmw", "Citroën": "citroen", "Cupra": "cupra",
    "Dacia": "dacia", "Fiat": "fiat", "Ford": "ford", "Honda": "honda",
    "Hyundai": "hyundai", "Jaguar": "jaguar", "Jeep": "jeep", "Kia": "kia",
    "Land Rover": "land_rover", "Mazda": "mazda", "Mercedes-Benz": "mercedes_benz",
    "Mini": "mini", "Mitsubishi": "mitsubishi", "Nissan": "nissan",
    "Opel": "opel", "Peugeot": "peugeot", "Porsche": "porsche",
    "Renault": "renault", "SEAT": "seat", "Skoda": "skoda",
    "Smart": "smart", "Suzuki": "suzuki", "Tesla": "tesla",
    "Toyota": "toyota", "Volkswagen": "volkswagen", "Volvo": "volvo",
}


class WallapopESScraper(BaseScraper):
    PLATFORM = "wallapop_es"
    COUNTRY = "ES"
    BASE_DOMAIN = "api.wallapop.com"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        make_key = _MAKE_MAP.get(make)
        if not make_key:
            return

        start = (await self._get_cursor(make, year) or 1) - 1  # wallapop uses offset 0-based

        while True:
            params = {
                "brand": make_key,
                "min_year": str(year),
                "max_year": str(year),
                "start": str(start),
                "step": str(_PAGE_SIZE),
                "order_by": "newest",
            }
            try:
                data = await self.http.get_json(
                    _API_URL,
                    params=params,
                    headers={
                        "Accept": "application/json, text/plain, */*",
                        "DeviceOS": "0",
                    },
                )
            except Exception as exc:
                self.logger.warning("wallapop offset %d: %s", start, exc)
                break

            items = data.get("search_objects") or []
            if not items:
                break

            for item in items:
                listing = self._parse(item, make, year)
                if listing:
                    yield listing

            page_num = (start // _PAGE_SIZE) + 1
            await self._set_cursor(make, year, page_num)

            if len(items) < _PAGE_SIZE:
                break

            start += _PAGE_SIZE
            await asyncio.sleep(self._rate_delay())

    def _parse(self, item: dict, make: str, year: int) -> RawListing | None:
        try:
            item_id = str(item.get("id", ""))
            content = item.get("content", {})

            price = float(content.get("sale_price") or item.get("price") or 0)
            km_raw = content.get("km") or content.get("kms")
            mileage = int(str(km_raw).replace(".", "")) if km_raw else None

            images = content.get("images") or item.get("images") or []
            thumb = None
            photo_urls = []
            for img in images:
                urls = img.get("urls") or {}
                url = urls.get("medium") or urls.get("large") or img.get("url", "")
                if url:
                    if not thumb:
                        thumb = url
                    photo_urls.append(url)

            return RawListing(
                platform=self.PLATFORM,
                country=self.COUNTRY,
                listing_id=item_id,
                source_url=f"https://es.wallapop.com/item/{item.get('web_slug', item_id)}",
                make=make,
                model=content.get("model") or "",
                year=int(content.get("year", year)),
                price_eur=price if price > 0 else None,
                mileage_km=mileage,
                fuel_type=content.get("engine"),
                city=item.get("location", {}).get("city"),
                thumbnail_url=thumb,
                photo_urls=photo_urls[:8],
                seller_name=item.get("user", {}).get("micro_name"),
                raw=item,
            )
        except Exception:
            return None
