"""
coches.net Spain — EXHAUSTIVE scraper.
Spain's second-largest car portal (Adevinta group).

coches.net exposes a REST JSON API:
  GET https://ms-mt--api-web.spain.advgo.net/search
  with query params: brand, model, year_from, year_to, num_page, items_per_page

Decomposed by brand × year. Exhaustive pagination.
"""
from __future__ import annotations

from typing import AsyncGenerator

from ..common.base_scraper import BaseScraper
from ..common.models import RawListing
from ..common.normalizer import (
    normalize_fuel,
    normalize_transmission,
    parse_price,
    parse_mileage,
    parse_power_kw,
)

_PAGE_SIZE = 30
_API_URL = (
    "https://ms-mt--api-web.spain.advgo.net/search"
    "?brand={brand}"
    "&year_from={year}&year_to={year}"
    "&num_page={page}&items_per_page={page_size}"
    "&order=date_desc"
)

# coches.net uses its own brand slugs
_BRAND_SLUGS: dict[str, str] = {
    "Abarth": "abarth", "Alfa Romeo": "alfa-romeo", "Audi": "audi",
    "BMW": "bmw", "Chevrolet": "chevrolet", "Citroën": "citroen",
    "Cupra": "cupra", "Dacia": "dacia", "DS": "ds",
    "Fiat": "fiat", "Ford": "ford", "Honda": "honda",
    "Hyundai": "hyundai", "Jaguar": "jaguar", "Jeep": "jeep",
    "Kia": "kia", "Land Rover": "land-rover", "Lexus": "lexus",
    "Maserati": "maserati", "Mazda": "mazda", "Mercedes-Benz": "mercedes-benz",
    "MG": "mg", "MINI": "mini", "Mitsubishi": "mitsubishi",
    "Nissan": "nissan", "Opel": "opel", "Peugeot": "peugeot",
    "Porsche": "porsche", "Renault": "renault", "Seat": "seat",
    "SEAT": "seat", "Skoda": "skoda", "Smart": "smart",
    "SsangYong": "ssangyong", "Subaru": "subaru", "Suzuki": "suzuki",
    "Tesla": "tesla", "Toyota": "toyota", "Volkswagen": "volkswagen",
    "Volvo": "volvo", "BYD": "byd", "Polestar": "polestar",
}


class CochesNet(BaseScraper):
    platform = "coches_net"
    country = "ES"
    domain = "coches.net"
    use_playwright = False

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        brand_slug = _BRAND_SLUGS.get(make)
        if not brand_slug:
            return

        cursor = await self.get_shard_cursor(make, year)
        new_cursor: str | None = None
        page = 1

        while True:
            url = _API_URL.format(brand=brand_slug, year=year, page=page, page_size=_PAGE_SIZE)
            try:
                data = await self.http.get_json(
                    url,
                    headers={"Accept": "application/json", "Referer": "https://www.coches.net/"},
                )
            except Exception as e:
                self.log.warning("coches_net.fetch_error", url=url, make=make, year=year, error=str(e))
                break

            items = data.get("items") or data.get("results") or data.get("ads") or []
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

            total = data.get("total") or data.get("totalCount") or 0
            if page * _PAGE_SIZE >= total or len(items) < _PAGE_SIZE:
                break
            page += 1

        if new_cursor:
            await self.save_shard_cursor(make, year, new_cursor)

    def _map(self, item: dict) -> RawListing | None:
        try:
            listing_id = str(item.get("id") or item.get("adId") or item.get("guid", ""))
            if not listing_id:
                return None

            url = item.get("url") or item.get("link") or ""
            if not url.startswith("http"):
                url = f"https://www.coches.net{url}"

            photos_raw = item.get("images") or item.get("photos") or []
            photos = [
                (p.get("url") or p.get("src") or p) if isinstance(p, dict) else str(p)
                for p in photos_raw
            ]
            photos = [p for p in photos if isinstance(p, str) and p.startswith("http")]

            price_raw = item.get("price") or item.get("priceRaw")
            if isinstance(price_raw, str):
                price_raw = parse_price(price_raw)

            return RawListing(
                source_platform=self.platform,
                source_country=self.country,
                source_url=url,
                source_listing_id=listing_id,
                make=item.get("brand") or item.get("make"),
                model=item.get("model"),
                variant=item.get("version") or item.get("variant"),
                year=item.get("year") or item.get("firstRegistrationYear"),
                mileage_km=item.get("km") or item.get("mileage") or parse_mileage(str(item.get("kms", ""))),
                fuel_type=normalize_fuel(item.get("fuel") or item.get("fuelType")),
                transmission=normalize_transmission(item.get("transmission") or item.get("gearbox")),
                color=item.get("color"),
                power_kw=parse_power_kw(str(item.get("power", "")) + " CV"),
                price_raw=float(price_raw) if price_raw else None,
                currency_raw="EUR",
                city=item.get("province") or item.get("city") or item.get("location"),
                country="ES",
                seller_type="DEALER" if item.get("professional") or item.get("dealer") else "PRIVATE",
                seller_name=item.get("dealerName") or item.get("sellerName"),
                photo_urls=photos[:20],
                thumbnail_url=photos[0] if photos else None,
                listing_status="ACTIVE",
                description_snippet=(item.get("description") or "")[:300],
            )
        except Exception as e:
            self.log.warning("coches_net.map_error", error=str(e), item_id=item.get("id"))
            return None


async def run() -> None:
    await CochesNet().run()
