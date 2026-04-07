"""
Autobiz DMS adapter — used by ~40,000 dealers across FR, BE, ES, IT, PT.
Autobiz provides a white-label stock management SaaS. Dealer sites powered by
Autobiz expose a standardized JSON API at:
  GET /autobiz/stock?format=json
  GET /api/autobiz/vehicles
  GET /stock?ab_format=json

The API returns vehicle objects with standard Autobiz schema.
"""
from __future__ import annotations

from typing import AsyncGenerator
from urllib.parse import urlparse

from scrapers.common.models import RawListing

_CHF_TO_EUR = 0.94

_FEED_PATHS = [
    "/autobiz/stock?format=json",
    "/api/autobiz/vehicles?format=json",
    "/stock?ab_format=json&limit=500",
    "/stock.json",
    "/api/stock?source=autobiz",
]


async def extract(
    http,
    dealer_id: str,
    dealer_name: str,
    base_url: str,
    country: str,
) -> AsyncGenerator[RawListing, None]:
    """Try all known Autobiz feed paths and yield listings."""
    base = base_url.rstrip("/")

    for path in _FEED_PATHS:
        url = base + path
        try:
            data = await http.get_json(url, headers={"Accept": "application/json"})
        except Exception:
            continue

        vehicles = (
            data.get("vehicles")
            or data.get("stock")
            or data.get("cars")
            or data.get("items")
            or (data if isinstance(data, list) else [])
        )

        if not vehicles:
            continue

        for v in vehicles:
            listing = _parse(v, dealer_id, dealer_name, base_url, country)
            if listing:
                yield listing
        return  # stop after first successful path

    # No Autobiz feed found on this site
    return


def _parse(v: dict, dealer_id: str, dealer_name: str, base_url: str, country: str) -> RawListing | None:
    try:
        vid = str(v.get("id") or v.get("vehicleId") or v.get("ref") or v.get("reference", ""))
        if not vid:
            return None

        # Price — Autobiz uses 'price' or 'prix' depending on locale
        price_raw = v.get("price") or v.get("prix") or v.get("prijs") or v.get("preis") or 0
        price = float(price_raw)

        # Convert CHF if needed
        if country == "CH" and price > 0:
            price = round(price * _CHF_TO_EUR, 2)

        km = v.get("mileage") or v.get("km") or v.get("kilometrage") or v.get("kilometerstand") or v.get("kilometerstand")
        mileage = int(str(km).replace(".", "").replace(" ", "").replace("km", "")) if km else None

        make = (v.get("make") or v.get("brand") or v.get("marque") or v.get("marke") or "").strip()
        model = (v.get("model") or v.get("modele") or v.get("modell") or "").strip()
        year_raw = v.get("year") or v.get("annee") or v.get("jahr") or v.get("bouwjaar")
        year = int(str(year_raw)[:4]) if year_raw else None

        fuel = v.get("fuel") or v.get("carburant") or v.get("kraftstoff") or v.get("brandstof")
        vin = v.get("vin") or v.get("VIN")
        color = v.get("color") or v.get("couleur") or v.get("farbe") or v.get("kleur")

        images = v.get("images") or v.get("photos") or v.get("pictures") or []
        thumb = None
        photo_urls = []
        for img in images:
            if isinstance(img, str):
                if not thumb:
                    thumb = img
                photo_urls.append(img)
            elif isinstance(img, dict):
                url = img.get("url") or img.get("src") or img.get("href")
                if url:
                    if not thumb:
                        thumb = url
                    photo_urls.append(url)

        from urllib.parse import urljoin as _urljoin
        detail_path = v.get("url") or v.get("link") or v.get("detailUrl") or f"/stock/{vid}"
        source_url = detail_path if detail_path.startswith("http") else _urljoin(base_url.rstrip("/") + "/", detail_path)

        return RawListing(
            platform=f"dealer_web:{dealer_id}",
            country=country,
            listing_id=f"autobiz:{dealer_id}:{vid}",
            source_url=source_url,
            make=make,
            model=model,
            year=year,
            price_eur=price if price > 0 else None,
            mileage_km=mileage,
            fuel_type=fuel,
            color=color,
            vin=vin,
            thumbnail_url=thumb,
            photo_urls=photo_urls[:10],
            seller_name=dealer_name,
            raw=v,
        )
    except Exception:
        return None
