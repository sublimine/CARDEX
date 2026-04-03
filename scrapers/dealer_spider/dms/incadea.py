"""
Incadea / CDK Global DMS adapter — dominant in DE, AT, CH, NL.
CDK Global (formerly Reynolds & Reynolds / Incadea) powers official branded
dealer sites for VW Group, BMW Group, Mercedes-Benz, and independents.
Inventory feed paths are standardized across all CDK-powered sites.
"""
from __future__ import annotations

from typing import AsyncGenerator

from scrapers.common.models import RawListing

_CHF_TO_EUR = 0.94

_FEED_PATHS = [
    "/api/fahrzeuge",
    "/api/v1/fahrzeuge",
    "/api/inventory",
    "/api/v1/inventory",
    "/api/vehicles",
    "/fahrzeuge.json",
    "/inventory.json",
    "/api/stock",
    "/api/gebrauchtwagen",
    "/incadea/api/stock",
    "/cdk/api/vehicles",
]


async def extract(
    http,
    dealer_id: str,
    dealer_name: str,
    base_url: str,
    country: str,
) -> AsyncGenerator[RawListing, None]:
    base = base_url.rstrip("/")

    for path in _FEED_PATHS:
        url = base + path
        try:
            data = await http.get_json(url, headers={
                "Accept": "application/json",
                "Accept-Language": "de-DE",
            })
        except Exception:
            continue

        vehicles = (
            data.get("fahrzeuge")
            or data.get("vehicles")
            or data.get("inventory")
            or data.get("stock")
            or (data if isinstance(data, list) else [])
        )
        if not vehicles:
            continue

        for v in vehicles:
            listing = _parse(v, dealer_id, dealer_name, base_url, country)
            if listing:
                yield listing
        return


def _parse(v: dict, dealer_id: str, dealer_name: str, base_url: str, country: str) -> RawListing | None:
    try:
        vid = str(v.get("id") or v.get("fahrzeugId") or v.get("vehicleId") or v.get("artikelNr", ""))
        if not vid:
            return None

        price_raw = v.get("preis") or v.get("price") or v.get("verkaufspreis") or 0
        price = float(price_raw)
        if country == "CH" and price > 0:
            price = round(price * _CHF_TO_EUR, 2)

        km_raw = v.get("kilometerstand") or v.get("mileage") or v.get("km")
        mileage = int(str(km_raw).replace(".", "").replace(" km", "")) if km_raw else None

        make = (v.get("marke") or v.get("make") or v.get("hersteller") or "").strip()
        model = (v.get("modell") or v.get("model") or v.get("fahrzeugtyp") or "").strip()
        year_raw = v.get("baujahr") or v.get("erstzulassung") or v.get("year")
        year = int(str(year_raw)[:4]) if year_raw else None

        fuel = v.get("kraftstoff") or v.get("kraftstoffart") or v.get("fuelType") or v.get("fuel")
        vin = v.get("vin") or v.get("fahrgestellnummer") or v.get("VIN")
        color = v.get("farbe") or v.get("aussenfarbe") or v.get("color")
        body = v.get("aufbau") or v.get("karosserie") or v.get("bodyType")

        bilder = v.get("bilder") or v.get("images") or v.get("fotos") or []
        thumb = None
        photo_urls = []
        for b in bilder:
            url = b if isinstance(b, str) else (b.get("url") or b.get("src") or "")
            if url:
                if not thumb:
                    thumb = url
                photo_urls.append(url)

        detail_rel = v.get("url") or v.get("detailUrl") or f"/fahrzeuge/{vid}"
        source_url = detail_rel if detail_rel.startswith("http") else base_url.rstrip("/") + "/" + detail_rel.lstrip("/")

        return RawListing(
            platform=f"dealer_web:{dealer_id}",
            country=country,
            listing_id=f"incadea:{dealer_id}:{vid}",
            source_url=source_url,
            make=make, model=model, year=year,
            price_eur=price if price > 0 else None,
            mileage_km=mileage,
            fuel_type=fuel, body_type=body, color=color, vin=vin,
            thumbnail_url=thumb, photo_urls=photo_urls[:10],
            seller_name=dealer_name, raw=v,
        )
    except Exception:
        return None
