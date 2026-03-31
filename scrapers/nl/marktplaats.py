"""
Marktplaats.nl Netherlands — EXHAUSTIVE scraper.
Netherlands' dominant classifieds platform (eBay Classifieds Group).

Marktplaats exposes a JSON API:
  GET https://www.marktplaats.nl/lrp/api/search
  Params: l1CategoryId=91 (Auto's), attributesByKey[]=brand:BMW, attributesByKey[]=constructionYear:2020,
          limit=100, offset=N

Decomposed by brand × year. Exhaustive pagination.
"""
from __future__ import annotations

from typing import AsyncGenerator

from ..common.base_scraper import BaseScraper
from ..common.models import RawListing
from ..common.normalizer import (
    normalize_fuel,
    normalize_transmission,
    parse_power_kw,
)

_PAGE_SIZE = 100  # marktplaats supports up to 100/page
_API_URL = (
    "https://www.marktplaats.nl/lrp/api/search"
    "?l1CategoryId=91"
    "&attributesByKey[]=brand:{make}"
    "&attributesByKey[]=constructionYear:{year}"
    "&sortBy=SORT_INDEX"
    "&sortOrder=DECREASING"
    "&limit={page_size}&offset={offset}"
)


class Marktplaats(BaseScraper):
    platform = "marktplaats"
    country = "NL"
    domain = "marktplaats.nl"
    use_playwright = False

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        cursor = await self.get_shard_cursor(make, year)
        new_cursor: str | None = None
        offset = 0

        while True:
            url = _API_URL.format(make=make, year=year, page_size=_PAGE_SIZE, offset=offset)
            try:
                data = await self.http.get_json(
                    url,
                    headers={
                        "Accept": "application/json",
                        "Accept-Language": "nl-NL,nl;q=0.9",
                        "Referer": "https://www.marktplaats.nl/",
                    },
                )
            except Exception as e:
                self.log.warning("marktplaats.fetch_error", url=url, make=make, year=year, error=str(e))
                break

            items = data.get("listings") or data.get("items") or []
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

            total = data.get("totalResultCount") or data.get("total") or 0
            offset += _PAGE_SIZE
            if offset >= total or len(items) < _PAGE_SIZE:
                break

        if new_cursor:
            await self.save_shard_cursor(make, year, new_cursor)

    def _map(self, item: dict) -> RawListing | None:
        try:
            listing_id = str(item.get("itemId") or item.get("id", ""))
            if not listing_id:
                return None

            url = item.get("vipUrl") or item.get("url") or ""
            if not url.startswith("http"):
                url = f"https://www.marktplaats.nl{url}"

            attrs = {a.get("key", ""): a.get("value", "") for a in (item.get("attributes") or [])}
            price_info = item.get("priceInfo") or {}
            price_raw = price_info.get("priceCents")
            price_eur = float(price_raw) / 100 if price_raw else None

            media = item.get("pictures") or item.get("media") or []
            photos = []
            for m in media:
                if isinstance(m, dict):
                    url_extra = m.get("extraExtraLargeUrl") or m.get("largeUrl") or m.get("mediumUrl") or ""
                    if url_extra:
                        photos.append(url_extra)

            location = item.get("location") or {}

            return RawListing(
                source_platform=self.platform,
                source_country=self.country,
                source_url=url,
                source_listing_id=listing_id,
                make=attrs.get("brand") or item.get("brand"),
                model=attrs.get("model") or item.get("model"),
                year=int(attrs["constructionYear"]) if attrs.get("constructionYear") else None,
                mileage_km=int(attrs["mileage"].replace(".", "").replace(",", "")) if attrs.get("mileage") else None,
                fuel_type=normalize_fuel(attrs.get("fuel")),
                transmission=normalize_transmission(attrs.get("transmission")),
                color=attrs.get("bodyColor") or attrs.get("color"),
                power_kw=parse_power_kw(attrs.get("power")),
                price_raw=price_eur,
                currency_raw="EUR",
                city=location.get("cityName") or location.get("city"),
                region=location.get("countryName"),
                country="NL",
                seller_type="DEALER" if item.get("sellerType", "").upper() == "BUSINESS" else "PRIVATE",
                seller_name=(item.get("sellerInformation") or {}).get("displayName"),
                photo_urls=photos[:20],
                thumbnail_url=photos[0] if photos else None,
                listing_status="ACTIVE",
                description_snippet=(item.get("description") or "")[:300],
            )
        except Exception as e:
            self.log.warning("marktplaats.map_error", error=str(e), item_id=item.get("itemId"))
            return None


async def run() -> None:
    await Marktplaats().run()
