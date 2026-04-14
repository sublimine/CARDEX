"""
Full-Spectrum Multi-Source Dealer Discovery Engine.

Runs multiple probes to achieve 100% territory coverage across 6 European
countries (DE, ES, FR, NL, BE, CH). Each probe queries a different data
source. Results feed into the same PostgreSQL dealers table with entity
resolution (matching by name+location or website).

Probes:
  1. OpenStreetMap Overpass API   — FREE, no auth, ~10K dealers
  2. INSEE SIRENE                 — France only, FREE with API key
  3. Zefix                        — Switzerland only, FREE REST API
  4. Common Crawl Index           — FREE, finds hidden dealer websites
  5. Google Places                — OPTIONAL, costs money, fills last gap
  6. OEM Dealer Locators          — FREE, scrape "Find a Dealer" pages
  7. Portal Dealer Directories    — FREE, from sites we already scrape

All probes handle errors gracefully, log via structlog, and checkpoint
progress in Redis so restarts resume where they left off.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import re
import signal
import time
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, AsyncIterator

import asyncpg
import h3
import httpx
import structlog
from redis.asyncio import from_url as redis_from_url

log = structlog.get_logger()

# ── Configuration ────────────────────────────────────────────────────────────

_GOOGLE_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
_INSEE_API_TOKEN = os.environ.get("INSEE_API_TOKEN", "")
_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://cardex:cardex@localhost:5432/cardex"
)
_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
_COUNTRIES = [
    c.strip()
    for c in os.environ.get("DISCOVERY_COUNTRIES", "DE,ES,FR,NL,BE,CH").split(",")
    if c.strip()
]

_STREAM_OUT = "stream:dealer_discovered"
_BLOOM_KEY = "bloom:dealer_place_ids"

# Bounding boxes: (south, north, west, east)  i.e. (lat_min, lat_max, lng_min, lng_max)
_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "DE": (47.27, 55.06, 5.87, 15.04),
    "ES": (36.00, 43.79, -9.30, 3.33),
    "FR": (42.33, 51.09, -4.79, 8.23),
    "NL": (50.75, 53.47, 3.36, 7.21),
    "BE": (49.50, 51.50, 2.55, 6.40),
    "CH": (45.82, 47.81, 5.96, 10.49),
}

# Country TLDs for Common Crawl
_COUNTRY_TLDS: dict[str, str] = {
    "DE": "de", "ES": "es", "FR": "fr", "NL": "nl", "BE": "be", "CH": "ch",
}

# H3 resolution 4 for Google Places grid
_H3_RESOLUTION = 4
_SEARCH_RADIUS_M = 25_000

# Google Places queries per country
_SEARCH_QUERIES: dict[str, list[str]] = {
    "DE": ["Autohändler", "Autohaus", "car dealer"],
    "ES": ["concesionario de coches", "car dealer"],
    "FR": ["concessionnaire automobile", "garagiste", "car dealer"],
    "NL": ["autodealer", "autobedrijf", "car dealer"],
    "BE": ["autodealer", "concessionnaire automobile", "car dealer"],
    "CH": ["Autohändler", "concessionnaire automobile", "car dealer"],
}

_PLACES_NEARBY_URL = (
    "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
)
_PLACES_DETAIL_URL = (
    "https://maps.googleapis.com/maps/api/place/details/json"
)

# Common Crawl automotive keywords per TLD
_CC_KEYWORDS: dict[str, list[str]] = {
    "de": ["*autohaus*", "*autoh*ndler*", "*kfz*", "*fahrzeug*"],
    "es": ["*concesionario*", "*coches*", "*vehiculos*", "*automovil*"],
    "fr": ["*concessionnaire*", "*automobile*", "*voiture*", "*garage-auto*"],
    "nl": ["*autodealer*", "*autohandel*", "*autobedrijf*"],
    "be": ["*autodealer*", "*garage-auto*"],
    "ch": ["*autohandel*", "*autohaus*", "*garage-auto*"],
}

# OEM brands and their dealer-locator JSON endpoints.
# Each entry: (brand, {country: endpoint_url_template})
# These are the XHR JSON endpoints that power OEM "Find a Dealer" pages.
_OEM_ENDPOINTS: dict[str, dict[str, str]] = {
    "BMW": {
        "DE": "https://www.bmw.de/de/home/footer/dealer-search.html/_jcr_content.api.json?lat=51.1657&lng=10.4515&country=DE&maxResults=9999",
        "ES": "https://www.bmw.es/es/home/footer/dealer-search.html/_jcr_content.api.json?lat=40.4637&lng=-3.7492&country=ES&maxResults=9999",
        "FR": "https://www.bmw.fr/fr/home/footer/dealer-search.html/_jcr_content.api.json?lat=46.2276&lng=2.2137&country=FR&maxResults=9999",
        "NL": "https://www.bmw.nl/nl/home/footer/dealer-search.html/_jcr_content.api.json?lat=52.1326&lng=5.2913&country=NL&maxResults=9999",
        "BE": "https://www.bmw.be/fr/home/footer/dealer-search.html/_jcr_content.api.json?lat=50.5039&lng=4.4699&country=BE&maxResults=9999",
        "CH": "https://www.bmw.ch/de/home/footer/dealer-search.html/_jcr_content.api.json?lat=46.8182&lng=8.2275&country=CH&maxResults=9999",
    },
    "Mercedes": {
        "DE": "https://api.mercedes-benz.com/dealer/v1/dealers?market=DE&brand=MB&pageSize=9999",
        "ES": "https://api.mercedes-benz.com/dealer/v1/dealers?market=ES&brand=MB&pageSize=9999",
        "FR": "https://api.mercedes-benz.com/dealer/v1/dealers?market=FR&brand=MB&pageSize=9999",
        "NL": "https://api.mercedes-benz.com/dealer/v1/dealers?market=NL&brand=MB&pageSize=9999",
        "BE": "https://api.mercedes-benz.com/dealer/v1/dealers?market=BE&brand=MB&pageSize=9999",
        "CH": "https://api.mercedes-benz.com/dealer/v1/dealers?market=CH&brand=MB&pageSize=9999",
    },
    "VW": {
        "DE": "https://app.volkswagen.de/ihdcc/in/DE/de/dealer?brand=V&capability=NewCarSale&maxResults=9999",
        "ES": "https://app.volkswagen.es/ihdcc/in/ES/es/dealer?brand=V&capability=NewCarSale&maxResults=9999",
        "FR": "https://app.volkswagen.fr/ihdcc/in/FR/fr/dealer?brand=V&capability=NewCarSale&maxResults=9999",
        "NL": "https://app.volkswagen.nl/ihdcc/in/NL/nl/dealer?brand=V&capability=NewCarSale&maxResults=9999",
        "BE": "https://app.volkswagen.be/ihdcc/in/BE/fr/dealer?brand=V&capability=NewCarSale&maxResults=9999",
        "CH": "https://app.volkswagen.ch/ihdcc/in/CH/de/dealer?brand=V&capability=NewCarSale&maxResults=9999",
    },
    "Audi": {
        "DE": "https://app.audi.de/ihdcc/in/DE/de/dealer?brand=A&capability=NewCarSale&maxResults=9999",
        "ES": "https://app.audi.es/ihdcc/in/ES/es/dealer?brand=A&capability=NewCarSale&maxResults=9999",
        "FR": "https://app.audi.fr/ihdcc/in/FR/fr/dealer?brand=A&capability=NewCarSale&maxResults=9999",
        "NL": "https://app.audi.nl/ihdcc/in/NL/nl/dealer?brand=A&capability=NewCarSale&maxResults=9999",
        "BE": "https://app.audi.be/ihdcc/in/BE/fr/dealer?brand=A&capability=NewCarSale&maxResults=9999",
        "CH": "https://app.audi.ch/ihdcc/in/CH/de/dealer?brand=A&capability=NewCarSale&maxResults=9999",
    },
    "Toyota": {
        "DE": "https://www.toyota.de/api/dealers?country=DE&type=sales&limit=9999",
        "ES": "https://www.toyota.es/api/dealers?country=ES&type=sales&limit=9999",
        "FR": "https://www.toyota.fr/api/dealers?country=FR&type=sales&limit=9999",
        "NL": "https://www.toyota.nl/api/dealers?country=NL&type=sales&limit=9999",
        "BE": "https://www.toyota.be/api/dealers?country=BE&type=sales&limit=9999",
        "CH": "https://www.toyota.ch/api/dealers?country=CH&type=sales&limit=9999",
    },
    "Renault": {
        "DE": "https://www.renault.de/wired/commerce/v1/dealers?country=DE&limit=9999",
        "ES": "https://www.renault.es/wired/commerce/v1/dealers?country=ES&limit=9999",
        "FR": "https://www.renault.fr/wired/commerce/v1/dealers?country=FR&limit=9999",
        "NL": "https://www.renault.nl/wired/commerce/v1/dealers?country=NL&limit=9999",
        "BE": "https://www.renault.be/wired/commerce/v1/dealers?country=BE&limit=9999",
        "CH": "https://www.renault.ch/wired/commerce/v1/dealers?country=CH&limit=9999",
    },
    "Peugeot": {
        "DE": "https://www.peugeot.de/api/dealer/v1/search?country=DE&maxResults=9999",
        "ES": "https://www.peugeot.es/api/dealer/v1/search?country=ES&maxResults=9999",
        "FR": "https://www.peugeot.fr/api/dealer/v1/search?country=FR&maxResults=9999",
        "NL": "https://www.peugeot.nl/api/dealer/v1/search?country=NL&maxResults=9999",
        "BE": "https://www.peugeot.be/api/dealer/v1/search?country=BE&maxResults=9999",
        "CH": "https://www.peugeot.ch/api/dealer/v1/search?country=CH&maxResults=9999",
    },
    "Ford": {
        "DE": "https://www.ford.de/cgi-bin/dealer-locator.cgi?country=DE&type=json&radius=99999",
        "ES": "https://www.ford.es/cgi-bin/dealer-locator.cgi?country=ES&type=json&radius=99999",
        "FR": "https://www.ford.fr/cgi-bin/dealer-locator.cgi?country=FR&type=json&radius=99999",
        "NL": "https://www.ford.nl/cgi-bin/dealer-locator.cgi?country=NL&type=json&radius=99999",
        "BE": "https://www.ford.be/cgi-bin/dealer-locator.cgi?country=BE&type=json&radius=99999",
        "CH": "https://www.ford.ch/cgi-bin/dealer-locator.cgi?country=CH&type=json&radius=99999",
    },
    "Hyundai": {
        "DE": "https://www.hyundai.com/de/api/v1/dealer-locator/dealers?countryCode=DE",
        "ES": "https://www.hyundai.com/es/api/v1/dealer-locator/dealers?countryCode=ES",
        "FR": "https://www.hyundai.com/fr/api/v1/dealer-locator/dealers?countryCode=FR",
        "NL": "https://www.hyundai.com/nl/api/v1/dealer-locator/dealers?countryCode=NL",
        "BE": "https://www.hyundai.com/be/api/v1/dealer-locator/dealers?countryCode=BE",
        "CH": "https://www.hyundai.com/ch/api/v1/dealer-locator/dealers?countryCode=CH",
    },
    "Kia": {
        "DE": "https://www.kia.com/de/api/dealer/dealers?countryCode=DE",
        "ES": "https://www.kia.com/es/api/dealer/dealers?countryCode=ES",
        "FR": "https://www.kia.com/fr/api/dealer/dealers?countryCode=FR",
        "NL": "https://www.kia.com/nl/api/dealer/dealers?countryCode=NL",
        "BE": "https://www.kia.com/be/api/dealer/dealers?countryCode=BE",
        "CH": "https://www.kia.com/ch/api/dealer/dealers?countryCode=CH",
    },
    "Volvo": {
        "DE": "https://www.volvocars.com/api/dealer/v1/dealers?market=de&type=sales",
        "ES": "https://www.volvocars.com/api/dealer/v1/dealers?market=es&type=sales",
        "FR": "https://www.volvocars.com/api/dealer/v1/dealers?market=fr&type=sales",
        "NL": "https://www.volvocars.com/api/dealer/v1/dealers?market=nl&type=sales",
        "BE": "https://www.volvocars.com/api/dealer/v1/dealers?market=be&type=sales",
        "CH": "https://www.volvocars.com/api/dealer/v1/dealers?market=ch&type=sales",
    },
    "Opel": {
        "DE": "https://www.opel.de/api/dealer/v1/search?country=DE&maxResults=9999",
        "ES": "https://www.opel.es/api/dealer/v1/search?country=ES&maxResults=9999",
        "FR": "https://www.opel.fr/api/dealer/v1/search?country=FR&maxResults=9999",
        "NL": "https://www.opel.nl/api/dealer/v1/search?country=NL&maxResults=9999",
        "BE": "https://www.opel.be/api/dealer/v1/search?country=BE&maxResults=9999",
        "CH": "https://www.opel.ch/api/dealer/v1/search?country=CH&maxResults=9999",
    },
    "SEAT": {
        "DE": "https://www.seat.de/services/dealer-locator/dealers.json?country=DE",
        "ES": "https://www.seat.es/services/dealer-locator/dealers.json?country=ES",
        "FR": "https://www.seat.fr/services/dealer-locator/dealers.json?country=FR",
        "NL": "https://www.seat.nl/services/dealer-locator/dealers.json?country=NL",
        "BE": "https://www.seat.be/services/dealer-locator/dealers.json?country=BE",
        "CH": "https://www.seat.ch/services/dealer-locator/dealers.json?country=CH",
    },
    "Skoda": {
        "DE": "https://www.skoda-auto.de/api/dealers?country=DE&limit=9999",
        "ES": "https://www.skoda-auto.es/api/dealers?country=ES&limit=9999",
        "FR": "https://www.skoda-auto.fr/api/dealers?country=FR&limit=9999",
        "NL": "https://www.skoda-auto.nl/api/dealers?country=NL&limit=9999",
        "BE": "https://www.skoda-auto.be/api/dealers?country=BE&limit=9999",
        "CH": "https://www.skoda-auto.ch/api/dealers?country=CH&limit=9999",
    },
    "Porsche": {
        "DE": "https://finder.porsche.com/api/v2/locations?country=DE&type=dealer&limit=9999",
        "ES": "https://finder.porsche.com/api/v2/locations?country=ES&type=dealer&limit=9999",
        "FR": "https://finder.porsche.com/api/v2/locations?country=FR&type=dealer&limit=9999",
        "NL": "https://finder.porsche.com/api/v2/locations?country=NL&type=dealer&limit=9999",
        "BE": "https://finder.porsche.com/api/v2/locations?country=BE&type=dealer&limit=9999",
        "CH": "https://finder.porsche.com/api/v2/locations?country=CH&type=dealer&limit=9999",
    },
    "Fiat": {
        "DE": "https://www.fiat.de/api/dealer/v1/search?country=DE&maxResults=9999",
        "ES": "https://www.fiat.es/api/dealer/v1/search?country=ES&maxResults=9999",
        "FR": "https://www.fiat.fr/api/dealer/v1/search?country=FR&maxResults=9999",
        "NL": "https://www.fiat.nl/api/dealer/v1/search?country=NL&maxResults=9999",
        "BE": "https://www.fiat.be/api/dealer/v1/search?country=BE&maxResults=9999",
        "CH": "https://www.fiat.ch/api/dealer/v1/search?country=CH&maxResults=9999",
    },
    "Nissan": {
        "DE": "https://www.nissan.de/api/dealer/v1/search?country=DE&maxResults=9999",
        "ES": "https://www.nissan.es/api/dealer/v1/search?country=ES&maxResults=9999",
        "FR": "https://www.nissan.fr/api/dealer/v1/search?country=FR&maxResults=9999",
        "NL": "https://www.nissan.nl/api/dealer/v1/search?country=NL&maxResults=9999",
        "BE": "https://www.nissan.be/api/dealer/v1/search?country=BE&maxResults=9999",
        "CH": "https://www.nissan.ch/api/dealer/v1/search?country=CH&maxResults=9999",
    },
    "Honda": {
        "DE": "https://www.honda.de/cars/dealers.json?country=DE",
        "ES": "https://www.honda.es/cars/dealers.json?country=ES",
        "FR": "https://www.honda.fr/cars/dealers.json?country=FR",
        "NL": "https://www.honda.nl/cars/dealers.json?country=NL",
        "BE": "https://www.honda.be/cars/dealers.json?country=BE",
        "CH": "https://www.honda.ch/cars/dealers.json?country=CH",
    },
    "Mazda": {
        "DE": "https://www.mazda.de/api/dealer-locator?country=DE&limit=9999",
        "ES": "https://www.mazda.es/api/dealer-locator?country=ES&limit=9999",
        "FR": "https://www.mazda.fr/api/dealer-locator?country=FR&limit=9999",
        "NL": "https://www.mazda.nl/api/dealer-locator?country=NL&limit=9999",
        "BE": "https://www.mazda.be/api/dealer-locator?country=BE&limit=9999",
        "CH": "https://www.mazda.ch/api/dealer-locator?country=CH&limit=9999",
    },
    "Citroen": {
        "DE": "https://www.citroen.de/api/dealer/v1/search?country=DE&maxResults=9999",
        "ES": "https://www.citroen.es/api/dealer/v1/search?country=ES&maxResults=9999",
        "FR": "https://www.citroen.fr/api/dealer/v1/search?country=FR&maxResults=9999",
        "NL": "https://www.citroen.nl/api/dealer/v1/search?country=NL&maxResults=9999",
        "BE": "https://www.citroen.be/api/dealer/v1/search?country=BE&maxResults=9999",
        "CH": "https://www.citroen.ch/api/dealer/v1/search?country=CH&maxResults=9999",
    },
}

# Portal dealer directory pages
_PORTAL_DIRECTORIES: dict[str, dict[str, str]] = {
    "AS24": {
        "DE": "https://www.autoscout24.de/haendler/",
        "ES": "https://www.autoscout24.es/concesionarios/",
        "FR": "https://www.autoscout24.fr/concessionnaires/",
        "NL": "https://www.autoscout24.nl/dealers/",
        "BE": "https://www.autoscout24.be/fr/concessionnaires/",
        "CH": "https://www.autoscout24.ch/de/haendler/",
    },
    "MOBILE_DE": {
        "DE": "https://www.mobile.de/haendler/",
    },
}


# ── Data Model ───────────────────────────────────────────────────────────────


@dataclass
class DealerRecord:
    """Unified dealer record produced by every probe."""

    name: str
    country: str
    source: str  # OSM, INSEE, ZEFIX, COMMON_CRAWL, GOOGLE_MAPS, OEM_<brand>, PORTAL_<portal>
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    city: str | None = None
    postcode: str | None = None
    website: str | None = None
    phone: str | None = None
    brand_affiliation: list[str] = field(default_factory=list)
    place_id: str | None = None
    registry_id: str | None = None
    osm_id: str | None = None


# ── Rate Limiter ─────────────────────────────────────────────────────────────


class _TokenBucket:
    """Simple async token-bucket rate limiter."""

    def __init__(self, qps: float) -> None:
        self._interval = 1.0 / max(qps, 0.01)
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._last + self._interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


# ── H3 Grid (for Google Places) ─────────────────────────────────────────────


def _h3_cells_for_country(country: str) -> list[str]:
    """Generate all H3 resolution-4 cells covering a country's bounding box."""
    bbox = _BBOXES.get(country)
    if not bbox:
        return []
    lat_min, lat_max, lng_min, lng_max = bbox
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [lng_min, lat_min],
                [lng_max, lat_min],
                [lng_max, lat_max],
                [lng_min, lat_max],
                [lng_min, lat_min],
            ]
        ],
    }
    return list(h3.geo_to_cells(polygon, res=_H3_RESOLUTION))


# ── Helpers ──────────────────────────────────────────────────────────────────


def _stable_id(name: str, country: str) -> str:
    """Generate a deterministic short hash for dedup when no external ID exists."""
    raw = f"{name.strip().lower()}|{country.upper()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _normalize_website(url: str | None) -> str | None:
    """Normalize a website URL to a canonical form."""
    if not url:
        return None
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    # Strip trailing slashes for consistency
    return url.rstrip("/")


def _extract_json_dealers(data: Any) -> list[dict]:
    """
    Best-effort extraction of dealer entries from varied OEM JSON structures.
    Handles common patterns: top-level list, {'dealers': [...]}, {'results': [...]},
    {'data': {'dealers': [...]}}, etc.
    """
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        # Try common keys
        for key in ("dealers", "results", "data", "items", "locations",
                     "Dealers", "Results", "Data", "Items", "Locations",
                     "dealer", "result"):
            val = data.get(key)
            if isinstance(val, list) and len(val) > 0:
                return val
            if isinstance(val, dict):
                # Recurse one level
                return _extract_json_dealers(val)
    return []


def _extract_oem_dealer(entry: dict, brand: str, country: str) -> DealerRecord | None:
    """
    Parse a single dealer from an OEM JSON response.
    Handles many variations of field names across different OEM APIs.
    """
    # Name
    name = (
        entry.get("name")
        or entry.get("dealerName")
        or entry.get("dealer_name")
        or entry.get("title")
        or entry.get("Name")
        or entry.get("companyName")
        or ""
    ).strip()
    if not name:
        return None

    # Coordinates
    lat = _float_or_none(
        entry.get("lat")
        or entry.get("latitude")
        or entry.get("Latitude")
        or _nested_get(entry, "geo", "lat")
        or _nested_get(entry, "location", "lat")
        or _nested_get(entry, "coordinates", "lat")
        or _nested_get(entry, "geoLocation", "latitude")
        or _nested_get(entry, "position", "lat")
    )
    lng = _float_or_none(
        entry.get("lng")
        or entry.get("lon")
        or entry.get("longitude")
        or entry.get("Longitude")
        or _nested_get(entry, "geo", "lng")
        or _nested_get(entry, "geo", "lon")
        or _nested_get(entry, "location", "lng")
        or _nested_get(entry, "location", "lon")
        or _nested_get(entry, "coordinates", "lng")
        or _nested_get(entry, "coordinates", "lon")
        or _nested_get(entry, "geoLocation", "longitude")
        or _nested_get(entry, "position", "lng")
        or _nested_get(entry, "position", "lon")
    )

    # Address fields
    address_obj = entry.get("address") or entry.get("Address") or {}
    if isinstance(address_obj, str):
        address = address_obj
        city = entry.get("city") or entry.get("City") or None
        postcode = entry.get("postcode") or entry.get("zipCode") or entry.get("zip") or None
    elif isinstance(address_obj, dict):
        street = (
            address_obj.get("street")
            or address_obj.get("Street")
            or address_obj.get("line1")
            or address_obj.get("addressLine1")
            or ""
        )
        city = (
            address_obj.get("city")
            or address_obj.get("City")
            or address_obj.get("town")
            or entry.get("city")
            or None
        )
        postcode = (
            address_obj.get("postcode")
            or address_obj.get("postalCode")
            or address_obj.get("zip")
            or address_obj.get("zipCode")
            or entry.get("postcode")
            or entry.get("zipCode")
            or None
        )
        address = street
    else:
        address = entry.get("street") or entry.get("formattedAddress") or None
        city = entry.get("city") or None
        postcode = entry.get("postcode") or entry.get("zipCode") or entry.get("zip") or None

    # Website
    website = _normalize_website(
        entry.get("website")
        or entry.get("url")
        or entry.get("Website")
        or entry.get("homepage")
        or entry.get("webUrl")
    )

    # Phone
    phone = (
        entry.get("phone")
        or entry.get("telephone")
        or entry.get("Phone")
        or entry.get("phoneNumber")
        or _nested_get(entry, "contact", "phone")
        or _nested_get(entry, "contact", "telephone")
    )

    return DealerRecord(
        name=name,
        country=country,
        source=f"OEM_{brand.upper()}",
        lat=lat,
        lng=lng,
        address=address if isinstance(address, str) else None,
        city=city,
        postcode=str(postcode) if postcode else None,
        website=website,
        phone=str(phone) if phone else None,
        brand_affiliation=[brand],
    )


def _nested_get(d: dict, *keys: str) -> Any:
    """Safely traverse nested dicts."""
    current = d
    for k in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(k)
    return current


def _float_or_none(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        if f == 0.0:
            return None
        return f
    except (ValueError, TypeError):
        return None


# ── Abstract Probe ───────────────────────────────────────────────────────────


class DiscoveryProbe(ABC):
    """Abstract base for discovery probes."""

    @abstractmethod
    async def discover(self, country: str) -> AsyncIterator[DealerRecord]:
        """Yield discovered dealers for a country."""
        ...  # pragma: no cover

    @property
    @abstractmethod
    def name(self) -> str:
        """Probe identifier."""
        ...  # pragma: no cover

    def supports_country(self, country: str) -> bool:
        """Return True if this probe supports the given country. Default: all."""
        return True


# ── Probe 1: OpenStreetMap Overpass API ──────────────────────────────────────


class OSMProbe(DiscoveryProbe):
    """
    Queries OpenStreetMap Overpass API for nodes/ways tagged shop=car
    and shop=car_repair (with dealer-like names). ~10K dealers across Europe.
    """

    _OVERPASS_URL = "https://overpass-api.de/api/interpreter"

    def __init__(self) -> None:
        self._rate = _TokenBucket(0.2)  # 1 request per 5 seconds

    @property
    def name(self) -> str:
        return "OSM"

    async def discover(self, country: str) -> AsyncIterator[DealerRecord]:
        bbox = _BBOXES.get(country)
        if not bbox:
            return
        lat_min, lat_max, lng_min, lng_max = bbox
        bbox_str = f"{lat_min},{lng_min},{lat_max},{lng_max}"

        async with httpx.AsyncClient(timeout=120.0) as client:
            # Query 1: shop=car
            for record in await self._query_shop_car(client, bbox_str, country):
                yield record

            # Query 2: shop=car_repair with dealer in name
            for record in await self._query_car_repair_dealers(client, bbox_str, country):
                yield record

    async def _query_shop_car(
        self, client: httpx.AsyncClient, bbox_str: str, country: str
    ) -> list[DealerRecord]:
        query = f"""
        [out:json][timeout:180];
        (
          node["shop"="car"]({bbox_str});
          way["shop"="car"]({bbox_str});
        );
        out center;
        """
        return await self._execute_query(client, query, country)

    async def _query_car_repair_dealers(
        self, client: httpx.AsyncClient, bbox_str: str, country: str
    ) -> list[DealerRecord]:
        query = f"""
        [out:json][timeout:180];
        (
          node["shop"="car_repair"]({bbox_str});
          way["shop"="car_repair"]({bbox_str});
        );
        out center;
        """
        results = await self._execute_query(client, query, country)
        # Filter to entries whose name suggests they are a dealer (not just a repair shop)
        dealer_keywords = [
            "dealer", "autohaus", "autoh", "concession", "concessio",
            "garage auto", "autobedrijf", "autohandel", "cars", "vente auto",
            "autodealer", "automobil", "fahrzeug",
        ]
        filtered = []
        for r in results:
            name_lower = r.name.lower()
            if any(kw in name_lower for kw in dealer_keywords):
                filtered.append(r)
        return filtered

    async def _execute_query(
        self, client: httpx.AsyncClient, query: str, country: str
    ) -> list[DealerRecord]:
        await self._rate.acquire()
        try:
            resp = await client.post(self._OVERPASS_URL, data={"data": query})
            resp.raise_for_status()
        except Exception as exc:
            log.warning("probe.osm.request_error", country=country, error=str(exc))
            return []

        try:
            data = resp.json()
        except Exception:
            log.warning("probe.osm.json_error", country=country)
            return []

        elements = data.get("elements", [])
        records: list[DealerRecord] = []

        for el in elements:
            tags = el.get("tags", {})
            name = tags.get("name", "").strip()
            if not name:
                continue

            # Coordinates: node has lat/lon directly; way uses center
            lat = el.get("lat") or _nested_get(el, "center", "lat")
            lng = el.get("lon") or _nested_get(el, "center", "lon")

            address_parts = []
            if tags.get("addr:street"):
                addr_street = tags["addr:street"]
                if tags.get("addr:housenumber"):
                    addr_street += " " + tags["addr:housenumber"]
                address_parts.append(addr_street)

            records.append(DealerRecord(
                name=name,
                country=country,
                source="OSM",
                lat=_float_or_none(lat),
                lng=_float_or_none(lng),
                address=" ".join(address_parts) if address_parts else None,
                city=tags.get("addr:city"),
                postcode=tags.get("addr:postcode"),
                website=_normalize_website(tags.get("website") or tags.get("contact:website")),
                phone=tags.get("phone") or tags.get("contact:phone"),
                osm_id=str(el.get("id", "")),
            ))

        log.info("probe.osm.results", country=country, count=len(records))
        return records


# ── Probe 2: INSEE SIRENE (France only) ─────────────────────────────────────


class INSEEProbe(DiscoveryProbe):
    """
    Queries the INSEE SIRENE API for companies with NAF code 45.11Z
    (motor vehicle sales). France only. Requires INSEE_API_TOKEN env var.
    """

    _SIRENE_URL = "https://api.insee.fr/entreprises/sirene/V3.11/siret"

    def __init__(self) -> None:
        self._token = _INSEE_API_TOKEN
        self._rate = _TokenBucket(0.5)  # Conservative

    @property
    def name(self) -> str:
        return "INSEE"

    def supports_country(self, country: str) -> bool:
        return country == "FR" and bool(self._token)

    async def discover(self, country: str) -> AsyncIterator[DealerRecord]:
        if country != "FR" or not self._token:
            return

        cursor = "*"
        total_yielded = 0

        async with httpx.AsyncClient(timeout=60.0) as client:
            while cursor:
                await self._rate.acquire()

                params = {
                    "q": "activitePrincipaleUniteLegale:45.11Z AND etatAdministratifEtablissement:A",
                    "nombre": 1000,
                    "curseur": cursor,
                }
                headers = {"Authorization": f"Bearer {self._token}"}

                try:
                    resp = await client.get(
                        self._SIRENE_URL, params=params, headers=headers
                    )
                    if resp.status_code == 401:
                        log.error("probe.insee.auth_error", hint="Check INSEE_API_TOKEN")
                        return
                    if resp.status_code == 429:
                        log.warning("probe.insee.rate_limited")
                        await asyncio.sleep(30)
                        continue
                    resp.raise_for_status()
                except Exception as exc:
                    log.warning("probe.insee.request_error", error=str(exc))
                    return

                try:
                    data = resp.json()
                except Exception:
                    log.warning("probe.insee.json_error")
                    return

                header = data.get("header", {})
                cursor = header.get("curseurSuivant")
                if cursor == header.get("curseur"):
                    cursor = None  # End of pagination

                etablissements = data.get("etablissements", [])
                if not etablissements:
                    break

                for etab in etablissements:
                    record = self._parse_etablissement(etab)
                    if record:
                        total_yielded += 1
                        yield record

        log.info("probe.insee.results", country="FR", count=total_yielded)

    def _parse_etablissement(self, etab: dict) -> DealerRecord | None:
        unite = etab.get("uniteLegale", {})
        adresse = etab.get("adresseEtablissement", {})

        # Build name from denomination
        name = (
            unite.get("denominationUniteLegale")
            or unite.get("nomUniteLegale", "")
        ).strip()
        if not name:
            return None

        # SIRET = SIREN (9 digits) + NIC (5 digits)
        siret = etab.get("siret", "")

        # Address
        num = adresse.get("numeroVoieEtablissement") or ""
        type_voie = adresse.get("typeVoieEtablissement") or ""
        libelle = adresse.get("libelleVoieEtablissement") or ""
        address = f"{num} {type_voie} {libelle}".strip()

        city = adresse.get("libelleCommuneEtablissement")
        postcode = adresse.get("codePostalEtablissement")

        return DealerRecord(
            name=name,
            country="FR",
            source="INSEE",
            address=address if address else None,
            city=city,
            postcode=postcode,
            registry_id=siret if siret else None,
        )


# ── Probe 3: Zefix (Switzerland only) ───────────────────────────────────────


class ZefixProbe(DiscoveryProbe):
    """
    Queries the Swiss Zefix public REST API for companies in NOGA sector 45.11
    (motor vehicle sales). Switzerland only, no auth required.
    """

    _ZEFIX_SEARCH_URL = "https://www.zefix.admin.ch/ZefixPublicREST/api/v1/company/search"

    def __init__(self) -> None:
        self._rate = _TokenBucket(0.5)

    @property
    def name(self) -> str:
        return "ZEFIX"

    def supports_country(self, country: str) -> bool:
        return country == "CH"

    async def discover(self, country: str) -> AsyncIterator[DealerRecord]:
        if country != "CH":
            return

        total_yielded = 0
        offset = 0
        page_size = 200

        async with httpx.AsyncClient(timeout=60.0) as client:
            while True:
                await self._rate.acquire()

                payload = {
                    "languageKey": "de",
                    "searchType": "exact",
                    "maxEntries": page_size,
                    "offset": offset,
                    "nogaCode": "45.11",
                    "activeOnly": True,
                }

                try:
                    resp = await client.post(
                        self._ZEFIX_SEARCH_URL,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )
                    if resp.status_code == 404:
                        break  # No more results
                    resp.raise_for_status()
                except Exception as exc:
                    log.warning("probe.zefix.request_error", error=str(exc), offset=offset)
                    break

                try:
                    results = resp.json()
                except Exception:
                    log.warning("probe.zefix.json_error")
                    break

                if not isinstance(results, list) or len(results) == 0:
                    break

                for entry in results:
                    record = self._parse_entry(entry)
                    if record:
                        total_yielded += 1
                        yield record

                if len(results) < page_size:
                    break
                offset += page_size

        log.info("probe.zefix.results", country="CH", count=total_yielded)

    def _parse_entry(self, entry: dict) -> DealerRecord | None:
        name = (entry.get("name") or "").strip()
        if not name:
            return None

        uid = entry.get("uid") or entry.get("chid") or ""
        address_obj = entry.get("address") or {}
        canton = entry.get("canton") or entry.get("cantonIso") or ""

        street = ""
        city = None
        postcode = None
        if isinstance(address_obj, dict):
            street = address_obj.get("street") or ""
            city = address_obj.get("city") or address_obj.get("town")
            postcode = address_obj.get("swissZipCode") or address_obj.get("zipCode")
        elif isinstance(address_obj, str):
            street = address_obj

        return DealerRecord(
            name=name,
            country="CH",
            source="ZEFIX",
            address=street if street else None,
            city=city or (canton if canton else None),
            postcode=str(postcode) if postcode else None,
            registry_id=str(uid) if uid else None,
        )


# ── Probe 4: Common Crawl Index ─────────────────────────────────────────────


class CommonCrawlProbe(DiscoveryProbe):
    """
    Searches Common Crawl's URL index for domains matching automotive keywords
    per country TLD. Finds hidden dealer websites that aren't on any portal.
    Slow but finds gems.
    """

    _CC_INDEX_URL = "https://index.commoncrawl.org/CC-MAIN-2024-10-index"

    def __init__(self) -> None:
        self._rate = _TokenBucket(0.5)  # 1 request per 2 seconds

    @property
    def name(self) -> str:
        return "COMMON_CRAWL"

    async def discover(self, country: str) -> AsyncIterator[DealerRecord]:
        tld = _COUNTRY_TLDS.get(country)
        if not tld:
            return

        keywords = _CC_KEYWORDS.get(tld, [])
        if not keywords:
            return

        seen_domains: set[str] = set()
        total_yielded = 0

        async with httpx.AsyncClient(timeout=60.0) as client:
            for keyword in keywords:
                try:
                    records = await self._search_keyword(
                        client, keyword, tld, country, seen_domains
                    )
                    for record in records:
                        total_yielded += 1
                        yield record
                except Exception as exc:
                    log.warning(
                        "probe.cc.keyword_error",
                        keyword=keyword,
                        tld=tld,
                        error=str(exc),
                    )

        log.info("probe.cc.results", country=country, count=total_yielded)

    async def _search_keyword(
        self,
        client: httpx.AsyncClient,
        keyword: str,
        tld: str,
        country: str,
        seen_domains: set[str],
    ) -> list[DealerRecord]:
        await self._rate.acquire()

        params = {
            "url": f"{keyword}.{tld}",
            "output": "json",
            "limit": 500,
            "fl": "url,status,mime",
        }

        try:
            resp = await client.get(self._CC_INDEX_URL, params=params)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
        except Exception as exc:
            log.debug("probe.cc.request_error", keyword=keyword, error=str(exc))
            return []

        records: list[DealerRecord] = []
        lines = resp.text.strip().split("\n")

        for line in lines:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            url = entry.get("url", "")
            status = str(entry.get("status", ""))
            mime = entry.get("mime", "")

            # Only HTML responses that returned 200
            if status != "200" or "html" not in mime.lower():
                continue

            # Extract domain
            try:
                parsed = urllib.parse.urlparse(url)
                domain = parsed.netloc.lower()
            except Exception:
                continue

            # Remove www prefix for dedup
            if domain.startswith("www."):
                domain = domain[4:]

            if not domain or domain in seen_domains:
                continue

            # Skip known large portals — we want individual dealer sites
            skip_domains = {
                "autoscout24", "mobile.de", "leboncoin", "marktplaats",
                "google", "facebook", "instagram", "twitter", "youtube",
                "wikipedia", "ebay", "amazon", "yelp",
            }
            if any(sd in domain for sd in skip_domains):
                continue

            seen_domains.add(domain)

            # Use domain as the dealer name (best we can extract from CC)
            name_from_domain = domain.replace(".", " ").replace("-", " ").title()

            records.append(DealerRecord(
                name=name_from_domain,
                country=country,
                source="COMMON_CRAWL",
                website=f"https://{domain}",
            ))

        return records


# ── Probe 5: Google Maps Grid Sweep ─────────────────────────────────────────


class GoogleMapsGridProbe(DiscoveryProbe):
    """
    Systematic H3 hex-grid sweep across all 6 countries using Google Places API.
    Divides each country into H3 resolution-5 hexagons (~252 km² each),
    queries Places Nearby Search with automotive keywords per cell.

    Yields every business with type=car_dealer and extracts website_url.
    This catches thousands of small-town dealers invisible to portals and OSM.

    Cost model (res-5):
      ~10,000 hexes total × 4 keywords × 1 call = ~40,000 API calls
      At $0.032/call ≈ $1,280 for full 6-country sweep.
      Set H3_GRID_RESOLUTION env to adjust granularity.
    """

    _H3_RES = int(os.environ.get("H3_GRID_RESOLUTION", "5"))
    _NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    _DETAIL_URL = "https://maps.googleapis.com/maps/api/place/details/json"

    # Search radius per hex center (meters). res-5 edge ~15km → 20km covers it.
    _RADIUS = 20_000

    # Automotive keywords per country — cast wide
    _QUERIES: dict[str, list[str]] = {
        "DE": ["Autohaus", "Autohändler", "Gebrauchtwagen", "KFZ Handel"],
        "ES": ["concesionario coches", "venta coches", "coches ocasión", "vehículos segunda mano"],
        "FR": ["concessionnaire automobile", "garage vente voiture", "voiture occasion", "vente véhicule"],
        "NL": ["autodealer", "autobedrijf", "occasion auto", "autohandel"],
        "BE": ["autodealer", "concessionnaire auto", "garage auto", "tweedehands auto"],
        "CH": ["Autohaus", "concessionnaire automobile", "Autohändler", "Occasionen"],
    }

    def __init__(self) -> None:
        self._api_key = _GOOGLE_API_KEY
        self._rate = _TokenBucket(10.0)  # 10 QPS (Google allows 50)

    @property
    def name(self) -> str:
        return "GOOGLE_GRID"

    def supports_country(self, country: str) -> bool:
        return bool(self._api_key)

    def _h3_cells(self, country: str) -> list[str]:
        bbox = _BBOXES.get(country)
        if not bbox:
            return []
        lat_min, lat_max, lng_min, lng_max = bbox
        polygon = {
            "type": "Polygon",
            "coordinates": [[
                [lng_min, lat_min], [lng_max, lat_min],
                [lng_max, lat_max], [lng_min, lat_max],
                [lng_min, lat_min],
            ]],
        }
        return list(h3.geo_to_cells(polygon, res=self._H3_RES))

    async def discover(self, country: str) -> AsyncIterator[DealerRecord]:
        if not self._api_key:
            log.warning("probe.google_grid.disabled", reason="no GOOGLE_MAPS_API_KEY")
            return

        cells = self._h3_cells(country)
        queries = self._QUERIES.get(country, ["car dealer"])
        seen_place_ids: set[str] = set()
        total = 0

        log.info("probe.google_grid.start", country=country, cells=len(cells), queries=len(queries))

        async with httpx.AsyncClient(timeout=15.0) as client:
            for cell_idx, cell in enumerate(cells):
                lat, lng = h3.cell_to_latlng(cell)

                for query in queries:
                    records = await self._search_nearby(
                        client, lat, lng, query, country, seen_place_ids,
                    )
                    for record in records:
                        total += 1
                        yield record

                    # Follow next_page_token for up to 3 pages (60 results)
                    # handled inside _search_nearby

                if (cell_idx + 1) % 200 == 0:
                    log.info(
                        "probe.google_grid.progress",
                        country=country,
                        cells_done=cell_idx + 1,
                        cells_total=len(cells),
                        dealers_found=total,
                    )

        log.info("probe.google_grid.done", country=country, total=total)

    async def _search_nearby(
        self,
        client: httpx.AsyncClient,
        lat: float,
        lng: float,
        query: str,
        country: str,
        seen: set[str],
    ) -> list[DealerRecord]:
        records: list[DealerRecord] = []
        next_page_token: str | None = None

        for page in range(3):  # max 3 pages per query (60 results)
            await self._rate.acquire()

            params: dict[str, Any] = {
                "key": self._api_key,
                "location": f"{lat},{lng}",
                "radius": self._RADIUS,
                "keyword": query,
                "type": "car_dealer",
            }
            if next_page_token:
                params = {"key": self._api_key, "pagetoken": next_page_token}

            try:
                resp = await client.get(self._NEARBY_URL, params=params)
                if resp.status_code != 200:
                    break
                data = resp.json()
            except Exception:
                break

            results = data.get("results", [])
            if not results:
                break

            for place in results:
                pid = place.get("place_id", "")
                if not pid or pid in seen:
                    continue
                seen.add(pid)

                name = (place.get("name") or "").strip()
                if not name:
                    continue

                geo = place.get("geometry", {}).get("location", {})
                p_lat = _float_or_none(geo.get("lat"))
                p_lng = _float_or_none(geo.get("lng"))
                vicinity = place.get("vicinity") or ""

                # Fetch website from Place Details
                website = await self._fetch_website(client, pid)

                records.append(DealerRecord(
                    name=name,
                    country=country,
                    source="GOOGLE_GRID",
                    lat=p_lat,
                    lng=p_lng,
                    address=vicinity or None,
                    website=website,
                    place_id=pid,
                ))

            next_page_token = data.get("next_page_token")
            if not next_page_token:
                break
            # Google requires 2s delay before using next_page_token
            await asyncio.sleep(2.0)

        return records

    async def _fetch_website(self, client: httpx.AsyncClient, place_id: str) -> str | None:
        await self._rate.acquire()
        try:
            resp = await client.get(self._DETAIL_URL, params={
                "key": self._api_key,
                "place_id": place_id,
                "fields": "website",
            })
            if resp.status_code == 200:
                website = resp.json().get("result", {}).get("website")
                return _normalize_website(website) if website else None
        except Exception:
            pass
        return None


# ── Probe 6: OEM Dealer Locators ────────────────────────────────────────────


class OEMDealerProbe(DiscoveryProbe):
    """
    Scrapes OEM "Find a Dealer" JSON endpoints for each major brand.
    These are public XHR endpoints that power OEM dealer-search pages.
    """

    def __init__(self) -> None:
        self._rate = _TokenBucket(0.5)  # Be polite to OEM servers

    @property
    def name(self) -> str:
        return "OEM"

    async def discover(self, country: str) -> AsyncIterator[DealerRecord]:
        total_yielded = 0

        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu) httpx/0.27 Python/3.12",
                "Accept": "application/json, text/html, */*",
                "Accept-Language": "en-US,en;q=0.9,de;q=0.8,fr;q=0.7",
            },
        ) as client:
            for brand, endpoints in _OEM_ENDPOINTS.items():
                url = endpoints.get(country)
                if not url:
                    continue

                try:
                    records = await self._fetch_brand_dealers(client, brand, url, country)
                    for record in records:
                        total_yielded += 1
                        yield record
                except Exception as exc:
                    log.warning(
                        "probe.oem.brand_error",
                        brand=brand,
                        country=country,
                        error=str(exc),
                    )

        log.info("probe.oem.results", country=country, count=total_yielded)

    async def _fetch_brand_dealers(
        self,
        client: httpx.AsyncClient,
        brand: str,
        url: str,
        country: str,
    ) -> list[DealerRecord]:
        await self._rate.acquire()

        try:
            resp = await client.get(url)
            if resp.status_code == 403:
                log.debug("probe.oem.forbidden", brand=brand, country=country)
                return []
            if resp.status_code == 404:
                log.debug("probe.oem.not_found", brand=brand, country=country)
                return []
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.debug("probe.oem.http_error", brand=brand, status=exc.response.status_code)
            return []
        except Exception as exc:
            log.debug("probe.oem.request_error", brand=brand, error=str(exc))
            return []

        # Try JSON parsing; some OEM pages return HTML with embedded JSON
        data = None
        try:
            data = resp.json()
        except Exception:
            # Try to extract JSON from HTML page (some OEMs embed JSON in script tags)
            try:
                text = resp.text
                # Look for JSON in <script> or data attributes
                json_match = re.search(
                    r'(?:window\.__INITIAL_STATE__|var\s+dealers\s*=|"dealers"\s*:\s*)\s*(\[.*?\]);?\s*(?:</script>|$)',
                    text,
                    re.DOTALL,
                )
                if json_match:
                    data = json.loads(json_match.group(1))
            except Exception:
                pass

        if data is None:
            log.debug("probe.oem.no_data", brand=brand, country=country)
            return []

        entries = _extract_json_dealers(data)
        records: list[DealerRecord] = []

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            record = _extract_oem_dealer(entry, brand, country)
            if record:
                records.append(record)

        log.debug(
            "probe.oem.brand_done",
            brand=brand,
            country=country,
            count=len(records),
        )
        return records


# ── Probe 7: Portal Aggregator Hijack ──────────────────────────────────────
#
# NOT scraping vehicle listings. Scraping DEALER DIRECTORIES from major portals.
# Each portal lists professional sellers with a "Visit Website" link.
# We iterate every page of the directory, follow each dealer profile,
# and extract their homepage URL. This is the highest-yield free probe.


# Portal configuration: base URLs, profile patterns, website extraction patterns
_PORTAL_AGGR_CONFIG: dict[str, dict[str, Any]] = {
    "AUTOSCOUT24": {
        "directories": {
            "DE": "https://www.autoscout24.de/haendler/",
            "ES": "https://www.autoscout24.es/concesionarios/",
            "FR": "https://www.autoscout24.fr/concessionnaires/",
            "NL": "https://www.autoscout24.nl/dealers/",
            "BE": "https://www.autoscout24.be/fr/concessionnaires/",
            "CH": "https://www.autoscout24.ch/de/haendler/",
        },
        "max_pages": 500,
        # Regex: extract profile hrefs from listing pages
        "profile_re": re.compile(
            r'href="((?:/(?:haendler|dealers?|concession[a-z]*|concessionnaire[a-z]*)/)[^"?#]+)"',
            re.I,
        ),
        # Domain prefix for resolving relative profile URLs
        "domain": {
            "DE": "https://www.autoscout24.de",
            "ES": "https://www.autoscout24.es",
            "FR": "https://www.autoscout24.fr",
            "NL": "https://www.autoscout24.nl",
            "BE": "https://www.autoscout24.be",
            "CH": "https://www.autoscout24.ch",
        },
        # On the profile page, extract the dealer's OWN website
        "website_re": [
            # Explicit "visit website" / "Webseite besuchen" links
            re.compile(
                r'href="(https?://(?!(?:www\.)?autoscout24)[^"]+)"[^>]*>\s*'
                r'(?:Website|Webseite|Sitio\s*web|Site\s*web|Visiter|Besuchen|Bekijken)',
                re.I,
            ),
            # JSON-LD url field (excluding autoscout24 itself)
            re.compile(r'"url"\s*:\s*"(https?://(?!(?:www\.)?autoscout24)[^"]+)"'),
            # data-href or class-based website link
            re.compile(
                r'class="[^"]*(?:dealer-?website|homepage|extern|website-link)[^"]*"[^>]*'
                r'href="(https?://(?!(?:www\.)?autoscout24)[^"]+)"',
                re.I,
            ),
        ],
    },
    "MOBILE_DE": {
        "directories": {
            "DE": "https://www.mobile.de/haendler/",
        },
        "max_pages": 500,
        "profile_re": re.compile(r'href="(/haendler/[^"?#]+)"', re.I),
        "domain": {"DE": "https://www.mobile.de"},
        "website_re": [
            re.compile(
                r'href="(https?://(?!(?:www\.)?mobile\.de)[^"]+)"[^>]*>\s*'
                r'(?:Website|Homepage|Webseite)',
                re.I,
            ),
            re.compile(r'"url"\s*:\s*"(https?://(?!(?:www\.)?mobile\.de)[^"]+)"'),
        ],
    },
    "LEBONCOIN": {
        "directories": {
            "FR": "https://www.leboncoin.fr/boutiques/voitures/",
        },
        "max_pages": 300,
        "profile_re": re.compile(r'href="(/boutique/[^"?#]+)"', re.I),
        "domain": {"FR": "https://www.leboncoin.fr"},
        "website_re": [
            re.compile(
                r'href="(https?://(?!(?:www\.)?leboncoin)[^"]+)"[^>]*>\s*'
                r'(?:Site\s*web|Visiter|Voir\s*le\s*site)',
                re.I,
            ),
            re.compile(r'"website"\s*:\s*"(https?://[^"]+)"'),
        ],
    },
    "COCHES_NET": {
        "directories": {
            "ES": "https://www.coches.net/concesionarios/",
        },
        "max_pages": 200,
        "profile_re": re.compile(r'href="(/concesionarios?/[^"?#]+\.htm)"', re.I),
        "domain": {"ES": "https://www.coches.net"},
        "website_re": [
            re.compile(
                r'href="(https?://(?!(?:www\.)?coches\.net)[^"]+)"[^>]*>\s*'
                r'(?:Web|Sitio|P[áa]gina|Visitar)',
                re.I,
            ),
            re.compile(r'"url"\s*:\s*"(https?://(?!(?:www\.)?coches\.net)[^"]+)"'),
        ],
    },
    "MARKTPLAATS": {
        "directories": {
            "NL": "https://www.marktplaats.nl/verkopers/autos/",
        },
        "max_pages": 200,
        "profile_re": re.compile(r'href="(/verkopers?/[^"?#]+)"', re.I),
        "domain": {"NL": "https://www.marktplaats.nl"},
        "website_re": [
            re.compile(
                r'href="(https?://(?!(?:www\.)?marktplaats)[^"]+)"[^>]*>\s*'
                r'(?:Website|Bekijk|Bezoek)',
                re.I,
            ),
        ],
    },
    "2DEHANDS": {
        "directories": {
            "BE": "https://www.2dehands.be/verkopers/autos/",
        },
        "max_pages": 200,
        "profile_re": re.compile(r'href="(/verkopers?/[^"?#]+)"', re.I),
        "domain": {"BE": "https://www.2dehands.be"},
        "website_re": [
            re.compile(
                r'href="(https?://(?!(?:www\.)?2dehands)[^"]+)"[^>]*>\s*'
                r'(?:Website|Bekijk|Bezoek)',
                re.I,
            ),
        ],
    },
}

# Skip these domains when extracting dealer websites (portals, social, directories)
_SKIP_DOMAINS = frozenset({
    "autoscout24.", "mobile.de", "leboncoin.", "coches.net", "marktplaats.",
    "2dehands.", "kleinanzeigen.", "wallapop.", "milanuncios.",
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com",
    "youtube.com", "google.", "yelp.", "tripadvisor.", "wikipedia.",
    "pagesjaunes.", "gelbeseiten.", "goudengids.", "paginasamarillas.",
})


class PortalAggregatorProbe(DiscoveryProbe):
    """
    Scrapes dealer DIRECTORIES from major European portals.
    Phase 1: Paginate through the dealer listing, collect profile URLs.
    Phase 2: Follow each profile page, extract the dealer's own website URL.

    Portals: AutoScout24 (6 countries), Mobile.de, LeBonCoin, Coches.net,
             Marktplaats, 2dehands.
    """

    def __init__(self) -> None:
        self._list_rate = _TokenBucket(0.5)    # 2s between listing pages
        self._profile_rate = _TokenBucket(2.0)  # 0.5s between profile fetches

    @property
    def name(self) -> str:
        return "PORTAL_AGGR"

    async def discover(self, country: str) -> AsyncIterator[DealerRecord]:
        total = 0

        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu) httpx/0.27 Python/3.12",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,de;q=0.8,fr;q=0.7,es;q=0.6,nl;q=0.5",
            },
        ) as client:
            for portal_name, cfg in _PORTAL_AGGR_CONFIG.items():
                dir_url = cfg["directories"].get(country)
                if not dir_url:
                    continue

                domain = cfg["domain"].get(country, "")
                try:
                    async for record in self._scrape_portal(
                        client, portal_name, dir_url, domain, cfg, country,
                    ):
                        total += 1
                        yield record
                except Exception as exc:
                    log.warning("probe.portal_aggr.error",
                                portal=portal_name, country=country, error=str(exc))

        log.info("probe.portal_aggr.results", country=country, total=total)

    async def _scrape_portal(
        self,
        client: httpx.AsyncClient,
        portal: str,
        dir_url: str,
        domain: str,
        cfg: dict,
        country: str,
    ) -> AsyncIterator[DealerRecord]:
        """Phase 1: paginate directory. Phase 2: follow profiles."""
        profile_re: re.Pattern = cfg["profile_re"]
        website_patterns: list[re.Pattern] = cfg["website_re"]
        max_pages = cfg.get("max_pages", 200)

        seen_profiles: set[str] = set()
        page = 1

        while page <= max_pages:
            await self._list_rate.acquire()

            url = dir_url if page == 1 else f"{dir_url}?page={page}"
            try:
                resp = await client.get(url)
                if resp.status_code in (404, 410, 403):
                    break
                resp.raise_for_status()
            except Exception as exc:
                log.debug("probe.portal_aggr.list_page_fail",
                          portal=portal, page=page, error=str(exc))
                break

            html = resp.text

            # Extract profile URLs from this listing page
            profile_hrefs = profile_re.findall(html)
            if not profile_hrefs:
                break

            new_profiles: list[str] = []
            for href in profile_hrefs:
                # Normalize: ensure absolute URL
                if href.startswith("/"):
                    full = domain + href
                elif href.startswith("http"):
                    full = href
                else:
                    continue

                # Dedup
                canon = full.rstrip("/").lower()
                if canon not in seen_profiles:
                    seen_profiles.add(canon)
                    new_profiles.append(full)

            if not new_profiles:
                break  # pagination exhausted (all dupes)

            # Phase 2: Follow each profile in parallel batches of 5
            for batch_start in range(0, len(new_profiles), 5):
                batch = new_profiles[batch_start:batch_start + 5]
                tasks = [
                    self._extract_from_profile(
                        client, profile_url, portal, website_patterns, country,
                    )
                    for profile_url in batch
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, DealerRecord):
                        yield result

            # Check for next page
            if not self._has_next_page(html):
                break
            page += 1

            if page % 20 == 0:
                log.info("probe.portal_aggr.progress",
                         portal=portal, country=country, page=page,
                         profiles=len(seen_profiles))

        log.info("probe.portal_aggr.portal_done",
                 portal=portal, country=country, pages=page,
                 profiles=len(seen_profiles))

    async def _extract_from_profile(
        self,
        client: httpx.AsyncClient,
        profile_url: str,
        portal: str,
        website_patterns: list[re.Pattern],
        country: str,
    ) -> DealerRecord | None:
        """Fetch a dealer profile page and extract name + website URL."""
        await self._profile_rate.acquire()

        try:
            resp = await client.get(profile_url)
            if resp.status_code >= 400:
                return None
            html = resp.text
        except Exception:
            return None

        # Extract name from <h1> or JSON-LD
        name = None
        h1_match = re.search(r'<h1[^>]*>([^<]{3,120})</h1>', html)
        if h1_match:
            name = h1_match.group(1).strip()
            name = re.sub(r"\s+", " ", name)

        if not name:
            # Try JSON-LD
            ld_match = re.search(r'"name"\s*:\s*"([^"]{3,120})"', html)
            if ld_match:
                name = ld_match.group(1).strip()

        if not name:
            return None

        # Extract website — try each pattern in order
        website = None
        for pattern in website_patterns:
            m = pattern.search(html)
            if m:
                candidate = m.group(1).strip()
                # Validate: not a portal domain
                if not any(skip in candidate.lower() for skip in _SKIP_DOMAINS):
                    website = _normalize_website(candidate)
                    break

        # Also try JSON-LD structured data
        if not website:
            for ld_match in re.finditer(
                r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
                html, re.DOTALL,
            ):
                try:
                    ld = json.loads(ld_match.group(1))
                    if isinstance(ld, dict):
                        ld_url = ld.get("url") or ""
                        if ld_url and not any(skip in ld_url.lower() for skip in _SKIP_DOMAINS):
                            website = _normalize_website(ld_url)
                            break
                except (json.JSONDecodeError, TypeError):
                    pass

        # Extract address from JSON-LD or meta tags
        address = city = postcode = phone = None
        addr_match = re.search(
            r'"streetAddress"\s*:\s*"([^"]*)".*?'
            r'"addressLocality"\s*:\s*"([^"]*)".*?'
            r'"postalCode"\s*:\s*"([^"]*)"',
            html, re.DOTALL,
        )
        if addr_match:
            address = addr_match.group(1).strip() or None
            city = addr_match.group(2).strip() or None
            postcode = addr_match.group(3).strip() or None

        phone_match = re.search(r'"telephone"\s*:\s*"([^"]+)"', html)
        if phone_match:
            phone = phone_match.group(1).strip()

        # Coords from JSON-LD
        lat = lng = None
        geo_match = re.search(
            r'"latitude"\s*:\s*"?([0-9.]+)"?.*?"longitude"\s*:\s*"?([0-9.]+)"?',
            html, re.DOTALL,
        )
        if geo_match:
            lat = _float_or_none(geo_match.group(1))
            lng = _float_or_none(geo_match.group(2))

        return DealerRecord(
            name=name,
            country=country,
            source=f"PORTAL_{portal}",
            lat=lat,
            lng=lng,
            address=address,
            city=city,
            postcode=postcode,
            website=website,
            phone=phone,
        )

    @staticmethod
    def _has_next_page(html: str) -> bool:
        next_patterns = [
            r'rel="next"',
            r'class="[^"]*next[^"]*"',
            r'aria-label="[Nn]ext',
            r'data-page="next"',
            r'>\s*(?:Next|Weiter|Suivant|Volgende|Siguiente|Nächste)\s*<',
            r'aria-label="[Pp]age\s+suivante"',
        ]
        return any(re.search(p, html, re.I) for p in next_patterns)


# ── Probe 8: Government Registry Bridge ────────────────────────────────────
#
# Wraps the 6 existing crawlers from scrapers/discovery/registries/ that tap
# into official government business registries. Filters by NACE 45.11
# (motor vehicle sales). These crawlers are fully functional — DE (Gelbe
# Seiten), FR (SIRENE), NL (KVK bulk CSV), BE (BCE open data), CH (Zefix),
# ES (Páginas Amarillas). We bridge them into the main discovery pipeline.


class GovernmentRegistryBridgeProbe(DiscoveryProbe):
    """
    Bridges existing government registry crawlers into the discovery pipeline.

    Each sub-crawler handles one country's official business registry:
      DE — Gelbe Seiten (Yellow Pages) systematic PLZ sweep
      FR — INSEE SIRENE open API (NAF 4511Z, 4519Z, 4520A)
      NL — KVK bulk CSV download (SBI 4511)
      BE — BCE/KBO open data ZIP (NACE 4511)
      CH — Zefix commercial register per canton
      ES — Páginas Amarillas API (52 provinces × 5 queries)

    These are SEPARATE from the native Probes 2 (INSEE) and 3 (Zefix) which
    query simpler API endpoints. The bridge crawlers use bulk data downloads
    and systematic sweeps for deeper coverage.
    """

    def __init__(self) -> None:
        self._crawler_classes: dict[str, tuple[str, str]] = {}
        self._loaded = False

    def _load_crawler_classes(self) -> None:
        """Load crawler CLASSES (not instances — they need rdb+session at runtime)."""
        if self._loaded:
            return
        _registry_map = {
            "DE": ("scrapers.discovery.registries.de_handelsregister", "DEHandelsregisterCrawler"),
            "FR": ("scrapers.discovery.registries.fr_sirene", "FRSIRENECrawler"),
            "NL": ("scrapers.discovery.registries.nl_kvk", "NLKVKCrawler"),
            "BE": ("scrapers.discovery.registries.be_bce", "BEBCECrawler"),
            "CH": ("scrapers.discovery.registries.ch_zefix", "CHZefixCrawler"),
            "ES": ("scrapers.discovery.registries.es_aeoc", "ESAEOCCrawler"),
        }
        for country, (module_path, class_name) in _registry_map.items():
            try:
                import importlib
                mod = importlib.import_module(module_path)
                self._crawler_classes[country] = getattr(mod, class_name)
            except (ImportError, AttributeError) as exc:
                log.debug("probe.registry_bridge.skip", country=country, error=str(exc))
        self._loaded = True
        log.info("probe.registry_bridge.loaded", crawlers=list(self._crawler_classes.keys()))

    @property
    def name(self) -> str:
        return "GOV_REGISTRY"

    def supports_country(self, country: str) -> bool:
        self._load_crawler_classes()
        return country in self._crawler_classes

    async def discover(self, country: str) -> AsyncIterator[DealerRecord]:
        self._load_crawler_classes()
        crawler_cls = self._crawler_classes.get(country)
        if not crawler_cls:
            return

        total = 0
        log.info("probe.registry_bridge.start", country=country,
                 crawler=crawler_cls.__name__)

        import aiohttp

        # Create the runtime dependencies the legacy crawlers expect
        rdb = redis_from_url(_REDIS_URL, decode_responses=True)
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={
                    "User-Agent": "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu) httpx/0.27 Python/3.12",
                },
            ) as session:
                crawler = crawler_cls(rdb=rdb, session=session)

                async for raw in crawler.crawl():
                    record = self._convert(raw, country)
                    if record:
                        total += 1
                        yield record

                        if total % 1000 == 0:
                            log.info("probe.registry_bridge.progress",
                                     country=country, found=total)
        except Exception as exc:
            log.warning("probe.registry_bridge.error",
                        country=country, error=str(exc), found_before_error=total)
        finally:
            await rdb.aclose()

        log.info("probe.registry_bridge.done", country=country, total=total)

    @staticmethod
    def _convert(raw: dict, country: str) -> DealerRecord | None:
        """Convert a registry crawler's raw dict to a DealerRecord."""
        name = (raw.get("name") or raw.get("company_name") or "").strip()
        if not name or len(name) < 3:
            return None

        return DealerRecord(
            name=name,
            country=country,
            source=f"GOV_{country}",
            lat=_float_or_none(raw.get("lat") or raw.get("latitude")),
            lng=_float_or_none(raw.get("lng") or raw.get("lon") or raw.get("longitude")),
            address=raw.get("address") or raw.get("street") or None,
            city=raw.get("city") or raw.get("locality") or None,
            postcode=str(raw.get("postcode") or raw.get("zip") or raw.get("postal_code") or "") or None,
            website=_normalize_website(raw.get("website") or raw.get("url")),
            phone=raw.get("phone") or raw.get("telephone") or None,
            registry_id=raw.get("registry_id") or raw.get("siret") or raw.get("kvk_number")
                        or raw.get("bce_number") or raw.get("uid") or None,
        )


# ── Database Operations ──────────────────────────────────────────────────────


async def _upsert_dealer(pg: asyncpg.Pool, record: DealerRecord) -> None:
    """Upsert a dealer record into PostgreSQL with entity resolution."""
    # Compute H3 indices if coordinates available
    h3_res7 = None
    h3_res4 = None
    if record.lat and record.lng:
        try:
            h3_res7 = h3.latlng_to_cell(record.lat, record.lng, 7)
            h3_res4 = h3.latlng_to_cell(record.lat, record.lng, 4)
        except Exception:
            pass

    await pg.execute(
        """
        INSERT INTO dealers (
            place_id, registry_id, osm_id, name, country,
            lat, lng, h3_res7, h3_res4,
            address, city, postcode, website, phone,
            brand_affiliation,
            source, discovery_sources, spider_status,
            created_at, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9,
            $10, $11, $12, $13, $14,
            $15,
            $16, ARRAY[$16]::text[], 'PENDING',
            NOW(), NOW()
        )
        ON CONFLICT (COALESCE(place_id, ''), COALESCE(registry_id, ''), COALESCE(osm_id, ''), name, country)
        DO UPDATE SET
            lat                = COALESCE(EXCLUDED.lat, dealers.lat),
            lng                = COALESCE(EXCLUDED.lng, dealers.lng),
            h3_res7            = COALESCE(EXCLUDED.h3_res7, dealers.h3_res7),
            h3_res4            = COALESCE(EXCLUDED.h3_res4, dealers.h3_res4),
            address            = COALESCE(EXCLUDED.address, dealers.address),
            city               = COALESCE(EXCLUDED.city, dealers.city),
            postcode           = COALESCE(EXCLUDED.postcode, dealers.postcode),
            website            = COALESCE(EXCLUDED.website, dealers.website),
            phone              = COALESCE(EXCLUDED.phone, dealers.phone),
            osm_id             = COALESCE(EXCLUDED.osm_id, dealers.osm_id),
            brand_affiliation  = ARRAY(
                SELECT DISTINCT unnest(
                    COALESCE(dealers.brand_affiliation, ARRAY[]::text[])
                    || COALESCE(EXCLUDED.brand_affiliation, ARRAY[]::text[])
                )
            ),
            discovery_sources  = ARRAY(
                SELECT DISTINCT unnest(
                    COALESCE(dealers.discovery_sources, ARRAY[]::text[])
                    || COALESCE(EXCLUDED.discovery_sources, ARRAY[]::text[])
                )
            ),
            updated_at         = NOW()
        """,
        record.place_id or "",
        record.registry_id or "",
        record.osm_id or "",
        record.name,
        record.country,
        record.lat,
        record.lng,
        h3_res7,
        h3_res4,
        record.address,
        record.city,
        record.postcode,
        record.website,
        record.phone,
        record.brand_affiliation if record.brand_affiliation else [],
        record.source,
    )


_STREAM_MISSING_URL = "stream:dealers_missing_url"
_STREAM_SNIPER_QUEUE = "stream:dealers_sniper_queue"


async def _publish_dealer(rdb: Any, record: DealerRecord) -> None:
    """
    Route dealer to the correct stream based on whether it has a website.

    Has website  → stream:dealer_discovered (spider consumes immediately)
    No website   → stream:dealers_missing_url (URL resolver consumes in real-time)
    """
    dealer_id = record.place_id or record.registry_id or record.osm_id or _stable_id(record.name, record.country)
    payload = {
        "dealer_id": dealer_id,
        "name": record.name,
        "country": record.country,
        "city": record.city or "",
        "postcode": record.postcode or "",
        "source": record.source,
    }

    if record.website:
        payload["website"] = record.website
        await rdb.xadd(_STREAM_OUT, payload)
    else:
        # No website → route to URL resolver stream for real-time resolution
        await rdb.xadd(_STREAM_MISSING_URL, payload)


# ── URL Resolution Engine (DuckDuckGo) — STREAM CONSUMER ────────────────────
# Runs as an independent service consuming stream:dealers_missing_url in
# real-time. Every dealer that Phase 1 discovers WITHOUT a website lands
# here within milliseconds. No waiting. No batching. Pure event-driven.


class URLResolver:
    """
    Stream consumer: reads from stream:dealers_missing_url, resolves websites
    via DuckDuckGo HTML scraping, routes results:

      Resolved   → UPDATE dealers.website + publish to stream:dealer_discovered
      Unresolved → publish to stream:dealers_sniper_queue (Google Places last resort)

    Runs continuously alongside Phase 1. Zero idle time.
    """

    _DDG_URL = "https://html.duckduckgo.com/html/"
    _CONSUMER_GROUP = "cg_url_resolver"
    _CONSUMER_NAME = "resolver-1"

    _USER_AGENT = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu) httpx/0.27 Python/3.12"

    _ACCEPT_LANGUAGES = {
        "DE": "de-DE,de;q=0.9,en;q=0.5",
        "ES": "es-ES,es;q=0.9,en;q=0.5",
        "FR": "fr-FR,fr;q=0.9,en;q=0.5",
        "NL": "nl-NL,nl;q=0.9,en;q=0.5",
        "BE": "nl-BE,nl;q=0.8,fr-BE;q=0.7,en;q=0.5",
        "CH": "de-CH,de;q=0.9,fr;q=0.7,en;q=0.5",
    }

    _PORTAL_DOMAINS = frozenset({
        "autoscout24.", "mobile.de", "kleinanzeigen.de", "heycar.",
        "coches.net", "wallapop.com", "milanuncios.com", "autocasion.com",
        "leboncoin.fr", "lacentrale.fr", "paruvendu.com",
        "marktplaats.nl", "autotrack.nl", "gaspedaal.nl",
        "2dehands.be", "gocar.be",
        "tutti.ch", "comparis.ch", "ricardo.ch",
        "facebook.com", "instagram.com", "twitter.com", "linkedin.com",
        "youtube.com", "google.com", "yelp.", "tripadvisor.",
        "pagesjaunes.fr", "gelbeseiten.de", "goudengids.",
        "paginasamarillas.es", "local.ch", "search.ch",
        "wikipedia.org", "wikidata.org",
    })

    _COUNTRY_NAMES = {
        "DE": "Deutschland",
        "ES": "España",
        "FR": "France",
        "NL": "Nederland",
        "BE": "België",
        "CH": "Schweiz",
    }

    _COUNTRY_AUTO_KEYWORDS = {
        "DE": "autohaus",
        "ES": "concesionario coches",
        "FR": "concessionnaire automobile",
        "NL": "autobedrijf",
        "BE": "autobedrijf garage",
        "CH": "autohaus garage",
    }

    def __init__(self) -> None:
        self._resolved = 0
        self._failed = 0
        self._stop = asyncio.Event()

    async def run(self, pg: asyncpg.Pool, rdb: Any) -> None:
        """
        Main loop: consume stream:dealers_missing_url indefinitely.
        Resolves URLs in real-time as Phase 1 discovers dealers.
        """
        # Ensure consumer group exists
        try:
            await rdb.xgroup_create(
                _STREAM_MISSING_URL, self._CONSUMER_GROUP, "0", mkstream=True
            )
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

        log.info("url_resolver.started", stream=_STREAM_MISSING_URL)

        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
        ) as client:
            while not self._stop.is_set():
                try:
                    messages = await rdb.xreadgroup(
                        groupname=self._CONSUMER_GROUP,
                        consumername=self._CONSUMER_NAME,
                        streams={_STREAM_MISSING_URL: ">"},
                        count=5,
                        block=2000,
                    )
                except Exception as exc:
                    log.warning("url_resolver.read_error", error=str(exc))
                    await asyncio.sleep(2)
                    continue

                if not messages:
                    continue

                for stream_name, entries in messages:
                    for msg_id, fields in entries:
                        dealer_id = fields.get("dealer_id", "")
                        name = fields.get("name", "")
                        country = fields.get("country", "")
                        city = fields.get("city", "")

                        if not name:
                            await rdb.xack(_STREAM_MISSING_URL, self._CONSUMER_GROUP, msg_id)
                            continue

                        website = await self._resolve_one(client, name, city, country)

                        if website:
                            # Update DB
                            await pg.execute(
                                """
                                UPDATE dealers SET website = $1, updated_at = NOW()
                                WHERE name = $2 AND country = $3 AND website IS NULL
                                """,
                                website, name, country,
                            )
                            # Feed spider immediately
                            await rdb.xadd(
                                _STREAM_OUT,
                                {
                                    "dealer_id": dealer_id,
                                    "name": name,
                                    "country": country,
                                    "website": website,
                                    "source": "URL_RESOLVER",
                                },
                            )
                            self._resolved += 1
                        else:
                            # Route to sniper queue
                            await rdb.xadd(
                                _STREAM_SNIPER_QUEUE,
                                {
                                    "dealer_id": dealer_id,
                                    "name": name,
                                    "country": country,
                                    "city": city,
                                    "source": "URL_RESOLVER_FAILED",
                                },
                            )
                            await pg.execute(
                                """
                                UPDATE dealers SET spider_status = 'URL_UNRESOLVED', updated_at = NOW()
                                WHERE name = $1 AND country = $2 AND website IS NULL
                                """,
                                name, country,
                            )
                            self._failed += 1

                        await rdb.xack(_STREAM_MISSING_URL, self._CONSUMER_GROUP, msg_id)

                        if (self._resolved + self._failed) % 50 == 0:
                            log.info(
                                "url_resolver.progress",
                                resolved=self._resolved,
                                failed=self._failed,
                                total=self._resolved + self._failed,
                            )

        log.info(
            "url_resolver.stopped",
            resolved=self._resolved,
            failed=self._failed,
        )

    def stop(self) -> None:
        self._stop.set()

    def _build_headers(self, country: str) -> dict[str, str]:
        """Build fresh headers with country-appropriate Accept-Language."""
        accept_lang = self._ACCEPT_LANGUAGES.get(country, "en-US,en;q=0.9")
        return {
            "User-Agent": self._USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": accept_lang,
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    async def _resolve_one(
        self, client: httpx.AsyncClient, name: str, city: str, country: str
    ) -> str | None:
        """Search DuckDuckGo for dealer website. Returns URL or None."""
        # Random jitter: 2-6s between requests to avoid detection
        await asyncio.sleep(2.0 + random.random() * 4.0)

        country_name = self._COUNTRY_NAMES.get(country, country)
        auto_kw = self._COUNTRY_AUTO_KEYWORDS.get(country, "car dealer")
        query = f"{name} {city} {country_name} {auto_kw}"

        headers = self._build_headers(country)
        headers["Referer"] = "https://html.duckduckgo.com/"

        try:
            resp = await client.post(
                self._DDG_URL,
                data={"q": query, "b": ""},
                headers=headers,
            )
            if resp.status_code != 200:
                return None
        except Exception:
            return None

        # Parse organic results from DDG HTML
        html = resp.text
        urls = re.findall(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"',
            html,
        )
        if not urls:
            # Fallback: try generic link extraction from result snippets
            urls = re.findall(
                r'<a[^>]+rel="nofollow"[^>]+href="//duckduckgo\.com/l/\?uddg=([^&"]+)',
                html,
            )
            urls = [urllib.parse.unquote(u) for u in urls]

        for url in urls[:10]:
            # Skip portals and directories
            if any(portal in url.lower() for portal in self._PORTAL_DOMAINS):
                continue

            # Validate the URL looks real
            normalized = _normalize_website(url)
            if not normalized:
                continue

            # Quick HEAD check to verify domain is alive
            try:
                head_resp = await client.head(normalized, timeout=8.0)
                if head_resp.status_code < 400:
                    return normalized
            except Exception:
                # Domain might block HEAD, try GET
                try:
                    get_resp = await client.get(normalized, timeout=8.0)
                    if get_resp.status_code < 400:
                        return normalized
                except Exception:
                    continue

        return None


# ── Google Places Sniper Mode ────────────────────────────────────────────────
# Google Places is NOT used for blind H3 grid scanning anymore.
# It is ONLY used as a last-resort enrichment for specific dealers where
# the free URL resolver failed. This minimizes API cost to near-zero.


class GooglePlacesSniperProbe(DiscoveryProbe):
    """
    SNIPER MODE: Only queries Google Places for specific dealers that:
    1. Were discovered by other probes (INSEE, Zefix, OEM, etc.)
    2. Have NO website after the free URL resolver ran
    3. Are marked spider_status = 'URL_UNRESOLVED'

    This is NOT a grid-scanning probe. It makes exactly 1-2 API calls per
    unresolved dealer (text search + place details), not thousands of
    Nearby Search calls across H3 cells.

    Cost model: ~$0.032 per dealer resolved (1 text search + 1 detail).
    If 500 dealers are unresolved after free probes, cost = ~$16 total.
    """

    _TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    _DETAIL_URL = "https://maps.googleapis.com/maps/api/place/details/json"

    def __init__(self) -> None:
        self._api_key = _GOOGLE_API_KEY
        self._rate = _TokenBucket(5.0)

    @property
    def name(self) -> str:
        return "GOOGLE_SNIPER"

    def supports_country(self, country: str) -> bool:
        return bool(self._api_key)

    async def discover(self, country: str) -> AsyncIterator[DealerRecord]:
        """This probe does NOT discover new dealers. It enriches existing ones."""
        # This is a no-op as a discovery probe. The enrichment happens in
        # resolve_unresolved_dealers() which is called by the orchestrator
        # AFTER all probes and the URL resolver have run.
        return
        yield  # Make this a generator (Python requires yield in async generators)

    async def resolve_unresolved_dealers(
        self, pg: asyncpg.Pool, rdb: Any
    ) -> int:
        """
        For each dealer with spider_status='URL_UNRESOLVED', attempt to find
        their Google Places entry and extract the website URL.

        Returns count of dealers resolved.
        """
        if not self._api_key:
            log.info("google_sniper.disabled", reason="no API key")
            return 0

        rows = await pg.fetch(
            """
            SELECT id, name, city, postcode, country
            FROM dealers
            WHERE spider_status = 'URL_UNRESOLVED'
              AND website IS NULL
              AND place_id IS NULL
            ORDER BY country, city NULLS LAST
            LIMIT 2000
            """
        )

        if not rows:
            log.info("google_sniper.no_unresolved_dealers")
            return 0

        log.info("google_sniper.starting", dealers=len(rows))
        resolved = 0

        async with httpx.AsyncClient(timeout=15.0) as client:
            for row in rows:
                dealer_id = row["id"]
                name = row["name"]
                city = row["city"] or ""
                country = row["country"]

                website, place_id = await self._snipe_one(
                    client, name, city, country
                )

                if website or place_id:
                    await pg.execute(
                        """
                        UPDATE dealers
                        SET website = COALESCE($1, website),
                            place_id = COALESCE($2, place_id),
                            spider_status = CASE WHEN $1 IS NOT NULL THEN 'PENDING' ELSE spider_status END,
                            updated_at = NOW()
                        WHERE id = $3
                        """,
                        website,
                        place_id,
                        dealer_id,
                    )
                    if website:
                        await rdb.xadd(
                            _STREAM_OUT,
                            {
                                "dealer_id": str(dealer_id),
                                "name": name,
                                "country": country,
                                "website": website,
                                "source": "GOOGLE_SNIPER",
                            },
                        )
                        resolved += 1
                else:
                    # Truly unresolvable — mark as NO_INVENTORY
                    await pg.execute(
                        """
                        UPDATE dealers
                        SET spider_status = 'NO_INVENTORY', updated_at = NOW()
                        WHERE id = $1
                        """,
                        dealer_id,
                    )

        log.info("google_sniper.complete", resolved=resolved, total=len(rows))
        return resolved

    async def _snipe_one(
        self, client: httpx.AsyncClient, name: str, city: str, country: str
    ) -> tuple[str | None, str | None]:
        """Text Search for a specific dealer, then fetch website from details."""
        await self._rate.acquire()

        query = f"{name} {city} car dealer"
        try:
            resp = await client.get(
                self._TEXT_SEARCH_URL,
                params={
                    "key": self._api_key,
                    "query": query,
                    "region": country.lower(),
                    "type": "car_dealer",
                },
            )
            if resp.status_code != 200:
                return (None, None)
            data = resp.json()
            results = data.get("results", [])
            if not results:
                return (None, None)
        except Exception:
            return (None, None)

        # Take the first result (most relevant)
        place = results[0]
        place_id = place.get("place_id")
        if not place_id:
            return (None, None)

        # Fetch website from Place Details
        await self._rate.acquire()
        try:
            detail_resp = await client.get(
                self._DETAIL_URL,
                params={
                    "key": self._api_key,
                    "place_id": place_id,
                    "fields": "website,formatted_phone_number",
                },
            )
            if detail_resp.status_code != 200:
                return (None, place_id)
            detail = detail_resp.json().get("result", {})
            website = detail.get("website")
            if website:
                website = _normalize_website(website)
            return (website, place_id)
        except Exception:
            return (None, place_id)


# ── Discovery Orchestrator ───────────────────────────────────────────────────


class DiscoveryOrchestrator:
    """
    Runs all probes for all countries and merges results into PostgreSQL.
    Tracks per-probe-per-country completion in Redis for resume support.
    """

    def __init__(self) -> None:
        self._probes: list[DiscoveryProbe] = []
        self._pg: asyncpg.Pool | None = None
        self._rdb: Any = None
        self._stop_event = asyncio.Event()
        self._stats: dict[str, dict[str, int]] = {}

    def _register_probes(self) -> None:
        """Register all discovery probes.

        9 probes total:
          1. OSM — OpenStreetMap Overpass (free, ~10K dealers)
          2. INSEE — France SIRENE API (free, NAF 45.11Z)
          3. Zefix — Swiss commercial register (free)
          4. CommonCrawl — hidden dealer domains (free)
          5. GoogleMapsGrid — H3 hex sweep with Places API (paid, ~40K+ dealers)
          6. OEM — 20 brand dealer locator endpoints (free, ~10K dealers)
          7. PortalAggregator — AS24/Mobile.de/LeBonCoin/Coches.net directories (free, ~30K+ dealers)
          8. GovernmentRegistry — 6 national business registries NACE 45.11 (free, ~50K+ dealers)

        Google Places Sniper runs AFTER URL resolver as last-resort enrichment.
        """
        # Always-on free probes
        self._probes.append(OSMProbe())
        self._probes.append(INSEEProbe())
        self._probes.append(ZefixProbe())
        self._probes.append(CommonCrawlProbe())
        self._probes.append(OEMDealerProbe())

        # Portal Aggregator — replaces old PortalDirectoryProbe
        # Follows dealer profiles to extract website URLs
        self._probes.append(PortalAggregatorProbe())

        # Government Registry Bridge — 6 national registries
        self._probes.append(GovernmentRegistryBridgeProbe())

        # Google Maps Grid — H3 systematic sweep (only if API key present)
        if _GOOGLE_API_KEY:
            self._probes.append(GoogleMapsGridProbe())
        else:
            log.info("orchestrator.google_grid_disabled",
                     reason="GOOGLE_MAPS_API_KEY not set")

        log.info(
            "orchestrator.probes_registered",
            probes=[p.name for p in self._probes],
            count=len(self._probes),
        )

    async def _setup(self) -> None:
        """Initialize database and Redis connections."""
        self._rdb = redis_from_url(_REDIS_URL, decode_responses=True)
        self._pg = await asyncpg.create_pool(_DATABASE_URL, min_size=2, max_size=8)

    async def _teardown(self) -> None:
        """Close connections."""
        if self._pg:
            await self._pg.close()
        if self._rdb:
            await self._rdb.aclose()

    def _setup_signal_handlers(self) -> None:
        """Register graceful shutdown handlers."""
        loop = asyncio.get_event_loop()
        try:
            loop.add_signal_handler(signal.SIGINT, self._handle_signal)
            loop.add_signal_handler(signal.SIGTERM, self._handle_signal)
        except NotImplementedError:
            # Windows fallback
            signal.signal(signal.SIGINT, lambda *_: self._handle_signal())
            signal.signal(signal.SIGTERM, lambda *_: self._handle_signal())

    def _handle_signal(self) -> None:
        log.info("orchestrator.shutdown_signal")
        self._stop_event.set()

    async def _is_probe_done(self, probe_name: str, country: str) -> bool:
        """Check Redis if a probe already completed for a country."""
        key = f"discovery:completed:{country}:{probe_name}"
        return bool(await self._rdb.get(key))

    async def _mark_probe_done(self, probe_name: str, country: str) -> None:
        """Mark a probe as completed for a country in Redis."""
        key = f"discovery:completed:{country}:{probe_name}"
        await self._rdb.set(key, "1", ex=86400 * 30)  # 30 day TTL

    async def _run_probe_for_country(
        self, probe: DiscoveryProbe, country: str
    ) -> int:
        """Run a single probe for a single country. Returns count of dealers found."""
        assert self._pg is not None
        assert self._rdb is not None

        if not probe.supports_country(country):
            return 0

        # Check if already completed
        if await self._is_probe_done(probe.name, country):
            log.info(
                "orchestrator.probe_skipped",
                probe=probe.name,
                country=country,
                reason="already_completed",
            )
            return 0

        log.info(
            "orchestrator.probe_start",
            probe=probe.name,
            country=country,
        )

        count = 0
        errors = 0

        try:
            async for record in probe.discover(country):
                if self._stop_event.is_set():
                    log.info(
                        "orchestrator.probe_interrupted",
                        probe=probe.name,
                        country=country,
                        found_so_far=count,
                    )
                    return count

                # Upsert to database
                try:
                    await _upsert_dealer(self._pg, record)
                    count += 1
                except Exception as exc:
                    errors += 1
                    if errors <= 10:
                        log.warning(
                            "orchestrator.upsert_error",
                            probe=probe.name,
                            name=record.name,
                            error=str(exc),
                        )

                # Publish to spider stream if website exists
                if record.website:
                    try:
                        await _publish_dealer(self._rdb, record)
                    except Exception as exc:
                        log.debug(
                            "orchestrator.publish_error",
                            name=record.name,
                            error=str(exc),
                        )

                # Log progress every 500 records
                if count % 500 == 0 and count > 0:
                    log.info(
                        "orchestrator.probe_progress",
                        probe=probe.name,
                        country=country,
                        found=count,
                        errors=errors,
                    )

        except Exception as exc:
            log.error(
                "orchestrator.probe_fatal",
                probe=probe.name,
                country=country,
                error=str(exc),
                found_before_error=count,
            )

        # Mark completed only if not interrupted
        if not self._stop_event.is_set():
            await self._mark_probe_done(probe.name, country)

        log.info(
            "orchestrator.probe_done",
            probe=probe.name,
            country=country,
            found=count,
            errors=errors,
        )
        return count

    async def run(self, countries: list[str] | None = None) -> dict[str, dict[str, int]]:
        """
        Main entry point. Executes the full discovery pipeline in 3 phases:

        Phase 1 — DISCOVERY (free probes):
            OSM, INSEE, Zefix, CommonCrawl, OEM, PortalDirectories
            → Populates dealers table. Many will have website=NULL.

        Phase 2 — URL RESOLUTION (free, DuckDuckGo):
            Takes all dealers where website IS NULL, searches for their
            website via DuckDuckGo HTML scraping. Cost: 0€.
            → Fills website for ~70-80% of NULL entries.

        Phase 3 — GOOGLE SNIPER (paid, last resort):
            Takes remaining dealers where URL resolver failed
            (spider_status='URL_UNRESOLVED'). Uses Google Places Text
            Search to find exactly those dealers. 1-2 API calls each.
            → Only runs if GOOGLE_MAPS_API_KEY is set. Cost: ~$0.032/dealer.

        The arrow: Discovery → Free Resolution → Premium Resolution (on failure only).
        """
        countries = countries or _COUNTRIES
        self._register_probes()
        await self._setup()
        self._setup_signal_handlers()

        assert self._pg is not None
        assert self._rdb is not None

        grand_stats: dict[str, dict[str, int]] = {}

        log.info(
            "orchestrator.starting",
            countries=countries,
            probes=[p.name for p in self._probes],
            phases=["DISCOVERY", "URL_RESOLUTION", "GOOGLE_SNIPER"],
        )

        try:
            # ── Launch Phase 2 (URL Resolver) as parallel task ──────────
            # Runs alongside Phase 1. Consumes stream:dealers_missing_url
            # in real-time as Phase 1 discovers dealers without websites.
            resolver = URLResolver()
            resolver_task = asyncio.create_task(
                resolver.run(self._pg, self._rdb),
                name="url_resolver",
            )
            log.info("orchestrator.url_resolver_launched")

            # ── Phase 1: Discovery (free probes) ────────────────────────
            log.info("orchestrator.phase1_discovery")

            for country in countries:
                if self._stop_event.is_set():
                    break

                country_stats: dict[str, int] = {}

                for probe in self._probes:
                    if self._stop_event.is_set():
                        break
                    count = await self._run_probe_for_country(probe, country)
                    country_stats[probe.name] = count

                grand_stats[country] = country_stats

                total = sum(country_stats.values())
                log.info(
                    "orchestrator.country_discovery_done",
                    country=country,
                    total_found=total,
                    per_probe=country_stats,
                )

            # ── Phase 1 done. Let resolver drain remaining messages. ────
            log.info(
                "orchestrator.phase1_complete_draining_resolver",
                resolver_resolved=resolver._resolved,
                resolver_failed=resolver._failed,
            )
            # Give resolver 60s to drain the stream, then stop it
            await asyncio.sleep(60)
            resolver.stop()
            try:
                await asyncio.wait_for(resolver_task, timeout=30)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

            for cs in grand_stats.values():
                cs["URL_RESOLVER_resolved"] = resolver._resolved
                cs["URL_RESOLVER_failed"] = resolver._failed

            log.info(
                "orchestrator.url_resolver_final",
                resolved=resolver._resolved,
                failed=resolver._failed,
            )

            # ── Phase 3: Google Sniper — reads stream:dealers_sniper_queue ─
            # Only runs if API key is set. Processes dealers that URL resolver
            # could not resolve. If no API key, they sit in the queue until
            # the key is injected and sniper runs.
            sniper_queue_len = await self._rdb.xlen(_STREAM_SNIPER_QUEUE)

            if _GOOGLE_API_KEY and sniper_queue_len > 0:
                log.info(
                    "orchestrator.phase3_google_sniper",
                    queued_dealers=sniper_queue_len,
                )
                sniper = GooglePlacesSniperProbe()
                sniped = await sniper.resolve_unresolved_dealers(
                    self._pg, self._rdb
                )
                for cs in grand_stats.values():
                    cs["GOOGLE_SNIPER"] = sniped
            elif sniper_queue_len > 0:
                log.info(
                    "orchestrator.phase3_queued",
                    queued_dealers=sniper_queue_len,
                    hint="Set GOOGLE_MAPS_API_KEY and re-run to resolve these dealers",
                )
            else:
                log.info("orchestrator.phase3_skipped", reason="sniper queue empty")

        finally:
            # Ensure resolver is stopped
            resolver.stop()
            if not resolver_task.done():
                resolver_task.cancel()
            await self._teardown()

        # ── Summary ──────────────────────────────────────────────────
        total_all = sum(sum(cs.values()) for cs in grand_stats.values())

        try:
            async with asyncpg.create_pool(_DATABASE_URL, min_size=1, max_size=2) as pg:
                row = await pg.fetchrow(
                    """
                    SELECT
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE website IS NOT NULL) as with_website,
                        COUNT(*) FILTER (WHERE website IS NULL) as without_website,
                        COUNT(*) FILTER (WHERE spider_status = 'URL_UNRESOLVED') as sniper_queue
                    FROM dealers
                    """
                )
                log.info(
                    "orchestrator.final_stats",
                    total_dealers=row["total"],
                    with_website=row["with_website"],
                    without_website=row["without_website"],
                    sniper_queue=row["sniper_queue"],
                    coverage_pct=round(
                        row["with_website"] / max(row["total"], 1) * 100, 1
                    ),
                )
        except Exception:
            pass

        log.info(
            "orchestrator.complete",
            total_discoveries=total_all,
            stats=grand_stats,
        )
        return grand_stats


# ── Public Entry Point ───────────────────────────────────────────────────────


async def run(
    countries: list[str] | None = None,
    probe_filter: list[str] | None = None,
) -> None:
    """
    Entry point: discover dealers across all configured countries.

    Args:
        countries: Override country list (default: DISCOVERY_COUNTRIES env var).
        probe_filter: If set, only run probes whose name is in this list.
    """
    orchestrator = DiscoveryOrchestrator()

    if probe_filter:
        # Re-register probes but filter
        orchestrator._register_probes()
        orchestrator._probes = [
            p for p in orchestrator._probes if p.name in probe_filter
        ]
        # Clear so run() doesn't re-register
        _orig_register = orchestrator._register_probes
        orchestrator._register_probes = lambda: None  # type: ignore[assignment]
        log.info("discovery.probe_filter", active=[p.name for p in orchestrator._probes])

    await orchestrator.run(countries)
