"""
Generic JSON/XML feed adapter — used when DMSDetector finds a direct feed URL
but the platform doesn't match a named DMS.

Probes a prioritised list of common feed paths and accepts the first one
that returns a non-empty array of vehicle-like objects. Field names are
normalised via heuristic key matching against ~40 common variants.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import AsyncGenerator

from scrapers.common.models import RawListing

_CHF_TO_EUR = 0.94

_FEED_PATHS = [
    "/api/stock.json", "/api/vehicles.json", "/api/inventory.json",
    "/inventory.json", "/stock.json", "/vehicles.json",
    "/coches.json", "/fahrzeuge.json", "/voitures.json",
    "/api/cars.json", "/api/v1/vehicles", "/api/v2/vehicles",
    "/feed/vehicles", "/vehicle-feed.xml", "/sitemap-vehicles.xml",
    "/inventory.xml", "/stock.xml",
]

# Heuristic field resolution: first matching key wins
_MAKE_KEYS   = ["make","brand","marca","marque","marke","merk","hersteller","fabricant"]
_MODEL_KEYS  = ["model","modele","modell","modelo","uitvoering","version","variante"]
_YEAR_KEYS   = ["year","annee","baujahr","bouwjaar","ano","año","matriculacion","firstRegistrationYear","registrationYear"]
_PRICE_KEYS  = ["price","prix","preis","prijs","precio","pvp","sale_price","consumerPrice","askingPrice","verkoopprijs","verkaufspreis"]
_MILEAGE_KEYS= ["mileage","km","kilometres","kilometrage","kilometerstand","kilometerstand","mileageInKm","mileageKm","kilometers"]
_FUEL_KEYS   = ["fuel","fuelType","carburant","kraftstoff","brandstof","combustible","energie","energy"]
_VIN_KEYS    = ["vin","VIN","fahrgestellnummer","bastidor","chassisnummer","chasis"]
_COLOR_KEYS  = ["color","colour","couleur","farbe","kleur","aussenfarbe","colorExterior","buitenkleur"]
_URL_KEYS    = ["url","link","detailUrl","detailpagina","fichaUrl","permalink"]
_ID_KEYS     = ["id","vehicleId","adId","ref","reference","insertionsId","occasionId","carId","stockId","vehicleIdentifier"]
_THUMB_KEYS  = ["thumbnail","thumb","mainImage","primaryImage","urlFoto","hauptbild"]
_IMAGES_KEYS = ["images","photos","pictures","fotos","bilder","imagenes","afbeeldingen","photos_urls"]


def _pick(d: dict, keys: list[str]) -> str | None:
    for k in keys:
        v = d.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def _parse_km(raw) -> int | None:
    if raw is None:
        return None
    s = str(raw).replace("\xa0", "").replace(" ", "").replace("km", "")
    # Handle both European (1.234) and US (1,234) thousand separators
    if "," in s and "." in s:
        # e.g. "1,234.56" → remove comma → 1234.56
        s = s.replace(",", "")
    elif "," in s and s.index(",") < len(s) - 4:
        # comma as thousands: "1,234" → "1234"
        s = s.replace(",", "")
    elif "." in s and s.index(".") < len(s) - 4:
        # dot as thousands: "1.234" → "1234"
        s = s.replace(".", "")
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _parse_price(raw, country: str) -> float | None:
    if raw is None:
        return None
    try:
        price = float(str(raw).replace(",", "").replace(".", "").replace(" ", "")
                      .replace("€", "").replace("CHF", "").replace("£", ""))
        # Re-parse properly: strip non-numeric except dot/comma
        import re
        m = re.search(r"[\d]+[.,]?\d*", str(raw).replace(" ", ""))
        if m:
            price = float(m.group().replace(",", "."))
        if price <= 0 or price > 10_000_000:
            return None
        if country == "CH":
            price = round(price * _CHF_TO_EUR, 2)
        return price
    except Exception:
        return None


def _extract_thumb(item: dict) -> tuple[str | None, list[str]]:
    """Return (thumbnail_url, photo_urls_list)."""
    # Direct thumb field
    thumb_raw = _pick(item, _THUMB_KEYS)
    if thumb_raw and thumb_raw.startswith("http"):
        return thumb_raw, [thumb_raw]

    images_raw = None
    for k in _IMAGES_KEYS:
        if k in item and item[k]:
            images_raw = item[k]
            break

    if not images_raw:
        return None, []

    urls = []
    if isinstance(images_raw, list):
        for img in images_raw[:10]:
            if isinstance(img, str) and img.startswith("http"):
                urls.append(img)
            elif isinstance(img, dict):
                for uk in ("url", "src", "href", "large", "medium", "thumb"):
                    if img.get(uk, "").startswith("http"):
                        urls.append(img[uk])
                        break
    elif isinstance(images_raw, str) and images_raw.startswith("http"):
        urls = [images_raw]

    return (urls[0] if urls else None), urls


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
        is_xml = path.endswith(".xml")
        try:
            if is_xml:
                text = await http.get_text(url)
                async for listing in _parse_xml(text, dealer_id, dealer_name, base_url, country):
                    yield listing
                return
            else:
                data = await http.get_json(url, headers={"Accept": "application/json"})
        except Exception:
            continue

        vehicles = (
            data if isinstance(data, list) else
            data.get("vehicles") or data.get("stock") or data.get("cars") or
            data.get("inventory") or data.get("items") or data.get("results") or
            data.get("data") or []
        )
        if not vehicles:
            continue

        for v in vehicles:
            listing = _parse_json(v, dealer_id, dealer_name, base_url, country)
            if listing:
                yield listing
        return  # stop after first successful feed


def _parse_json(v: dict, dealer_id: str, dealer_name: str, base_url: str, country: str) -> RawListing | None:
    try:
        vid = _pick(v, _ID_KEYS)
        if not vid:
            return None

        make  = _pick(v, _MAKE_KEYS) or ""
        model = _pick(v, _MODEL_KEYS) or ""
        year_s = _pick(v, _YEAR_KEYS)
        year = int(str(year_s)[:4]) if year_s and str(year_s)[:4].isdigit() else None

        price = _parse_price(_pick(v, _PRICE_KEYS), country)
        mileage = _parse_km(_pick(v, _MILEAGE_KEYS))
        fuel  = _pick(v, _FUEL_KEYS)
        vin   = _pick(v, _VIN_KEYS)
        color = _pick(v, _COLOR_KEYS)

        detail_rel = _pick(v, _URL_KEYS) or f"/{vid}"
        source_url = detail_rel if detail_rel.startswith("http") else base_url.rstrip("/") + "/" + detail_rel.lstrip("/")

        thumb, photos = _extract_thumb(v)

        return RawListing(
            source_platform=f"dealer_web:{dealer_id}",
            source_country=country,
            source_listing_id=f"feed:{dealer_id}:{vid}",
            source_url=source_url,
            make=make, model=model, year=year,
            price_raw=price, mileage_km=mileage,
            fuel_type=None,  # normalizer maps string later
            color=color, vin=vin,
            thumbnail_url=thumb, photo_urls=photos,
            seller_name=dealer_name,
            seller_type="DEALER",
        )
    except Exception:
        return None


async def _parse_xml(text: str, dealer_id: str, dealer_name: str, base_url: str, country: str):
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return

    for el in root.iter():
        if el.tag.lower() in ("vehicle", "car", "auto", "item", "listing", "ad", "fahrzeug", "voiture"):
            def t(tags):
                for tag in tags:
                    node = el.find(tag)
                    if node is not None and node.text and node.text.strip():
                        return node.text.strip()
                return None

            vid = t(["id", "vehicleId", "ref", "reference"])
            if not vid:
                continue

            make  = t(["make", "brand", "marque", "marke"]) or ""
            model = t(["model", "modele", "modell"]) or ""
            year_s = t(["year", "annee", "baujahr", "bouwjaar"])
            year = int(year_s[:4]) if year_s and year_s[:4].isdigit() else None
            price = _parse_price(t(["price", "prix", "preis"]), country)
            mileage = _parse_km(t(["mileage", "km", "kilometerstand"]))
            vin   = t(["vin", "VIN"])
            thumb = t(["image", "photo", "thumbnail", "picture"])

            yield RawListing(
                source_platform=f"dealer_web:{dealer_id}",
                source_country=country,
                source_listing_id=f"xml:{dealer_id}:{vid}",
                source_url=base_url,
                make=make, model=model, year=year,
                price_raw=price, mileage_km=mileage,
                vin=vin, thumbnail_url=thumb,
                seller_name=dealer_name,
                seller_type="DEALER",
            )
