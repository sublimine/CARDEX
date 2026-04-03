"""
Tutti.ch — Switzerland's general classifieds (Tamedia group), strong in used cars.
API: JSON search for category 27 (Auto & Motorrad > Autos).
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper
from scrapers.common.models import RawListing

_API_URL = "https://www.tutti.ch/api/v10/ads"
_PAGE_SIZE = 40
_CHF_TO_EUR = 0.94


class TuttiChScraper(BaseScraper):
    PLATFORM = "tutti_ch"
    COUNTRY = "CH"
    BASE_DOMAIN = "www.tutti.ch"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        page = await self._get_cursor(make, year) or 1

        while True:
            params = {
                "category_id": "27",
                "query": f"{make} {year}",
                "page": str(page),
                "page_size": str(_PAGE_SIZE),
                "sort_by": "date_desc",
            }
            try:
                data = await self.http.get_json(
                    _API_URL, params=params,
                    headers={"Accept": "application/json", "Accept-Language": "de-CH"},
                )
            except Exception as exc:
                self.logger.warning("tutti_ch page %d: %s", page, exc)
                break

            ads = data.get("ads") or data.get("results") or []
            if not ads:
                break

            for ad in ads:
                listing = self._parse(ad, make, year)
                if listing:
                    yield listing

            await self._set_cursor(make, year, page)

            total = data.get("total_count") or data.get("total") or 0
            total_pages = (total + _PAGE_SIZE - 1) // _PAGE_SIZE
            if page >= total_pages or len(ads) < _PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(self._rate_delay())

    def _parse(self, ad: dict, make: str, year: int) -> RawListing | None:
        try:
            aid = str(ad.get("id", ""))
            price_chf = float(ad.get("price") or 0)
            price_eur = round(price_chf * _CHF_TO_EUR, 2) if price_chf > 0 else None

            attrs = {a.get("key"): a.get("value") for a in ad.get("attributes", [])}
            km_raw = attrs.get("km") or attrs.get("mileage")
            mileage = int(str(km_raw).replace("'", "").replace(" km", "")) if km_raw else None

            images = ad.get("images") or ad.get("pictures") or []
            thumb = images[0].get("url") if images and isinstance(images[0], dict) else None

            return RawListing(
                platform=self.PLATFORM, country=self.COUNTRY, listing_id=aid,
                source_url=ad.get("url") or f"https://www.tutti.ch/de/vi/{aid}",
                make=make, model=attrs.get("model") or ad.get("title", "").replace(make, "").strip(),
                year=int(attrs.get("year") or year),
                price_eur=price_eur, mileage_km=mileage,
                fuel_type=attrs.get("fuel_type"),
                city=ad.get("location", {}).get("city") if isinstance(ad.get("location"), dict) else None,
                thumbnail_url=thumb, raw=ad,
            )
        except Exception:
            return None
