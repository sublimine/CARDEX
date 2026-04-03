"""
AutoScout24 Spain — EXHAUSTIVE scraper.
Same API shape as autoscout24_de. Decomposed by make × year, no page cap.
"""
from __future__ import annotations

import json
import re
from typing import AsyncGenerator

from ..common.base_scraper import BaseScraper
from ..common.models import RawListing
from ..common.normalizer import (
    normalize_fuel,
    normalize_transmission,
    parse_co2,
    parse_mileage,
    parse_power_kw,
    parse_price,
)

_PAGE_SIZE = 20
_SEARCH_URL = (
    "https://www.autoscout24.es/lst/{make_slug}"
    "?sort=age&desc=0&ustate=N%2CU&size={page_size}&page={page}"
    "&fregfrom={year}&fregto={year}"
)
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)

_MAKE_SLUG_MAP: dict[str, str] = {
    "Alfa Romeo": "alfa-romeo",
    "Aston Martin": "aston-martin",
    "Land Rover": "land-rover",
    "Mercedes-Benz": "mercedes-benz",
    "Rolls-Royce": "rolls-royce",
    "Lynk & Co": "lynk-co",
}


def _make_to_slug(make: str) -> str:
    return _MAKE_SLUG_MAP.get(make, make.lower().replace(" ", "-").replace("&", "").replace("/", "-"))


class AutoScout24ES(BaseScraper):
    platform = "autoscout24_es"
    country = "ES"
    domain = "autoscout24.es"
    use_playwright = False

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        make_slug = _make_to_slug(make)
        cursor = await self.get_shard_cursor(make, year)
        new_cursor: str | None = None
        page = 1

        while True:
            url = _SEARCH_URL.format(
                make_slug=make_slug,
                page_size=_PAGE_SIZE,
                page=page,
                year=year,
            )
            try:
                resp = await self.http.get(url, headers={"Accept-Language": "es-ES,es;q=0.9"})
                html = resp.text
            except Exception as e:
                self.log.warning("autoscout24_es.fetch_error", url=url, make=make, year=year, error=str(e))
                break

            listings, total_pages = self._parse_page(html)
            if not listings:
                break

            cursor_hit = False
            for listing in listings:
                lid = listing.source_listing_id
                if new_cursor is None:
                    new_cursor = lid
                if cursor and lid == cursor:
                    cursor_hit = True
                    break
                yield listing

            if cursor_hit or page >= total_pages:
                break
            page += 1

        if new_cursor:
            await self.save_shard_cursor(make, year, new_cursor)

    def _parse_page(self, html: str) -> tuple[list[RawListing], int]:
        m = _NEXT_DATA_RE.search(html)
        if not m:
            return [], 0
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return [], 0

        try:
            results_data = data["props"]["pageProps"]["listings"]["data"]
            articles = results_data["results"]
        except (KeyError, TypeError):
            return [], 0

        try:
            total_pages = results_data.get("pagination", {}).get("totalPages", 1)
        except (KeyError, TypeError):
            total_pages = 1

        return [r for r in (self._map(a) for a in articles) if r], total_pages

    def _map(self, item: dict) -> RawListing | None:
        try:
            listing_id = str(item.get("id") or item.get("guid", ""))
            if not listing_id:
                return None

            url = item.get("url", "")
            if not url.startswith("http"):
                url = f"https://www.autoscout24.es{url}"

            vehicle = item.get("vehicle", {}) or {}
            price_info = (item.get("prices") or {}).get("public", {}) or {}
            raw_price = price_info.get("priceRaw") or price_info.get("price")
            if raw_price is None:
                raw_price = parse_price(str(price_info.get("priceFormatted", "")))

            photos = [p["url"] for p in (item.get("images") or []) if p.get("url")]

            return RawListing(
                source_platform=self.platform,
                source_country=self.country,
                source_url=url,
                source_listing_id=listing_id,
                make=vehicle.get("make"),
                model=vehicle.get("model"),
                variant=vehicle.get("modelVersionInput"),
                year=vehicle.get("firstRegistrationYear"),
                mileage_km=vehicle.get("mileageInKm") or parse_mileage(str(vehicle.get("mileage", ""))),
                fuel_type=normalize_fuel(vehicle.get("fuelTypeText")),
                transmission=normalize_transmission(vehicle.get("transmissionTypeText")),
                color=vehicle.get("colorText"),
                power_kw=parse_power_kw(f"{vehicle['powerInKw']} kW" if vehicle.get("powerInKw") else None),
                co2_gkm=parse_co2(vehicle.get("co2EmissionsText")),
                price_raw=float(raw_price) if raw_price else None,
                currency_raw="EUR",
                city=(item.get("location") or {}).get("city"),
                region=(item.get("location") or {}).get("region"),
                country="ES",
                seller_type="DEALER" if (item.get("seller") or {}).get("type") == "dealer" else "PRIVATE",
                seller_name=(item.get("seller") or {}).get("name"),
                photo_urls=photos[:20],
                thumbnail_url=photos[0] if photos else None,
                listing_status="ACTIVE",
                description_snippet=(item.get("description") or "")[:300],
            )
        except Exception as e:
            self.log.warning("autoscout24_es.map_error", error=str(e), item_id=item.get("id"))
            return None


async def run() -> None:
    await AutoScout24ES().run()
