"""
mobile.de Germany — EXHAUSTIVE scraper.

Query decomposition: make × year
  Iterates ALL pages per (make, year) until platform returns empty page.
  No artificial page cap.

mobile.de search API returns JSON when Accept: application/json is sent.
Supports `makeModelVariant[0].makeId` and `firstRegistration.from/to` filters.
"""
from __future__ import annotations

from typing import AsyncGenerator

import structlog

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

log = structlog.get_logger()

_PAGE_SIZE = 50
_SEARCH_URL = (
    "https://suchen.mobile.de/fahrzeuge/search.html"
    "?isSearchRequest=true"
    "&sortOption.sortBy=creationTime"
    "&sortOption.sortOrder=DESCENDING"
    "&pageNumber={page}"
    "&pageSize={page_size}"
    "&minFirstRegistrationDate={year}-01-01"
    "&maxFirstRegistrationDate={year}-12-31"
    "&makeModelVariant1.makeId={make_id}"
    "&damageUnrepaired=WITHOUT_DAMAGE_UNREPAIRED"
)

# mobile.de numeric make IDs (subset — full list fetched dynamically at startup)
# These are the static IDs for common makes. The scraper fetches the full map.
_STATIC_MAKE_IDS: dict[str, str] = {
    "Abarth": "25200", "Alfa Romeo": "1900", "Audi": "1900",
    "BMW": "3500", "Chevrolet": "3600", "Chrysler": "3700",
    "Citroën": "3800", "Cupra": "25100", "Dacia": "4000",
    "DS": "25000", "Fiat": "5200", "Ford": "5400",
    "Honda": "6200", "Hyundai": "6400", "Infiniti": "6500",
    "Jaguar": "7000", "Jeep": "7100", "Kia": "7300",
    "Lada": "7500", "Land Rover": "7700", "Lexus": "7900",
    "Maserati": "8400", "Mazda": "8500", "Mercedes-Benz": "8600",
    "MG": "23600", "MINI": "15900", "Mitsubishi": "9000",
    "Nissan": "9400", "Opel": "9600", "Peugeot": "10000",
    "Porsche": "10300", "Renault": "10400", "Saab": "10600",
    "SEAT": "10700", "Skoda": "10900", "Smart": "11000",
    "SsangYong": "11100", "Subaru": "11200", "Suzuki": "11300",
    "Tesla": "24100", "Toyota": "11600", "Volkswagen": "12300",
    "Volvo": "12500", "BYD": "25300", "Polestar": "25500",
}


class MobileDe(BaseScraper):
    platform = "mobile_de"
    country = "DE"
    domain = "suchen.mobile.de"
    use_playwright = False
    _make_id_map: dict[str, str] = {}

    async def _ensure_make_ids(self) -> None:
        """Fetch complete make list from mobile.de API (runs once at startup)."""
        if self._make_id_map:
            return
        # Start with static map; fetch dynamic map for full coverage
        self._make_id_map = dict(_STATIC_MAKE_IDS)
        try:
            data = await self.http.get_json(
                "https://suchen.mobile.de/fahrzeuge/search.html?isSearchRequest=true&makeModelVariant1.makeId=",
                headers={"Accept": "application/json", "Accept-Language": "de-DE"},
            )
            for make_entry in (data.get("makes") or []):
                make_id = str(make_entry.get("id") or make_entry.get("makeId", ""))
                make_name = make_entry.get("name") or make_entry.get("makeName", "")
                if make_id and make_name:
                    self._make_id_map[make_name] = make_id
        except Exception:
            pass  # use static map

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        await self._ensure_make_ids()
        make_id = self._make_id_map.get(make)
        if not make_id:
            return

        cursor = await self.get_shard_cursor(make, year)
        new_cursor: str | None = None
        page = 1

        while True:
            url = _SEARCH_URL.format(
                page=page,
                page_size=_PAGE_SIZE,
                year=year,
                make_id=make_id,
            )
            try:
                data = await self.http.get_json(
                    url,
                    headers={
                        "Accept": "application/json",
                        "Accept-Language": "de-DE,de;q=0.9",
                        "Referer": "https://suchen.mobile.de/",
                    },
                )
            except Exception as e:
                self.log.warning("mobile_de.fetch_error", url=url, make=make, year=year, error=str(e))
                break

            items = data.get("items") or data.get("results") or []
            if not items:
                break

            cursor_hit = False
            for item in items:
                listing = self._map(item)
                if not listing:
                    continue
                lid = listing.source_listing_id
                if new_cursor is None:
                    new_cursor = lid
                if cursor and lid == cursor:
                    cursor_hit = True
                    break
                yield listing

            if cursor_hit:
                break

            total_pages = (
                data.get("totalPages")
                or (data.get("pagination") or {}).get("totalPages", 1)
            )
            if page >= total_pages or len(items) < _PAGE_SIZE:
                break
            page += 1

        if new_cursor:
            await self.save_shard_cursor(make, year, new_cursor)

    def _map(self, item: dict) -> RawListing | None:
        try:
            listing_id = str(item.get("id", ""))
            if not listing_id:
                return None

            url = item.get("relativeUrl") or item.get("url") or ""
            if not url.startswith("http"):
                url = f"https://suchen.mobile.de{url}"

            attrs = item.get("attributes") or {}
            price_info = item.get("price") or {}
            raw_price = price_info.get("amountInEuro") or price_info.get("grossAmount")
            if raw_price is None:
                raw_price = parse_price(str(price_info.get("displayPrice", "")))

            images = item.get("images") or []
            photos = [img.get("uri") or img.get("url", "") for img in images if (img.get("uri") or img.get("url"))]
            location = item.get("location") or (item.get("seller") or {}).get("address") or {}

            return RawListing(
                source_platform=self.platform,
                source_country=self.country,
                source_url=url,
                source_listing_id=listing_id,
                make=item.get("make") or attrs.get("make"),
                model=item.get("model") or attrs.get("model"),
                variant=item.get("modelDescription") or attrs.get("modelDescription"),
                year=item.get("firstRegistrationYear") or attrs.get("firstRegistrationYear"),
                mileage_km=attrs.get("mileageInKm") or parse_mileage(str(attrs.get("mileage", ""))),
                fuel_type=normalize_fuel(attrs.get("fuelType") or attrs.get("fuelTypeText")),
                transmission=normalize_transmission(attrs.get("transmission") or attrs.get("transmissionText")),
                color=attrs.get("color") or attrs.get("colorText"),
                power_kw=parse_power_kw(attrs.get("power")),
                co2_gkm=parse_co2(attrs.get("co2Emission")),
                price_raw=float(raw_price) if raw_price else None,
                currency_raw="EUR",
                city=location.get("city") or location.get("locality"),
                region=location.get("region"),
                country="DE",
                seller_type="DEALER" if (item.get("sellerType") or "").upper() == "DEALER" else "PRIVATE",
                seller_name=(item.get("seller") or {}).get("name"),
                photo_urls=photos[:20],
                thumbnail_url=photos[0] if photos else None,
                listing_status="ACTIVE",
                description_snippet=(item.get("description") or "")[:300],
            )
        except Exception as e:
            self.log.warning("mobile_de.map_error", error=str(e), item_id=item.get("id"))
            return None


async def run() -> None:
    await MobileDe().run()
