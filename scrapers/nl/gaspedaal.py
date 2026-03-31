"""
Gaspedaal.nl — Netherlands car search aggregator (Autoscout24 Group).
API: JSON search.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper
from scrapers.common.models import RawListing

_API_URL = "https://www.gaspedaal.nl/api/search"
_PAGE_SIZE = 30


class GaspedaalNLScraper(BaseScraper):
    PLATFORM = "gaspedaal_nl"
    COUNTRY = "NL"
    BASE_DOMAIN = "www.gaspedaal.nl"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        page = await self._get_cursor(make, year) or 1

        while True:
            params = {
                "merk": make.lower().replace(" ", "-"),
                "bouwjaar_van": str(year),
                "bouwjaar_tot": str(year),
                "pagina": str(page),
                "aantal": str(_PAGE_SIZE),
            }
            try:
                data = await self.http.get_json(
                    _API_URL, params=params, headers={"Accept": "application/json", "Accept-Language": "nl-NL"},
                )
            except Exception as exc:
                self.logger.warning("gaspedaal page %d: %s", page, exc)
                break

            items = data.get("autos") or data.get("results") or []
            if not items:
                break

            for item in items:
                listing = self._parse(item, make, year)
                if listing:
                    yield listing

            await self._set_cursor(make, year, page)

            total = data.get("totaal") or data.get("total") or 0
            total_pages = (total + _PAGE_SIZE - 1) // _PAGE_SIZE
            if page >= total_pages or len(items) < _PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(self._rate_delay())

    def _parse(self, item: dict, make: str, year: int) -> RawListing | None:
        try:
            vid = str(item.get("id", ""))
            price = float(item.get("prijs") or item.get("price") or 0)
            km = item.get("km") or item.get("kilometerstand")
            mileage = int(str(km).replace(".", "").replace(" km", "")) if km else None

            return RawListing(
                platform=self.PLATFORM, country=self.COUNTRY, listing_id=vid,
                source_url=item.get("url") or f"https://www.gaspedaal.nl/auto/{vid}",
                make=make, model=item.get("model") or "", year=int(item.get("bouwjaar") or year),
                price_eur=price if price > 0 else None, mileage_km=mileage,
                fuel_type=item.get("brandstof"), city=item.get("stad") or item.get("plaats"),
                raw=item,
            )
        except Exception:
            return None
