"""
AutoScout24 Belgium — EXHAUSTIVE scraper.
Same __NEXT_DATA__ structure as autoscout24_de. Decomposed by make × year.
Belgium uses EUR. Both FR/NL language listings coexist.
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
    "https://www.autoscout24.be/lst/{make_slug}"
    "?sort=age&desc=0&ustate=N%2CU&size={page_size}&page={page}"
    "&fregfrom={year}&fregto={year}"
)
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_MAKE_SLUG_MAP = {
    "Alfa Romeo": "alfa-romeo", "Aston Martin": "aston-martin",
    "Land Rover": "land-rover", "Mercedes-Benz": "mercedes-benz",
    "Rolls-Royce": "rolls-royce",
}


def _slug(make: str) -> str:
    return _MAKE_SLUG_MAP.get(make, make.lower().replace(" ", "-").replace("&", "").replace("/", "-"))


class AutoScout24BE(BaseScraper):
    platform = "autoscout24_be"
    country = "BE"
    domain = "autoscout24.be"
    use_playwright = False

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        cursor = await self.get_shard_cursor(make, year)
        new_cursor: str | None = None
        page = 1

        while True:
            url = _SEARCH_URL.format(make_slug=_slug(make), page_size=_PAGE_SIZE, page=page, year=year)
            try:
                resp = await self.http.get(url, headers={"Accept-Language": "fr-BE,fr;q=0.9,nl-BE;q=0.8"})
                html = resp.text
            except Exception as e:
                self.log.warning("autoscout24_be.fetch_error", url=url, make=make, year=year, error=str(e))
                break

            m = _NEXT_DATA_RE.search(html)
            if not m:
                break
            try:
                data = json.loads(m.group(1))
                results_data = data["props"]["pageProps"]["listings"]["data"]
                articles = results_data["results"]
                total_pages = results_data.get("pagination", {}).get("totalPages", 1)
            except (json.JSONDecodeError, KeyError, TypeError):
                break

            cursor_hit = False
            for item in articles:
                lid = str(item.get("id") or item.get("guid", ""))
                if not lid:
                    continue
                url_item = item.get("url", "")
                if not url_item.startswith("http"):
                    url_item = f"https://www.autoscout24.be{url_item}"
                vehicle = item.get("vehicle", {}) or {}
                price_info = (item.get("prices") or {}).get("public", {}) or {}
                raw_price = price_info.get("priceRaw") or parse_price(str(price_info.get("priceFormatted", "")))
                photos = [p["url"] for p in (item.get("images") or []) if p.get("url")]

                if new_cursor is None:
                    new_cursor = lid
                if cursor and lid == cursor:
                    cursor_hit = True
                    break

                yield RawListing(
                    source_platform=self.platform, source_country=self.country,
                    source_url=url_item, source_listing_id=lid,
                    make=vehicle.get("make"), model=vehicle.get("model"),
                    variant=vehicle.get("modelVersionInput"),
                    year=vehicle.get("firstRegistrationYear"),
                    mileage_km=vehicle.get("mileageInKm") or parse_mileage(str(vehicle.get("mileage", ""))),
                    fuel_type=normalize_fuel(vehicle.get("fuelTypeText")),
                    transmission=normalize_transmission(vehicle.get("transmissionTypeText")),
                    color=vehicle.get("colorText"),
                    power_kw=parse_power_kw(f"{vehicle['powerInKw']} kW" if vehicle.get("powerInKw") else None),
                    co2_gkm=parse_co2(vehicle.get("co2EmissionsText")),
                    price_raw=float(raw_price) if raw_price else None, currency_raw="EUR",
                    city=(item.get("location") or {}).get("city"),
                    region=(item.get("location") or {}).get("region"), country="BE",
                    seller_type="DEALER" if (item.get("seller") or {}).get("type") == "dealer" else "PRIVATE",
                    seller_name=(item.get("seller") or {}).get("name"),
                    photo_urls=photos[:20], thumbnail_url=photos[0] if photos else None,
                    listing_status="ACTIVE",
                    description_snippet=(item.get("description") or "")[:300],
                )

            if cursor_hit or page >= total_pages:
                break
            page += 1

        if new_cursor:
            await self.save_shard_cursor(make, year, new_cursor)


async def run() -> None:
    await AutoScout24BE().run()
