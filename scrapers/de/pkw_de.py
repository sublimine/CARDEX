"""
Pkw.de — German used car marketplace (Cartelligence group).
API: JSON search with brand + year filters.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper
from scrapers.common.models import RawListing

_API_URL = "https://www.pkw.de/api/search"
_PAGE_SIZE = 20

_MAKE_MAP: dict[str, str] = {
    "Alfa Romeo": "Alfa Romeo", "Audi": "Audi", "BMW": "BMW",
    "Citroën": "Citroën", "Cupra": "Cupra", "Dacia": "Dacia",
    "Ferrari": "Ferrari", "Fiat": "Fiat", "Ford": "Ford",
    "Honda": "Honda", "Hyundai": "Hyundai", "Jaguar": "Jaguar",
    "Jeep": "Jeep", "Kia": "Kia", "Land Rover": "Land Rover",
    "Lexus": "Lexus", "Maserati": "Maserati", "Mazda": "Mazda",
    "Mercedes-Benz": "Mercedes-Benz", "Mini": "MINI", "Mitsubishi": "Mitsubishi",
    "Nissan": "Nissan", "Opel": "Opel", "Peugeot": "Peugeot",
    "Porsche": "Porsche", "Renault": "Renault", "SEAT": "Seat",
    "Skoda": "Skoda", "Smart": "Smart", "Subaru": "Subaru",
    "Suzuki": "Suzuki", "Tesla": "Tesla", "Toyota": "Toyota",
    "Volkswagen": "Volkswagen", "Volvo": "Volvo",
}


class PkwDEScraper(BaseScraper):
    PLATFORM = "pkw_de"
    COUNTRY = "DE"
    BASE_DOMAIN = "www.pkw.de"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        make_label = _MAKE_MAP.get(make)
        if not make_label:
            return

        page = await self._get_cursor(make, year) or 1

        while True:
            params = {
                "marke": make_label,
                "erstZulassungVon": str(year),
                "erstZulassungBis": str(year),
                "seite": str(page),
                "anzahl": str(_PAGE_SIZE),
                "sortierung": "Datum",
            }
            try:
                data = await self.http.get_json(
                    _API_URL, params=params,
                    headers={"Accept": "application/json", "Accept-Language": "de-DE"},
                )
            except Exception as exc:
                self.logger.warning("pkw_de page %d: %s", page, exc)
                break

            items = data.get("fahrzeuge") or data.get("vehicles") or data.get("results") or []
            if not items:
                break

            for item in items:
                listing = self._parse(item, make, year)
                if listing:
                    yield listing

            await self._set_cursor(make, year, page)

            total = data.get("gesamtAnzahl") or data.get("total") or 0
            total_pages = (total + _PAGE_SIZE - 1) // _PAGE_SIZE
            if page >= total_pages or len(items) < _PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(self._rate_delay())

    def _parse(self, item: dict, make: str, year: int) -> RawListing | None:
        try:
            vid = str(item.get("id") or item.get("insertionsId", ""))
            price = float(item.get("preis") or item.get("price") or 0)
            km = item.get("kilometerstand") or item.get("km")
            mileage = int(str(km).replace(".", "").replace(" km", "")) if km else None

            images = item.get("bilder") or item.get("images") or []
            thumb = images[0] if images and isinstance(images[0], str) else (
                images[0].get("url") if images else None
            )

            return RawListing(
                platform=self.PLATFORM, country=self.COUNTRY, listing_id=vid,
                source_url=item.get("url") or f"https://www.pkw.de/fahrzeuge/{vid}",
                make=make, model=item.get("modell") or item.get("model") or "",
                year=int(item.get("erstZulassung") or year),
                price_eur=price if price > 0 else None, mileage_km=mileage,
                fuel_type=item.get("kraftstoff") or item.get("fuel"),
                city=item.get("ort") or item.get("city"),
                thumbnail_url=thumb if isinstance(thumb, str) else None,
                raw=item,
            )
        except Exception:
            return None
