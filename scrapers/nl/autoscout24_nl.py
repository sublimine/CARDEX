"""
AutoScout24 Netherlands — same AS24 API, country=NL, currency=EUR.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper, ALL_MAKES
from scrapers.common.models import RawListing

_PAGE_SIZE = 20
_SEARCH_URL = (
    "https://www.autoscout24.nl/lst/{make_slug}"
    "?sort=age&desc=0&ustate=N%2CU&size={page_size}&page={page}"
    "&fregfrom={year}&fregto={year}&cy=NL&atype=C"
)

_MAKE_SLUGS: dict[str, str] = {
    "Abarth": "abarth", "Alfa Romeo": "alfa-romeo", "Aston Martin": "aston-martin",
    "Audi": "audi", "Bentley": "bentley", "BMW": "bmw", "Bugatti": "bugatti",
    "Cadillac": "cadillac", "Chevrolet": "chevrolet", "Chrysler": "chrysler",
    "Citroën": "citroen", "Cupra": "cupra", "Dacia": "dacia", "Daewoo": "daewoo",
    "Daihatsu": "daihatsu", "Dodge": "dodge", "Ferrari": "ferrari", "Fiat": "fiat",
    "Ford": "ford", "Honda": "honda", "Hyundai": "hyundai", "Infiniti": "infiniti",
    "Jaguar": "jaguar", "Jeep": "jeep", "Kia": "kia", "Lamborghini": "lamborghini",
    "Land Rover": "land-rover", "Lexus": "lexus", "Maserati": "maserati",
    "Mazda": "mazda", "Mercedes-Benz": "mercedes-benz", "Mini": "mini",
    "Mitsubishi": "mitsubishi", "Nissan": "nissan", "Opel": "opel",
    "Peugeot": "peugeot", "Porsche": "porsche", "Renault": "renault",
    "Rolls-Royce": "rolls-royce", "Saab": "saab", "SEAT": "seat",
    "Skoda": "skoda", "Smart": "smart", "SsangYong": "ssangyong",
    "Subaru": "subaru", "Suzuki": "suzuki", "Tesla": "tesla", "Toyota": "toyota",
    "Volkswagen": "volkswagen", "Volvo": "volvo",
}


class AutoScout24NLScraper(BaseScraper):
    PLATFORM = "autoscout24_nl"
    COUNTRY = "NL"
    BASE_DOMAIN = "www.autoscout24.nl"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        make_slug = _MAKE_SLUGS.get(make)
        if not make_slug:
            return

        page = await self._get_cursor(make, year) or 1

        while True:
            url = _SEARCH_URL.format(make_slug=make_slug, page_size=_PAGE_SIZE, page=page, year=year)
            try:
                data = await self.http.get_json(url, headers={
                    "Accept": "application/json",
                    "Accept-Language": "nl-NL,nl;q=0.9",
                })
            except Exception as exc:
                self.logger.warning("autoscout24_nl page %d: %s", page, exc)
                break

            articles = data.get("articles") or data.get("listItems") or []
            if not articles:
                break

            for article in articles:
                listing = self._parse(article, make, year)
                if listing:
                    yield listing

            await self._set_cursor(make, year, page)

            total_pages = data.get("totalPageCount") or data.get("pageCount") or 1
            if page >= total_pages or len(articles) < _PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(self._rate_delay())

    def _parse(self, article: dict, make: str, year: int) -> RawListing | None:
        try:
            listing_id = str(article.get("id", ""))
            price_info = article.get("price") or article.get("prices", {}).get("public") or {}
            price = float(price_info.get("value") or price_info.get("amount") or price_info or 0)

            km = article.get("mileage") or article.get("km")
            mileage = int(str(km).replace(".", "").replace(" km", "")) if km else None

            images = article.get("images") or article.get("pictures") or []
            thumb = images[0].get("url") if images and isinstance(images[0], dict) else None
            photo_urls = [img.get("url") for img in images[:8] if isinstance(img, dict) and img.get("url")]

            return RawListing(
                platform=self.PLATFORM, country=self.COUNTRY,
                listing_id=listing_id,
                source_url=article.get("url") or f"https://www.autoscout24.nl/auto/{listing_id}",
                make=make, model=article.get("model") or article.get("modelVersionInput") or "",
                year=int(article.get("firstRegistrationYear") or year),
                price_eur=price if price > 0 else None, mileage_km=mileage,
                fuel_type=article.get("fuel"), body_type=article.get("bodyType"),
                city=article.get("location", {}).get("city"),
                seller_name=article.get("vendor", {}).get("name"),
                thumbnail_url=thumb, photo_urls=photo_urls, raw=article,
            )
        except Exception:
            return None
