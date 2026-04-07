"""
Motormanager DMS adapter — dominant in NL and BE (~8,000 dealers).
Motormanager is the leading Dutch dealer SaaS. Their platform exposes
a standardized XML or JSON feed at known paths.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import AsyncGenerator

from scrapers.common.models import RawListing

_FEED_PATHS_JSON = [
    "/api/occasions",
    "/api/v1/occasions",
    "/api/stock",
    "/occasions.json",
    "/api/vehicles",
    "/api/aanbod",
]

_FEED_PATHS_XML = [
    "/api/occasions.xml",
    "/aanbod.xml",
    "/occasions.xml",
    "/stock.xml",
    "/motormanager/feed.xml",
]


async def extract(
    http,
    dealer_id: str,
    dealer_name: str,
    base_url: str,
    country: str,
) -> AsyncGenerator[RawListing, None]:
    base = base_url.rstrip("/")

    # Try JSON feeds first
    for path in _FEED_PATHS_JSON:
        url = base + path
        try:
            data = await http.get_json(url, headers={
                "Accept": "application/json",
                "Accept-Language": "nl-NL",
            })
        except Exception:
            continue

        vehicles = (
            data.get("occasions")
            or data.get("aanbod")
            or data.get("vehicles")
            or data.get("stock")
            or (data if isinstance(data, list) else [])
        )
        if not vehicles:
            continue

        for v in vehicles:
            listing = _parse_json(v, dealer_id, dealer_name, base_url, country)
            if listing:
                yield listing
        return

    # Try XML feeds
    for path in _FEED_PATHS_XML:
        url = base + path
        try:
            xml_text = await http.get_text(url)
            root = ET.fromstring(xml_text)
        except Exception:
            continue

        for vehicle_el in root.iter("vehicle"):
            listing = _parse_xml(vehicle_el, dealer_id, dealer_name, base_url, country)
            if listing:
                yield listing
        return


def _parse_json(v: dict, dealer_id: str, dealer_name: str, base_url: str, country: str) -> RawListing | None:
    try:
        vid = str(v.get("id") or v.get("occasionId") or v.get("voertuigId", ""))
        if not vid:
            return None

        price = float(v.get("prijs") or v.get("price") or v.get("verkoopprijs") or 0)
        km_raw = v.get("kilometerstand") or v.get("km") or v.get("mileage")
        mileage = int(str(km_raw).replace(".", "").replace(" km", "")) if km_raw else None

        make = (v.get("merk") or v.get("make") or "").strip()
        model = (v.get("model") or v.get("uitvoering") or "").strip()
        year_raw = v.get("bouwjaar") or v.get("jaar") or v.get("year")
        year = int(str(year_raw)[:4]) if year_raw else None

        fuel = v.get("brandstof") or v.get("fuel") or v.get("fuelType")
        vin = v.get("vin") or v.get("chassisnummer")
        color = v.get("kleur") or v.get("buitenkleur") or v.get("color")

        images = v.get("afbeeldingen") or v.get("fotos") or v.get("images") or []
        thumb = None
        photo_urls = []
        for img in images:
            url = img if isinstance(img, str) else (img.get("url") or img.get("src") or "")
            if url:
                if not thumb:
                    thumb = url
                photo_urls.append(url)

        from urllib.parse import urljoin as _urljoin
        detail_rel = v.get("url") or v.get("detailpagina") or f"/occasion/{vid}"
        source_url = detail_rel if detail_rel.startswith("http") else _urljoin(base_url.rstrip("/") + "/", detail_rel)

        return RawListing(
            platform=f"dealer_web:{dealer_id}",
            country=country,
            listing_id=f"motormanager:{dealer_id}:{vid}",
            source_url=source_url,
            make=make, model=model, year=year,
            price_eur=price if price > 0 else None,
            mileage_km=mileage,
            fuel_type=fuel, color=color, vin=vin,
            thumbnail_url=thumb, photo_urls=photo_urls[:10],
            seller_name=dealer_name, raw=v,
        )
    except Exception:
        return None


def _parse_xml(el: ET.Element, dealer_id: str, dealer_name: str, base_url: str, country: str) -> RawListing | None:
    def t(tag: str) -> str:
        node = el.find(tag)
        return node.text.strip() if node is not None and node.text else ""

    try:
        vid = t("id") or t("vehicleId")
        if not vid:
            return None

        price_s = t("price") or t("prijs")
        price = float(price_s.replace(",", ".")) if price_s else None
        km_s = t("mileage") or t("km") or t("kilometerstand")
        mileage = int(km_s.replace(".", "")) if km_s else None

        make = t("make") or t("merk")
        model = t("model")
        year_s = t("year") or t("bouwjaar")
        year = int(year_s[:4]) if year_s else None

        from urllib.parse import urljoin as _urljoin
        detail_url = t("url") or t("link") or t("detailUrl")
        source_url = _urljoin(base_url.rstrip("/") + "/", detail_url) if detail_url else None
        if not source_url:
            source_url = _urljoin(base_url.rstrip("/") + "/", f"/occasion/{vid}")

        return RawListing(
            platform=f"dealer_web:{dealer_id}",
            country=country,
            listing_id=f"motormanager:{dealer_id}:{vid}",
            source_url=source_url,
            make=make, model=model, year=year,
            price_eur=price,
            mileage_km=mileage,
            fuel_type=t("fuel") or t("brandstof"),
            vin=t("vin"),
            color=t("color") or t("kleur"),
            seller_name=dealer_name,
            raw={"_xml_id": vid},
        )
    except Exception:
        return None
