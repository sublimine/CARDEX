"""
AutoScout24 Germany — EXHAUSTIVE scraper.

Query decomposition: make × year
  For each (make, year): page through ALL result pages.
  Stop only when page returns 0 results or fewer than page_size (= no more data).
  No artificial page cap → covers EVERY listing on the platform.

AutoScout24 embeds listings in __NEXT_DATA__ SSR JSON.
Sort: age ascending (oldest first within each shard, to detect new additions easily).
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
    "https://www.autoscout24.de/lst/{make_slug}"
    "?sort=age&desc=0&ustate=N%2CU&size={page_size}&page={page}"
    "&fregfrom={year}&fregto={year}"
)
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)

# AutoScout24 make slugs (URL-safe lowercase, special chars stripped)
_MAKE_SLUG_MAP: dict[str, str] = {
    "Alfa Romeo": "alfa-romeo",
    "Aston Martin": "aston-martin",
    "Land Rover": "land-rover",
    "Mercedes-Benz": "mercedes-benz",
    "Rolls-Royce": "rolls-royce",
    "Lynk & Co": "lynk-co",
}


def _make_to_slug(make: str) -> str:
    return _MAKE_SLUG_MAP.get(make, make.lower().replace(" ", "-").replace("&", ""))


class AutoScout24DE(BaseScraper):
    platform = "autoscout24_de"
    country = "DE"
    domain = "autoscout24.de"
    use_playwright = False

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        make_slug = _make_to_slug(make)
        cursor = await self.get_shard_cursor(make, year)
        # cursor stores the last listing ID seen — used for incremental diff
        cursor_hit = False
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
                resp = await self.http.get(url, headers={"Accept-Language": "de-DE,de;q=0.9"})
                html = resp.text
            except Exception as e:
                self.log.warning("autoscout24_de.fetch_error", url=url, make=make, year=year, error=str(e))
                break

            listings, total_pages = self._parse_page(html)

            if not listings:
                break

            for listing in listings:
                lid = listing.source_listing_id
                if new_cursor is None:
                    new_cursor = lid  # first ID of this shard run = newest
                if cursor and lid == cursor:
                    cursor_hit = True
                    break
                yield listing

            if cursor_hit:
                break

            # Advance to next page only if more pages exist
            if page >= total_pages:
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
            pagination = results_data.get("pagination", {})
            total_pages = pagination.get("totalPages", 1)
        except (KeyError, TypeError):
            total_pages = 1

        listings = [r for r in (self._map(a) for a in articles) if r]
        return listings, total_pages

    def _map(self, item: dict) -> RawListing | None:
        try:
            listing_id = str(item.get("id") or item.get("guid", ""))
            if not listing_id:
                return None

            url = item.get("url", "")
            if not url.startswith("http"):
                url = f"https://www.autoscout24.de{url}"

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
                country="DE",
                seller_type="DEALER" if (item.get("seller") or {}).get("type") == "dealer" else "PRIVATE",
                seller_name=(item.get("seller") or {}).get("name"),
                photo_urls=photos[:20],
                thumbnail_url=photos[0] if photos else None,
                listing_status="ACTIVE",
                description_snippet=(item.get("description") or "")[:300],
            )
        except Exception as e:
            self.log.warning("autoscout24_de.map_error", error=str(e), item_id=item.get("id"))
            return None


async def run() -> None:
    await AutoScout24DE().run()
