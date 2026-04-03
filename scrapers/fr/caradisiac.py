"""
Caradisiac — France's leading automotive media + occasion listings.
API: JSON search for annonces occasion.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper
from scrapers.common.models import RawListing

_API_URL = "https://www.caradisiac.com/api/occasion/search"
_PAGE_SIZE = 24


class CaradisiacFRScraper(BaseScraper):
    PLATFORM = "caradisiac_fr"
    COUNTRY = "FR"
    BASE_DOMAIN = "www.caradisiac.com"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        page = await self._get_cursor(make, year) or 1

        while True:
            params = {
                "marque": make.lower().replace(" ", "-").replace("é", "e"),
                "anneeMin": str(year),
                "anneeMax": str(year),
                "page": str(page),
                "limit": str(_PAGE_SIZE),
                "order": "date_desc",
            }
            try:
                data = await self.http.get_json(
                    _API_URL, params=params,
                    headers={"Accept": "application/json", "Accept-Language": "fr-FR"},
                )
            except Exception as exc:
                self.logger.warning("caradisiac page %d: %s", page, exc)
                break

            ads = data.get("annonces") or data.get("listings") or data.get("results") or []
            if not ads:
                break

            for ad in ads:
                listing = self._parse(ad, make, year)
                if listing:
                    yield listing

            await self._set_cursor(make, year, page)

            total = data.get("total") or data.get("nbTotal") or 0
            total_pages = (total + _PAGE_SIZE - 1) // _PAGE_SIZE
            if page >= total_pages or len(ads) < _PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(self._rate_delay())

    def _parse(self, ad: dict, make: str, year: int) -> RawListing | None:
        try:
            aid = str(ad.get("id") or ad.get("ref", ""))
            price = float(ad.get("prix") or ad.get("price") or 0)
            km = ad.get("km") or ad.get("kilometrage")
            mileage = int(str(km).replace(" ", "").replace("km", "")) if km else None
            images = ad.get("photos") or ad.get("images") or []
            thumb = images[0] if images and isinstance(images[0], str) else (
                images[0].get("url") if images else None
            )

            return RawListing(
                platform=self.PLATFORM, country=self.COUNTRY, listing_id=aid,
                source_url=ad.get("url") or f"https://www.caradisiac.com/occasion/{aid}",
                make=make, model=ad.get("modele") or ad.get("model") or "",
                year=int(ad.get("annee") or year),
                price_eur=price if price > 0 else None, mileage_km=mileage,
                fuel_type=ad.get("carburant") or ad.get("fuel"),
                city=ad.get("ville") or ad.get("departement"),
                thumbnail_url=thumb if isinstance(thumb, str) else None,
                raw=ad,
            )
        except Exception:
            return None
