"""
Tweedehands.be — Belgium's largest general classifieds (Marktplaats group).
API: Same Adevinta stack as marktplaats.nl. Category l1=91 (Auto's).
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper
from scrapers.common.models import RawListing

_API_URL = "https://www.tweedehands.be/lrp/api/search"
_PAGE_SIZE = 100

_MAKE_MAP: dict[str, str] = {
    "Alfa Romeo": "Alfa Romeo", "Audi": "Audi", "BMW": "BMW",
    "Citroën": "Citroën", "Cupra": "Cupra", "Dacia": "Dacia",
    "Fiat": "Fiat", "Ford": "Ford", "Honda": "Honda",
    "Hyundai": "Hyundai", "Jaguar": "Jaguar", "Jeep": "Jeep",
    "Kia": "Kia", "Land Rover": "Land Rover", "Lexus": "Lexus",
    "Mazda": "Mazda", "Mercedes-Benz": "Mercedes-Benz", "Mini": "Mini",
    "Mitsubishi": "Mitsubishi", "Nissan": "Nissan", "Opel": "Opel",
    "Peugeot": "Peugeot", "Porsche": "Porsche", "Renault": "Renault",
    "SEAT": "SEAT", "Skoda": "Skoda", "Subaru": "Subaru",
    "Suzuki": "Suzuki", "Tesla": "Tesla", "Toyota": "Toyota",
    "Volkswagen": "Volkswagen", "Volvo": "Volvo",
}


class TweedehandsBEScraper(BaseScraper):
    PLATFORM = "tweedehands_be"
    COUNTRY = "BE"
    BASE_DOMAIN = "www.tweedehands.be"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        make_label = _MAKE_MAP.get(make)
        if not make_label:
            return

        offset = ((await self._get_cursor(make, year) or 1) - 1) * _PAGE_SIZE

        while True:
            params = {
                "l1CategoryId": "91",
                "attributesByKey[]": [
                    f"brand:{make_label}",
                    f"constructionYear:{year}",
                ],
                "offset": str(offset),
                "limit": str(_PAGE_SIZE),
                "sortBy": "SORT_INDEX",
                "sortOrder": "DECREASING",
            }
            try:
                data = await self.http.get_json(
                    _API_URL,
                    params=params,
                    headers={"Accept": "application/json", "Accept-Language": "nl-BE"},
                )
            except Exception as exc:
                self.logger.warning("tweedehands_be offset %d: %s", offset, exc)
                break

            listings_data = data.get("listings") or []
            if not listings_data:
                break

            for item in listings_data:
                listing = self._parse(item, make, year)
                if listing:
                    yield listing

            page = (offset // _PAGE_SIZE) + 1
            await self._set_cursor(make, year, page)

            total = data.get("totalResultCount") or 0
            if offset + _PAGE_SIZE >= total or len(listings_data) < _PAGE_SIZE:
                break

            offset += _PAGE_SIZE
            await asyncio.sleep(self._rate_delay())

    def _parse(self, item: dict, make: str, year: int) -> RawListing | None:
        try:
            item_id = str(item.get("itemId", ""))
            price_info = item.get("priceInfo", {})
            price = float(price_info.get("priceCents", 0)) / 100

            attrs = {a.get("key"): a.get("value") for a in item.get("attributes", [])}
            km_raw = attrs.get("mileage") or attrs.get("km")
            mileage = int(str(km_raw).replace(".", "").replace(" km", "")) if km_raw else None

            images = item.get("pictures") or []
            thumb = images[0].get("largeUrl") if images else None

            return RawListing(
                platform=self.PLATFORM,
                country=self.COUNTRY,
                listing_id=item_id,
                source_url=f"https://www.tweedehands.be/auto/{item_id}.html",
                make=make,
                model=attrs.get("model") or item.get("title", "").replace(make, "").strip(),
                year=int(attrs.get("constructionYear") or year),
                price_eur=price if price > 0 else None,
                mileage_km=mileage,
                fuel_type=attrs.get("fuelType") or attrs.get("fuel"),
                city=item.get("location", {}).get("cityName"),
                thumbnail_url=thumb,
                photo_urls=[img.get("largeUrl") for img in images[:8] if img.get("largeUrl")],
                raw=item,
            )
        except Exception:
            return None
