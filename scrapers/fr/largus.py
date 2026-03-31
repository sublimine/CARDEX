"""
L'Argus — France's historic car valuation authority + classifieds.
API: JSON search for annonces occasion.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper
from scrapers.common.models import RawListing

_API_URL = "https://www.largus.fr/api/v1/annonces/search"
_PAGE_SIZE = 30

_MAKE_MAP: dict[str, str] = {
    "Alfa Romeo": "Alfa Romeo", "Audi": "Audi", "BMW": "BMW",
    "Citroën": "Citroën", "Cupra": "Cupra", "Dacia": "Dacia",
    "Fiat": "Fiat", "Ford": "Ford", "Honda": "Honda",
    "Hyundai": "Hyundai", "Jaguar": "Jaguar", "Jeep": "Jeep",
    "Kia": "Kia", "Land Rover": "Land Rover", "Lexus": "Lexus",
    "Maserati": "Maserati", "Mazda": "Mazda", "Mercedes-Benz": "Mercedes-Benz",
    "Mini": "Mini", "Mitsubishi": "Mitsubishi", "Nissan": "Nissan",
    "Opel": "Opel", "Peugeot": "Peugeot", "Porsche": "Porsche",
    "Renault": "Renault", "SEAT": "Seat", "Skoda": "Skoda",
    "Smart": "Smart", "Subaru": "Subaru", "Suzuki": "Suzuki",
    "Tesla": "Tesla", "Toyota": "Toyota", "Volkswagen": "Volkswagen",
    "Volvo": "Volvo",
}


class LargusFRScraper(BaseScraper):
    PLATFORM = "largus_fr"
    COUNTRY = "FR"
    BASE_DOMAIN = "www.largus.fr"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        make_label = _MAKE_MAP.get(make)
        if not make_label:
            return

        page = await self._get_cursor(make, year) or 1

        while True:
            params = {
                "marque": make_label,
                "anneeMin": str(year),
                "anneeMax": str(year),
                "page": str(page),
                "nbResultats": str(_PAGE_SIZE),
                "tri": "datePublication",
            }
            try:
                data = await self.http.get_json(
                    _API_URL, params=params,
                    headers={"Accept": "application/json", "Accept-Language": "fr-FR"},
                )
            except Exception as exc:
                self.logger.warning("largus_fr page %d: %s", page, exc)
                break

            ads = data.get("annonces") or data.get("results") or []
            if not ads:
                break

            for ad in ads:
                listing = self._parse(ad, make, year)
                if listing:
                    yield listing

            await self._set_cursor(make, year, page)

            total = data.get("nbTotal") or data.get("total") or 0
            total_pages = (total + _PAGE_SIZE - 1) // _PAGE_SIZE
            if page >= total_pages or len(ads) < _PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(self._rate_delay())

    def _parse(self, ad: dict, make: str, year: int) -> RawListing | None:
        try:
            aid = str(ad.get("id") or ad.get("reference", ""))
            price = float(ad.get("prix") or ad.get("price") or 0)
            km = ad.get("km") or ad.get("kilometrage")
            mileage = int(str(km).replace(" ", "").replace("km", "")) if km else None
            thumb = ad.get("photo") or ad.get("urlImage")

            return RawListing(
                platform=self.PLATFORM, country=self.COUNTRY, listing_id=aid,
                source_url=ad.get("url") or f"https://www.largus.fr/annonce-voiture/{aid}.html",
                make=make, model=ad.get("modele") or ad.get("model") or "",
                year=int(ad.get("annee") or year),
                price_eur=price if price > 0 else None, mileage_km=mileage,
                fuel_type=ad.get("energie") or ad.get("carburant") or ad.get("fuel"),
                city=ad.get("ville") or ad.get("codePostal"),
                region=ad.get("departement"),
                thumbnail_url=thumb, raw=ad,
            )
        except Exception:
            return None
