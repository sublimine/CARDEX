"""
Motor.es — Spain's automotive news + classifieds portal.
API: JSON search for coches de segunda mano.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from scrapers.common.base_scraper import BaseScraper
from scrapers.common.models import RawListing

_API_URL = "https://www.motor.es/api/v1/coches/ocasion/buscar"
_PAGE_SIZE = 20


class MotorESScraper(BaseScraper):
    PLATFORM = "motor_es"
    COUNTRY = "ES"
    BASE_DOMAIN = "www.motor.es"

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        page = await self._get_cursor(make, year) or 1

        while True:
            params = {
                "marca": make.lower().replace(" ", "-"),
                "anio_desde": str(year),
                "anio_hasta": str(year),
                "pagina": str(page),
                "por_pagina": str(_PAGE_SIZE),
                "orden": "fecha_desc",
            }
            try:
                data = await self.http.get_json(
                    _API_URL, params=params,
                    headers={"Accept": "application/json", "Accept-Language": "es-ES"},
                )
            except Exception as exc:
                self.logger.warning("motor_es page %d: %s", page, exc)
                break

            items = data.get("anuncios") or data.get("coches") or data.get("results") or []
            if not items:
                break

            for item in items:
                listing = self._parse(item, make, year)
                if listing:
                    yield listing

            await self._set_cursor(make, year, page)

            total = data.get("total") or data.get("totalResultados") or 0
            total_pages = (total + _PAGE_SIZE - 1) // _PAGE_SIZE
            if page >= total_pages or len(items) < _PAGE_SIZE:
                break

            page += 1
            await asyncio.sleep(self._rate_delay())

    def _parse(self, item: dict, make: str, year: int) -> RawListing | None:
        try:
            aid = str(item.get("id") or item.get("anuncioId", ""))
            price = float(item.get("precio") or item.get("price") or 0)
            km = item.get("km") or item.get("kilometros")
            mileage = int(str(km).replace(".", "").replace(" km", "")) if km else None

            images = item.get("fotos") or item.get("images") or []
            thumb = images[0] if images and isinstance(images[0], str) else (
                images[0].get("url") if images else None
            )

            return RawListing(
                platform=self.PLATFORM, country=self.COUNTRY, listing_id=aid,
                source_url=item.get("url") or f"https://www.motor.es/coches-segunda-mano/{aid}.html",
                make=make, model=item.get("modelo") or item.get("model") or "",
                year=int(item.get("ano") or year),
                price_eur=price if price > 0 else None, mileage_km=mileage,
                fuel_type=item.get("combustible") or item.get("fuel"),
                city=item.get("provincia") or item.get("location"),
                thumbnail_url=thumb if isinstance(thumb, str) else None,
                raw=item,
            )
        except Exception:
            return None
