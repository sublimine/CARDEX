"""
Autentia/Izmo DMS adapter — dominant in Spain (~15,000 dealer sites).
Autentia powers the majority of Spanish dealer websites via their
"MotorStock" SaaS platform. Inventory is accessible via:
  GET /api/v1/vehiculos or /api/vehiculos.json
  GET /motorstock/api/stock

Also covers Izmo (rebranded Autentia for international market).
"""
from __future__ import annotations

from typing import AsyncGenerator

from scrapers.common.models import RawListing

_FEED_PATHS = [
    "/api/v1/vehiculos",
    "/api/vehiculos.json",
    "/api/vehiculos",
    "/motorstock/api/stock",
    "/api/stock/vehiculos",
    "/api/v2/vehiculos",
    "/izmo/api/stock",
    "/coches.json",
    "/api/coches",
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
                "Accept-Language": "es-ES",
            })
        except Exception:
            continue

        vehicles = (
            data.get("vehiculos")
            or data.get("coches")
            or data.get("stock")
            or data.get("vehicles")
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
        vid = str(v.get("id") or v.get("idVehiculo") or v.get("referencia") or v.get("ref", ""))
        if not vid:
            return None

        price = float(v.get("precio") or v.get("price") or v.get("pvp") or 0)

        km_raw = v.get("km") or v.get("kilometros") or v.get("kilometraje") or v.get("mileage")
        mileage = int(str(km_raw).replace(".", "").replace(" km", "")) if km_raw else None

        make = (v.get("marca") or v.get("make") or "").strip()
        model = (v.get("modelo") or v.get("model") or v.get("version") or "").strip()
        year_raw = v.get("anio") or v.get("año") or v.get("year") or v.get("matriculacion")
        year = int(str(year_raw)[:4]) if year_raw else None

        fuel = v.get("combustible") or v.get("carburante") or v.get("fuel")
        vin = v.get("vin") or v.get("bastidor") or v.get("VIN")
        color = v.get("color") or v.get("colorExterior")

        fotos = v.get("fotos") or v.get("imagenes") or v.get("images") or v.get("photos") or []
        thumb = None
        photo_urls = []
        for f in fotos:
            url = f if isinstance(f, str) else (f.get("url") or f.get("src") or "")
            if url:
                if not thumb:
                    thumb = url
                photo_urls.append(url)

        from urllib.parse import urljoin as _urljoin
        detail_rel = v.get("url") or v.get("urlDetalle") or f"/ficha/{vid}"
        source_url = detail_rel if detail_rel.startswith("http") else _urljoin(base_url.rstrip("/") + "/", detail_rel)

        return RawListing(
            platform=f"dealer_web:{dealer_id}",
            country=country,
            listing_id=f"autentia:{dealer_id}:{vid}",
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
