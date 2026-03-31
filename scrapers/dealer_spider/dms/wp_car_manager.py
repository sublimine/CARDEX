"""
WP Car Manager adapter — extremely common WordPress plugin for small/medium dealers.
~25,000 WordPress dealer sites across Europe use this plugin.
Exposes WP REST API at /wp-json/wp/v2/car with all inventory as posts.
Also handles the related "Car Dealer" and "Vehicle Listings" WP plugins.
"""
from __future__ import annotations

import re
from typing import AsyncGenerator

from scrapers.common.models import RawListing

_REST_PATHS = [
    "/wp-json/wp/v2/car?per_page=100&page={page}",
    "/wp-json/wp/v2/vehicle?per_page=100&page={page}",
    "/wp-json/wp/v2/listing?per_page=100&page={page}",
    "/wp-json/wp/v2/auto?per_page=100&page={page}",
    "/wp-json/wp/v2/voiture?per_page=100&page={page}",
    "/wp-json/wp/v2/fahrzeug?per_page=100&page={page}",
    "/wp-json/car-dealer/v1/cars?per_page=100&page={page}",
    "/wp-json/wpcm/v1/listings?per_page=100&page={page}",
]

_PRICE_RE = re.compile(r"[\d.,]+")


async def extract(
    http,
    dealer_id: str,
    dealer_name: str,
    base_url: str,
    country: str,
) -> AsyncGenerator[RawListing, None]:
    base = base_url.rstrip("/")

    for path_template in _REST_PATHS:
        page = 1
        found_any = False

        while True:
            url = base + path_template.format(page=page)
            try:
                items = await http.get_json(url, headers={"Accept": "application/json"})
            except Exception:
                break

            if not isinstance(items, list) or not items:
                break

            found_any = True
            for item in items:
                listing = _parse(item, dealer_id, dealer_name, base_url, country)
                if listing:
                    yield listing

            if len(items) < 100:
                break
            page += 1

        if found_any:
            return


def _parse(item: dict, dealer_id: str, dealer_name: str, base_url: str, country: str) -> RawListing | None:
    try:
        post_id = str(item.get("id", ""))
        if not post_id:
            return None

        # WP post title as vehicle name
        title = item.get("title", {}).get("rendered", "") if isinstance(item.get("title"), dict) else str(item.get("title", ""))

        # Meta fields (WP Car Manager stores everything in post meta)
        meta = item.get("meta") or item.get("acf") or item.get("car_data") or {}

        def m(keys: list[str]) -> str:
            for k in keys:
                v = meta.get(k)
                if v:
                    return str(v).strip()
            return ""

        price_s = m(["price", "prix", "prijs", "preis", "sale_price", "_price", "car_price"])
        price_match = _PRICE_RE.search(price_s.replace(",", "").replace(".", "")) if price_s else None
        price = float(price_match.group()) if price_match else None

        km_s = m(["mileage", "km", "kilometres", "kilometrage", "kilometerstand", "car_mileage"])
        km_match = _PRICE_RE.search(km_s.replace(".", "")) if km_s else None
        mileage = int(km_match.group()) if km_match else None

        make = m(["make", "marca", "marque", "marke", "merk", "brand", "car_make"])
        model = m(["model", "modelo", "modele", "modell", "car_model"])
        year_s = m(["year", "ano", "annee", "baujahr", "bouwjaar", "car_year"])
        year = int(year_s[:4]) if year_s and year_s[:4].isdigit() else None

        # If make/model not in meta, parse from title
        if not make and title:
            parts = title.split()
            if parts:
                make = parts[0]
            if len(parts) > 1:
                model = parts[1]

        fuel = m(["fuel_type", "fuel", "carburant", "combustible", "kraftstoff", "brandstof"])
        vin = m(["vin", "VIN", "bastidor", "fahrgestellnummer", "chassisnummer"])
        color = m(["color", "colour", "couleur", "farbe", "kleur", "exterior_color"])

        link = item.get("link") or item.get("guid", {}).get("rendered", base_url)
        if isinstance(link, dict):
            link = link.get("rendered", base_url)

        # Featured image
        thumb = None
        embedded = item.get("_embedded") or {}
        wp_media = embedded.get("wp:featuredmedia") or []
        if wp_media and isinstance(wp_media[0], dict):
            media_details = wp_media[0].get("media_details") or {}
            sizes = media_details.get("sizes") or {}
            for size in ("medium_large", "large", "medium", "thumbnail"):
                if sizes.get(size):
                    thumb = sizes[size].get("source_url")
                    break
            if not thumb:
                thumb = wp_media[0].get("source_url")

        return RawListing(
            platform=f"dealer_web:{dealer_id}",
            country=country,
            listing_id=f"wp:{dealer_id}:{post_id}",
            source_url=str(link),
            make=make, model=model, year=year,
            price_eur=price,
            mileage_km=mileage,
            fuel_type=fuel, color=color, vin=vin,
            thumbnail_url=thumb,
            seller_name=dealer_name,
            raw=item,
        )
    except Exception:
        return None
