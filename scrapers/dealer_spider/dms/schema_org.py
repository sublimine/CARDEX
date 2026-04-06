"""
Schema.org JSON-LD extractor — used when the dealer website embeds
structured data using the schema.org/Car (or schema.org/Vehicle) vocabulary.

Parses all <script type="application/ld+json"> blocks from the homepage HTML
and any linked inventory page. Falls back to probing common inventory paths
to find pages that contain Car JSON-LD.

JSON-LD field mapping (schema.org → RawListing):
  name / brand.name    → make
  model                → model
  vehicleModelDate     → year
  mileageFromOdometer  → mileage_km
  offers.price         → price_raw
  vehicleIdentificationNumber → vin
  color / vehicleInteriorColor → color
  fuelType             → fuel_type
  url                  → source_url
  image / image[0]     → thumbnail_url
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import AsyncGenerator

from scrapers.common.models import RawListing
from scrapers.dealer_spider.dms.generic_feed import _parse_price, _parse_km

# Paths to probe for inventory pages that may embed JSON-LD
_PROBE_PATHS = [
    "/stock", "/inventory", "/vehicles", "/cars", "/used-cars",
    "/coches", "/fahrzeuge", "/voitures", "/occasion", "/gebrauchtwagen",
    "/tweedehands", "/occasions", "/gamas/ocasion",
]

_SCHEMA_TYPES = {
    "car", "vehicle", "automobile", "usedcar", "usedvehicle",
    "offeritemcondition", "product",
}


def _extract_jsonld_blocks(html: str) -> list[dict]:
    """Extract all JSON-LD objects from <script type="application/ld+json"> tags."""
    results = []
    # Match all JSON-LD script blocks
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.IGNORECASE | re.DOTALL,
    ):
        raw = m.group(1).strip()
        try:
            obj = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            # Try stripping BOM or leading noise
            try:
                obj = json.loads(raw.lstrip("\ufeff"))
            except Exception:
                continue

        if isinstance(obj, list):
            results.extend(obj)
        elif isinstance(obj, dict):
            # Unwrap @graph arrays
            if "@graph" in obj and isinstance(obj["@graph"], list):
                results.extend(obj["@graph"])
            else:
                results.append(obj)
    return results


def _is_vehicle(obj: dict) -> bool:
    """Return True if a JSON-LD object represents a vehicle."""
    t = obj.get("@type", "")
    if isinstance(t, list):
        t = " ".join(t)
    return any(v in t.lower() for v in _SCHEMA_TYPES)


def _str(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, dict):
        # schema.org often nests: {"@type": "QuantitativeValue", "value": 123}
        v = v.get("value") or v.get("name") or v.get("@value") or ""
    s = str(v).strip()
    return s if s else None


def _extract_make(obj: dict) -> str:
    # schema.org uses brand.name or manufacturer.name
    brand = obj.get("brand") or obj.get("manufacturer") or {}
    if isinstance(brand, dict):
        name = brand.get("name") or ""
    else:
        name = str(brand)
    return name.strip() or _str(obj.get("make")) or ""


def _extract_price(obj: dict, country: str) -> float | None:
    offers = obj.get("offers") or obj.get("Offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if isinstance(offers, dict):
        price = offers.get("price") or offers.get("lowPrice")
        currency = offers.get("priceCurrency", "EUR")
        if price is not None:
            # Use CHF→EUR conversion if needed
            raw_country = "CH" if (currency or "").upper() == "CHF" else country
            return _parse_price(price, raw_country)
    # Fallback: direct price field
    return _parse_price(obj.get("price"), country)


def _extract_mileage(obj: dict) -> int | None:
    mileage = obj.get("mileageFromOdometer") or obj.get("mileage")
    if isinstance(mileage, dict):
        value = mileage.get("value")
        unit = (mileage.get("unitCode") or mileage.get("unitText") or "KMT").upper()
        if value is None:
            return None
        km = _parse_km(value)
        if km and "SMI" in unit:  # statute miles → km
            km = int(km * 1.60934)
        return km
    return _parse_km(mileage)


def _extract_year(obj: dict) -> int | None:
    y = obj.get("vehicleModelDate") or obj.get("dateVehicleFirstRegistered") or obj.get("productionDate")
    if not y:
        return None
    s = str(y)[:4]
    return int(s) if s.isdigit() else None


def _extract_url(obj: dict, base_url: str) -> str:
    url = obj.get("url") or obj.get("@id") or ""
    if url and url.startswith("http"):
        return url
    if url and url.startswith("/"):
        return base_url.rstrip("/") + url
    return base_url


def _extract_images(obj: dict) -> tuple[str | None, list[str]]:
    img = obj.get("image") or obj.get("photo")
    urls = []
    if isinstance(img, list):
        for item in img[:10]:
            if isinstance(item, str) and item.startswith("http"):
                urls.append(item)
            elif isinstance(item, dict):
                u = item.get("url") or item.get("contentUrl") or ""
                if u.startswith("http"):
                    urls.append(u)
    elif isinstance(img, str) and img.startswith("http"):
        urls = [img]
    elif isinstance(img, dict):
        u = img.get("url") or img.get("contentUrl") or ""
        if u.startswith("http"):
            urls = [u]
    return (urls[0] if urls else None), urls


def _vehicle_from_jsonld(
    obj: dict,
    dealer_id: str,
    dealer_name: str,
    base_url: str,
    country: str,
) -> RawListing | None:
    try:
        # Derive a stable ID: prefer VIN, then @id/url fragment, then product ID
        vin = _str(obj.get("vehicleIdentificationNumber") or obj.get("vin"))
        vid = (
            vin
            or _str(obj.get("productID") or obj.get("sku") or obj.get("identifier"))
        )
        # Try URL-based ID
        if not vid:
            url_str = obj.get("url") or obj.get("@id") or ""
            if url_str:
                # Extract last meaningful path segment
                segments = [s for s in url_str.rstrip("/").split("/") if s and len(s) > 1]
                if segments:
                    vid = segments[-1]
        # Last resort: generate from name + model (stable per listing)
        if not vid or len(vid) < 2:
            name_str = obj.get("name") or ""
            model_str = _str(obj.get("model")) or ""
            if name_str or model_str:
                import hashlib
                vid = hashlib.md5(f"{name_str}:{model_str}:{obj.get('offers',{}).get('price','')}".encode()).hexdigest()[:12]
        if not vid or len(vid) < 2:
            return None

        make = _extract_make(obj)
        model_raw = _str(obj.get("model")) or obj.get("name", "") or ""
        # Clean model: strip make prefix if present (e.g. "SEAT Altea XL" → "Altea XL")
        model = model_raw
        if make and model.upper().startswith(make.upper()):
            model = model[len(make):].strip()
        # Strip trailing trim/engine info in parentheses: "Altea XL 1.6 TDI (105 CV)" → "Altea XL"
        # Keep the model name, remove engine spec
        if not model and make:
            # name field might have "Seat Altea XL" — use it
            name_val = obj.get("name", "")
            if name_val and make and name_val.upper().startswith(make.upper()):
                model = name_val[len(make):].strip()
        year = _extract_year(obj)
        price = _extract_price(obj, country)
        mileage = _extract_mileage(obj)
        color = _str(obj.get("color") or obj.get("vehicleInteriorColor"))
        fuel = _str(obj.get("fuelType"))
        source_url = _extract_url(obj, base_url)
        thumb, photos = _extract_images(obj)

        return RawListing(
            source_platform=f"dealer_web:{dealer_id}",
            source_country=country,
            source_listing_id=f"jsonld:{dealer_id}:{vid}",
            source_url=source_url,
            make=make, model=model, year=year,
            price_raw=price, mileage_km=mileage,
            fuel_type=None,  # normalizer maps
            color=color, vin=vin,
            thumbnail_url=thumb, photo_urls=photos,
            seller_name=dealer_name,
            seller_type="DEALER",
        )
    except Exception:
        return None


async def extract(
    http,
    dealer_id: str,
    dealer_name: str,
    base_url: str,
    country: str,
) -> AsyncGenerator[RawListing, None]:
    """
    Main entry point: fetch homepage HTML (and optionally inventory pages),
    extract all Car/Vehicle JSON-LD objects, yield RawListings.
    """
    base = base_url.rstrip("/")
    seen_ids: set[str] = set()

    async def _process_html(html: str) -> list[RawListing]:
        listings = []
        for obj in _extract_jsonld_blocks(html):
            if not _is_vehicle(obj):
                continue
            listing = _vehicle_from_jsonld(obj, dealer_id, dealer_name, base, country)
            if listing and listing.source_listing_id not in seen_ids:
                seen_ids.add(listing.source_listing_id)
                listings.append(listing)
        return listings

    # 1. Try homepage first (some dealers embed all inventory as JSON-LD)
    try:
        html = await http.get_text(base)
        homepage_listings = await _process_html(html)
        if homepage_listings:
            for l in homepage_listings:
                yield l
            return
    except Exception:
        pass

    # 2. Probe common inventory paths
    for path in _PROBE_PATHS:
        try:
            html = await http.get_text(base + path)
            listings = await _process_html(html)
            if listings:
                for l in listings:
                    yield l
                return  # stop after first productive page
        except Exception:
            continue

    # 3. Try sitemap to find vehicle listing URLs
    try:
        sitemap_text = await http.get_text(base + "/sitemap.xml")
        vehicle_urls = _parse_sitemap_vehicle_urls(sitemap_text, base)
        count = 0
        for url in vehicle_urls[:200]:  # cap at 200 detail pages
            try:
                html = await http.get_text(url)
                listings = await _process_html(html)
                for l in listings:
                    yield l
                    count += 1
            except Exception:
                continue
        if count > 0:
            return
    except Exception:
        pass


def _parse_sitemap_vehicle_urls(text: str, base_url: str) -> list[str]:
    """Extract URLs from sitemap.xml that look like vehicle detail pages."""
    urls = []
    vehicle_patterns = re.compile(
        r'(stock|inventory|vehicle|car|auto|fahrzeug|voiture|coche|occasion|'
        r'gebrauchtwagen|tweedehands|usato|usado|veicolo)',
        re.IGNORECASE,
    )
    try:
        root = ET.fromstring(text)
        # Handle both sitemap index and URL set
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        for loc in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
            url = (loc.text or "").strip()
            if url and vehicle_patterns.search(url):
                urls.append(url)
    except ET.ParseError:
        # Try regex fallback
        for m in re.finditer(r'<loc>(.*?)</loc>', text):
            url = m.group(1).strip()
            if vehicle_patterns.search(url):
                urls.append(url)
    return urls
