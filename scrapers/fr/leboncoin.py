"""
leboncoin.fr France — EXHAUSTIVE scraper.
France's largest classifieds platform (Adevinta). Massive private seller base.

leboncoin has a public JSON search API:
  POST https://api.leboncoin.fr/api/adfinder/v1/search
  with JSON body including filters for category (2 = Voitures), make/model, year, price.

Decomposed by brand × year. Exhaustive pagination.
"""
from __future__ import annotations

import json
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

_PAGE_SIZE = 35
_API_URL = "https://api.leboncoin.fr/api/adfinder/v1/search"


def _build_body(make: str, year: int, page: int) -> dict:
    return {
        "limit": _PAGE_SIZE,
        "offset": (page - 1) * _PAGE_SIZE,
        "filters": {
            "category": {"id": "2"},  # Voitures
            "enums": {
                "u_car_brand": [make],
                "regdate": [str(year)],
            },
            "ranges": {},
            "keywords": {},
            "location": {},
        },
        "sort_by": "time",
        "sort_order": "desc",
        "pivot": "",
    }


class LeBonCoin(BaseScraper):
    platform = "leboncoin"
    country = "FR"
    domain = "api.leboncoin.fr"
    use_playwright = False

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        cursor = await self.get_shard_cursor(make, year)
        new_cursor: str | None = None
        page = 1

        while True:
            body = _build_body(make, year, page)
            try:
                resp = await self.http._client.post(
                    _API_URL,
                    content=json.dumps(body).encode(),
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "api_key": "ba0c2dad52b3585c9c4b529781058dbc",  # public key, same as browser
                        "Referer": "https://www.leboncoin.fr/",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                self.log.warning("leboncoin.fetch_error", make=make, year=year, page=page, error=str(e))
                break

            items = data.get("ads") or []
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

            total = data.get("total") or data.get("ranges_total") or 0
            if page * _PAGE_SIZE >= total or len(items) < _PAGE_SIZE:
                break
            page += 1

        if new_cursor:
            await self.save_shard_cursor(make, year, new_cursor)

    def _map(self, item: dict) -> RawListing | None:
        try:
            listing_id = str(item.get("list_id") or item.get("ad_id", ""))
            if not listing_id:
                return None

            url = item.get("url") or f"https://www.leboncoin.fr/voitures/{listing_id}.htm"
            attrs = {a["key"]: a.get("value") or (a.get("values") or [None])[0]
                     for a in (item.get("attributes") or [])}

            price_raw = None
            price_info = item.get("price") or []
            if isinstance(price_info, list) and price_info:
                price_raw = float(price_info[0])
            elif isinstance(price_info, (int, float)):
                price_raw = float(price_info)

            images = item.get("images") or {}
            thumb = images.get("thumb_url") or images.get("small_url") or ""
            urls = images.get("urls_large") or images.get("urls") or []

            location = item.get("location") or {}

            return RawListing(
                source_platform=self.platform,
                source_country=self.country,
                source_url=url,
                source_listing_id=listing_id,
                make=attrs.get("u_car_brand") or item.get("brand"),
                model=attrs.get("u_car_model") or item.get("model"),
                year=int(attrs["regdate"]) if attrs.get("regdate") else None,
                mileage_km=int(attrs["mileage"]) if attrs.get("mileage") else None,
                fuel_type=normalize_fuel(attrs.get("fuel")),
                transmission=normalize_transmission(attrs.get("gearbox")),
                color=attrs.get("car_color"),
                power_kw=parse_power_kw(str(attrs.get("horse_power_din", "")) + " CV"),
                price_raw=price_raw,
                currency_raw="EUR",
                city=location.get("city") or location.get("city_label"),
                region=location.get("region_label"),
                country="FR",
                seller_type="DEALER" if item.get("owner", {}).get("type") == "pro" else "PRIVATE",
                seller_name=(item.get("owner") or {}).get("name"),
                photo_urls=urls[:20],
                thumbnail_url=thumb or (urls[0] if urls else None),
                listing_status="ACTIVE",
                description_snippet=(item.get("body") or "")[:300],
            )
        except Exception as e:
            self.log.warning("leboncoin.map_error", error=str(e), item_id=item.get("list_id"))
            return None


async def run() -> None:
    await LeBonCoin().run()
