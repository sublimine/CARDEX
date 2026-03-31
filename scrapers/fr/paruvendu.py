"""
ParuVendu — France general classifieds, strong in used cars.
API: JSON search for category voitures.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper
from scrapers.common.models import RawListing

_API_URL = "https://www.paruvendu.fr/a/voitures-occasions/"
_PAGE_SIZE = 30


class ParuvenduFRScraper(BaseScraper):
    PLATFORM = "paruvendu_fr"
    COUNTRY = "FR"
    BASE_DOMAIN = "www.paruvendu.fr"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        make_slug = make.lower().replace(" ", "-").replace("é", "e").replace("ë", "e")
        page = await self._get_cursor(make, year) or 1

        while True:
            params = {
                "marque": make_slug,
                "anneeMin": str(year),
                "anneeMax": str(year),
                "p": str(page),
                "nbResultParPage": str(_PAGE_SIZE),
                "typeAnnonce": "P",
            }
            try:
                data = await self.http.get_json(
                    _API_URL,
                    params=params,
                    headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
                )
            except Exception as exc:
                self.logger.warning("paruvendu page %d: %s", page, exc)
                break

            items = data.get("annonces") or data.get("results") or []
            if not items:
                break

            for item in items:
                listing = self._parse(item, make, year)
                if listing:
                    yield listing

            await self._set_cursor(make, year, page)

            total = data.get("nbTotal") or data.get("total") or 0
            total_pages = (total + _PAGE_SIZE - 1) // _PAGE_SIZE
            if page >= total_pages or len(items) < _PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(self._rate_delay())

    def _parse(self, item: dict, make: str, year: int) -> RawListing | None:
        try:
            aid = str(item.get("id") or item.get("noAnnonce", ""))
            price = float(item.get("prix") or item.get("price") or 0)
            km = item.get("km") or item.get("kilometrage")
            mileage = int(str(km).replace(" ", "").replace("km", "")) if km else None
            thumb = item.get("photo") or item.get("urlPhoto")

            return RawListing(
                platform=self.PLATFORM, country=self.COUNTRY, listing_id=aid,
                source_url=item.get("url") or f"https://www.paruvendu.fr/a/voitures-occasions/{aid}",
                make=make, model=item.get("modele") or item.get("model") or "",
                year=int(item.get("annee") or year),
                price_eur=price if price > 0 else None, mileage_km=mileage,
                fuel_type=item.get("carburant") or item.get("fuel"),
                city=item.get("ville") or item.get("cp"), thumbnail_url=thumb, raw=item,
            )
        except Exception:
            return None
