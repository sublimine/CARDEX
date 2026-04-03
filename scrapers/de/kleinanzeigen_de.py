"""
Kleinanzeigen (formerly eBay Kleinanzeigen) — Germany's largest C2C classifieds.
API: JSON search endpoint with category 216 (Autos).
Exhaustive crawl via make × year shards.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper, ALL_MAKES
from scrapers.common.models import RawListing

_SEARCH_URL = (
    "https://www.kleinanzeigen.de/s-autos/anzeige:angebote"
    "/seite:{page}/c216+autos.marke_s:{make_slug}+autos.ez_i:{year}"
)

_PAGE_SIZE = 25  # Kleinanzeigen shows 25 results per page

_MAKE_SLUG_MAP: dict[str, str] = {
    "Abarth": "abarth", "Alfa Romeo": "alfa_romeo", "Aston Martin": "aston_martin",
    "Audi": "audi", "Bentley": "bentley", "BMW": "bmw", "Bugatti": "bugatti",
    "Cadillac": "cadillac", "Chevrolet": "chevrolet", "Chrysler": "chrysler",
    "Citroën": "citroen", "Cupra": "cupra", "Dacia": "dacia", "Daewoo": "daewoo",
    "Daihatsu": "daihatsu", "Dodge": "dodge", "Ferrari": "ferrari", "Fiat": "fiat",
    "Ford": "ford", "Honda": "honda", "Hyundai": "hyundai", "Infiniti": "infiniti",
    "Jaguar": "jaguar", "Jeep": "jeep", "Kia": "kia", "Lamborghini": "lamborghini",
    "Land Rover": "land_rover", "Lexus": "lexus", "Maserati": "maserati",
    "Mazda": "mazda", "Mercedes-Benz": "mercedes_benz", "Mini": "mini",
    "Mitsubishi": "mitsubishi", "Nissan": "nissan", "Opel": "opel",
    "Peugeot": "peugeot", "Porsche": "porsche", "Renault": "renault",
    "Rolls-Royce": "rolls_royce", "Saab": "saab", "SEAT": "seat",
    "Skoda": "skoda", "Smart": "smart", "SsangYong": "ssangyong",
    "Subaru": "subaru", "Suzuki": "suzuki", "Tesla": "tesla", "Toyota": "toyota",
    "Volkswagen": "volkswagen", "Volvo": "volvo",
}


class KleinanzeigenDEScraper(BaseScraper):
    PLATFORM = "kleinanzeigen_de"
    COUNTRY = "DE"
    BASE_DOMAIN = "www.kleinanzeigen.de"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        make_slug = _MAKE_SLUG_MAP.get(make)
        if not make_slug:
            return

        page = await self._get_cursor(make, year)
        if page is None:
            page = 1

        while True:
            url = _SEARCH_URL.format(make_slug=make_slug, year=year, page=page)
            try:
                data = await self.http.get_json(url, headers={
                    "Accept": "application/json, text/html",
                    "Accept-Language": "de-DE,de;q=0.9",
                })
            except Exception as exc:
                self.logger.warning("kleinanzeigen_de page %d failed: %s", page, exc)
                break

            ads = data.get("ads") or data.get("items") or []
            if not ads:
                break

            for ad in ads:
                listing = self._parse_ad(ad, make, year)
                if listing:
                    yield listing

            await self._set_cursor(make, year, page)

            total = data.get("numResultsTotal", 0)
            total_pages = (total + _PAGE_SIZE - 1) // _PAGE_SIZE
            if page >= total_pages or len(ads) < _PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(self._rate_delay())

    def _parse_ad(self, ad: dict, make: str, year: int) -> RawListing | None:
        try:
            ad_id = str(ad.get("id", ""))
            title = ad.get("title", "")
            price_raw = ad.get("price", {})
            price = None
            if isinstance(price_raw, dict):
                amount = price_raw.get("amount")
                if amount:
                    price = float(str(amount).replace(".", "").replace(",", "."))
            elif isinstance(price_raw, (int, float)):
                price = float(price_raw)

            attrs = {a.get("name"): a.get("values", [None])[0]
                     for a in ad.get("attributes", [])}

            mileage = None
            raw_km = attrs.get("milage") or attrs.get("mileage")
            if raw_km:
                mileage = int(str(raw_km).replace(".", "").replace(",", "").replace(" km", ""))

            fuel = attrs.get("fuel")
            location = ad.get("location", {})
            city = location.get("city", "")

            images = ad.get("pictures", []) or ad.get("images", [])
            thumb = images[0].get("url") if images else None

            return RawListing(
                platform=self.PLATFORM,
                country=self.COUNTRY,
                listing_id=ad_id,
                source_url=f"https://www.kleinanzeigen.de/s-anzeige/{ad_id}",
                make=make,
                model=self._extract_model(title, make),
                year=year,
                price_eur=price,
                mileage_km=mileage,
                fuel_type=fuel,
                city=city,
                thumbnail_url=thumb,
                photo_urls=[img.get("url") for img in images[:8] if img.get("url")],
                seller_name=ad.get("userInfo", {}).get("displayName"),
                raw=ad,
            )
        except Exception:
            return None

    @staticmethod
    def _extract_model(title: str, make: str) -> str:
        title_lower = title.lower()
        make_lower = make.lower()
        idx = title_lower.find(make_lower)
        if idx >= 0:
            rest = title[idx + len(make):].strip()
            return rest.split()[0] if rest else ""
        return title.split()[0] if title else ""
