"""
La Centrale — France's leading professional car classifieds (Webedia group).
API: JSON search with marque + annee filters.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper
from scrapers.common.models import RawListing

_API_URL = "https://www.lacentrale.fr/api/search"
_PAGE_SIZE = 30

_MAKE_MAP: dict[str, str] = {
    "Alfa Romeo": "ALFA_ROMEO", "Audi": "AUDI", "BMW": "BMW",
    "Citroën": "CITROEN", "Cupra": "CUPRA", "Dacia": "DACIA",
    "Fiat": "FIAT", "Ford": "FORD", "Honda": "HONDA",
    "Hyundai": "HYUNDAI", "Jaguar": "JAGUAR", "Jeep": "JEEP",
    "Kia": "KIA", "Land Rover": "LAND_ROVER", "Lexus": "LEXUS",
    "Maserati": "MASERATI", "Mazda": "MAZDA", "Mercedes-Benz": "MERCEDES",
    "Mini": "MINI", "Mitsubishi": "MITSUBISHI", "Nissan": "NISSAN",
    "Opel": "OPEL", "Peugeot": "PEUGEOT", "Porsche": "PORSCHE",
    "Renault": "RENAULT", "SEAT": "SEAT", "Skoda": "SKODA",
    "Smart": "SMART", "Subaru": "SUBARU", "Suzuki": "SUZUKI",
    "Tesla": "TESLA", "Toyota": "TOYOTA", "Volkswagen": "VW",
    "Volvo": "VOLVO",
}


class LaCentraleFRScraper(BaseScraper):
    PLATFORM = "lacentrale_fr"
    COUNTRY = "FR"
    BASE_DOMAIN = "www.lacentrale.fr"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        make_code = _MAKE_MAP.get(make)
        if not make_code:
            return

        page = await self._get_cursor(make, year) or 1

        while True:
            params = {
                "makesModelsCommercialNames": make_code,
                "yearMin": str(year),
                "yearMax": str(year),
                "page": str(page),
                "pageSize": str(_PAGE_SIZE),
                "sortBy": "datecreaDesc",
            }
            try:
                data = await self.http.get_json(
                    _API_URL,
                    params=params,
                    headers={
                        "Accept": "application/json",
                        "Referer": "https://www.lacentrale.fr/listing",
                    },
                )
            except Exception as exc:
                self.logger.warning("lacentrale page %d: %s", page, exc)
                break

            ads = data.get("ads") or data.get("vehicles") or data.get("results") or []
            if not ads:
                break

            for ad in ads:
                listing = self._parse(ad, make, year)
                if listing:
                    yield listing

            await self._set_cursor(make, year, page)

            total = data.get("totalCount") or data.get("total") or 0
            total_pages = (total + _PAGE_SIZE - 1) // _PAGE_SIZE
            if page >= total_pages or len(ads) < _PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(self._rate_delay())

    def _parse(self, ad: dict, make: str, year: int) -> RawListing | None:
        try:
            ad_id = str(ad.get("id") or ad.get("adId", ""))
            price = float(ad.get("price") or ad.get("priceFAI") or 0)
            km = ad.get("mileage") or ad.get("km")
            mileage = int(str(km).replace(" ", "").replace("km", "")) if km else None

            images = ad.get("photos") or ad.get("images") or []
            thumb = images[0] if images and isinstance(images[0], str) else (
                images[0].get("url") if images else None
            )

            return RawListing(
                platform=self.PLATFORM,
                country=self.COUNTRY,
                listing_id=ad_id,
                source_url=ad.get("url") or f"https://www.lacentrale.fr/auto-occasion-annonce-{ad_id}.html",
                make=make,
                model=ad.get("model") or ad.get("modelLabel") or "",
                year=int(ad.get("year") or year),
                price_eur=price if price > 0 else None,
                mileage_km=mileage,
                fuel_type=ad.get("energy") or ad.get("fuelType"),
                city=ad.get("city") or ad.get("postalCode"),
                region=ad.get("region") or ad.get("department"),
                thumbnail_url=thumb if isinstance(thumb, str) else None,
                seller_name=ad.get("sellerName") or ad.get("dealer", {}).get("name"),
                raw=ad,
            )
        except Exception:
            return None
