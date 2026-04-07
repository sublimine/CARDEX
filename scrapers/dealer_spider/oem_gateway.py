"""
OEM Gateway — centralized inventory extraction from manufacturer platforms.

OEM franchise dealers don't have independent inventory pages. Their stock
lives on the brand's central used-car platform (e.g. bmw.de/gebrauchtwagen,
mercedes-benz.de/fahrzeuge/gebrauchtwagen). Scraping each dealer individually
is wasteful — they all redirect to the same ecosystem.

This module queries OEM used-car APIs at NATIONAL level:
  - "Give me all used cars in Germany from BMW" → one API call
  - Response contains dealer_id/location per vehicle
  - We reconcile each vehicle back to its physical dealer in our DB

Supported OEM groups:
  - BMW Group (BMW, MINI)
  - VAG (VW, Audi, Porsche, SEAT, Skoda, CUPRA)
  - Mercedes-Benz (Mercedes, Smart)
  - Stellantis (Peugeot, Citroën, Opel, Fiat, Jeep, Alfa Romeo, DS)
  - Renault Group (Renault, Dacia)
  - Toyota/Lexus
  - Hyundai/Kia
  - Ford, Volvo, Nissan, Honda, Mazda

Architecture:
  1. For each OEM, query their used-car search API with country filter
  2. Parse the vehicle JSON (make, model, year, price, mileage, URL, dealer info)
  3. Reconcile dealer info against our dealers table (by name, city, oem_dealer_id)
  4. Publish each vehicle to the pipeline via GatewayClient
  5. Update dealer spider_status from OEM_FRANCHISE to DONE

Runs as a standalone service, separate from the main spider.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from typing import Any, AsyncIterator
from urllib.parse import urljoin

import asyncpg
import httpx
from redis.asyncio import from_url as redis_from_url

from scrapers.common.gateway_client import GatewayClient
from scrapers.common.models import RawListing

log = logging.getLogger("oem_gateway")

_DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex@localhost:5432/cardex")
_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
_CONCURRENCY = int(os.environ.get("OEM_GATEWAY_CONCURRENCY", "3"))

# ── OEM Used-Car API Endpoints ───────────────────────────────────────────────
# Each entry defines how to query a brand's used-car search API.
# These are the XHR/REST endpoints behind their "Gebrauchtwagen"/"Occasion" pages.

_OEM_USED_CAR_APIS: list[dict[str, Any]] = [
    # ── BMW Group ────────────────────────────────────────────────────────
    {
        "brand": "BMW",
        "group": "BMW_GROUP",
        "countries": {
            "DE": {
                "url": "https://www.bmw.de/de/ssl/used-car-search.html",
                "api": "https://www.bmw.de/used-api/search",
                "params": {"country": "DE", "brand": "BM", "pageSize": 100, "page": 0},
            },
            "FR": {
                "url": "https://www.bmw.fr/fr/ssl/used-car-search.html",
                "api": "https://www.bmw.fr/used-api/search",
                "params": {"country": "FR", "brand": "BM", "pageSize": 100, "page": 0},
            },
            "ES": {
                "url": "https://www.bmw.es/es/ssl/used-car-search.html",
                "api": "https://www.bmw.es/used-api/search",
                "params": {"country": "ES", "brand": "BM", "pageSize": 100, "page": 0},
            },
            "NL": {
                "api": "https://www.bmw.nl/used-api/search",
                "params": {"country": "NL", "brand": "BM", "pageSize": 100, "page": 0},
            },
            "BE": {
                "api": "https://www.bmw.be/used-api/search",
                "params": {"country": "BE", "brand": "BM", "pageSize": 100, "page": 0},
            },
            "CH": {
                "api": "https://www.bmw.ch/used-api/search",
                "params": {"country": "CH", "brand": "BM", "pageSize": 100, "page": 0},
            },
        },
        "parser": "_parse_bmw",
    },
    # ── Mercedes-Benz ────────────────────────────────────────────────────
    {
        "brand": "MERCEDES",
        "group": "MERCEDES",
        "countries": {
            "DE": {
                "api": "https://search.2-3.mercedes-benz.com/vehicle-search/v2/search",
                "params": {"market": "de-DE", "pageSize": 100, "page": 1, "category": "used"},
            },
            "FR": {
                "api": "https://search.2-3.mercedes-benz.com/vehicle-search/v2/search",
                "params": {"market": "fr-FR", "pageSize": 100, "page": 1, "category": "used"},
            },
            "ES": {
                "api": "https://search.2-3.mercedes-benz.com/vehicle-search/v2/search",
                "params": {"market": "es-ES", "pageSize": 100, "page": 1, "category": "used"},
            },
            "NL": {
                "api": "https://search.2-3.mercedes-benz.com/vehicle-search/v2/search",
                "params": {"market": "nl-NL", "pageSize": 100, "page": 1, "category": "used"},
            },
            "BE": {
                "api": "https://search.2-3.mercedes-benz.com/vehicle-search/v2/search",
                "params": {"market": "fr-BE", "pageSize": 100, "page": 1, "category": "used"},
            },
            "CH": {
                "api": "https://search.2-3.mercedes-benz.com/vehicle-search/v2/search",
                "params": {"market": "de-CH", "pageSize": 100, "page": 1, "category": "used"},
            },
        },
        "parser": "_parse_mercedes",
    },
    # ── Volkswagen ───────────────────────────────────────────────────────
    {
        "brand": "VW",
        "group": "VAG",
        "countries": {
            "DE": {
                "api": "https://www.volkswagen.de/app/used-car-search/api/v2/search",
                "params": {"pageSize": 100, "page": 0},
            },
            "FR": {
                "api": "https://www.volkswagen.fr/app/used-car-search/api/v2/search",
                "params": {"pageSize": 100, "page": 0},
            },
            "ES": {
                "api": "https://www.volkswagen.es/app/used-car-search/api/v2/search",
                "params": {"pageSize": 100, "page": 0},
            },
        },
        "parser": "_parse_vag",
    },
    # ── Audi ─────────────────────────────────────────────────────────────
    {
        "brand": "AUDI",
        "group": "VAG",
        "countries": {
            "DE": {
                "api": "https://www.audi.de/de/web/faw/plus/api/v1/used-cars/search",
                "params": {"pageSize": 100, "page": 0},
            },
            "FR": {
                "api": "https://www.audi.fr/fr/web/faw/plus/api/v1/used-cars/search",
                "params": {"pageSize": 100, "page": 0},
            },
            "ES": {
                "api": "https://www.audi.es/es/web/faw/plus/api/v1/used-cars/search",
                "params": {"pageSize": 100, "page": 0},
            },
        },
        "parser": "_parse_vag",
    },
    # ── Stellantis Group (Peugeot, Citroën, Opel, Fiat, Jeep) ───────────
    {
        "brand": "PEUGEOT",
        "group": "STELLANTIS",
        "countries": {
            "DE": {"api": "https://www.peugeot.de/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "FR": {"api": "https://www.peugeot.fr/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "ES": {"api": "https://www.peugeot.es/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "NL": {"api": "https://www.peugeot.nl/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "BE": {"api": "https://www.peugeot.be/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "CH": {"api": "https://www.peugeot.ch/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
        },
        "parser": "_parse_stellantis",
    },
    {
        "brand": "CITROEN",
        "group": "STELLANTIS",
        "countries": {
            "DE": {"api": "https://www.citroen.de/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "FR": {"api": "https://www.citroen.fr/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "ES": {"api": "https://www.citroen.es/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "NL": {"api": "https://www.citroen.nl/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "BE": {"api": "https://www.citroen.be/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "CH": {"api": "https://www.citroen.ch/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
        },
        "parser": "_parse_stellantis",
    },
    {
        "brand": "OPEL",
        "group": "STELLANTIS",
        "countries": {
            "DE": {"api": "https://www.opel.de/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "FR": {"api": "https://www.opel.fr/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "ES": {"api": "https://www.opel.es/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "NL": {"api": "https://www.opel.nl/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "BE": {"api": "https://www.opel.be/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "CH": {"api": "https://www.opel.ch/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
        },
        "parser": "_parse_stellantis",
    },
    {
        "brand": "FIAT",
        "group": "STELLANTIS",
        "countries": {
            "DE": {"api": "https://www.fiat.de/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "FR": {"api": "https://www.fiat.fr/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "ES": {"api": "https://www.fiat.es/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
        },
        "parser": "_parse_stellantis",
    },
    {
        "brand": "JEEP",
        "group": "STELLANTIS",
        "countries": {
            "DE": {"api": "https://www.jeep.de/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "FR": {"api": "https://www.jeep.fr/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "ES": {"api": "https://www.jeep.es/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
        },
        "parser": "_parse_stellantis",
    },
    # ── Renault Group (Renault, Dacia) ───────────────────────────────────
    {
        "brand": "RENAULT",
        "group": "RENAULT",
        "countries": {
            "DE": {"api": "https://www.renault.de/wired/commerce/v1/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "FR": {"api": "https://www.renault.fr/wired/commerce/v1/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "ES": {"api": "https://www.renault.es/wired/commerce/v1/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "NL": {"api": "https://www.renault.nl/wired/commerce/v1/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "BE": {"api": "https://www.renault.be/wired/commerce/v1/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "CH": {"api": "https://www.renault.ch/wired/commerce/v1/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
        },
        "parser": "_parse_renault",
    },
    {
        "brand": "DACIA",
        "group": "RENAULT",
        "countries": {
            "DE": {"api": "https://www.dacia.de/wired/commerce/v1/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "FR": {"api": "https://www.dacia.fr/wired/commerce/v1/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "ES": {"api": "https://www.dacia.es/wired/commerce/v1/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "NL": {"api": "https://www.dacia.nl/wired/commerce/v1/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "BE": {"api": "https://www.dacia.be/wired/commerce/v1/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "CH": {"api": "https://www.dacia.ch/wired/commerce/v1/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
        },
        "parser": "_parse_renault",
    },
    # ── Toyota/Lexus ─────────────────────────────────────────────────────
    {
        "brand": "TOYOTA",
        "group": "TOYOTA",
        "countries": {
            "DE": {"api": "https://www.toyota.de/api/used-cars/search", "params": {"pageSize": 100, "page": 0}},
            "FR": {"api": "https://www.toyota.fr/api/used-cars/search", "params": {"pageSize": 100, "page": 0}},
            "ES": {"api": "https://www.toyota.es/api/used-cars/search", "params": {"pageSize": 100, "page": 0}},
            "NL": {"api": "https://www.toyota.nl/api/used-cars/search", "params": {"pageSize": 100, "page": 0}},
            "BE": {"api": "https://www.toyota.be/api/used-cars/search", "params": {"pageSize": 100, "page": 0}},
            "CH": {"api": "https://www.toyota.ch/api/used-cars/search", "params": {"pageSize": 100, "page": 0}},
        },
        "parser": "_parse_toyota",
    },
    # ── Ford ─────────────────────────────────────────────────────────────
    {
        "brand": "FORD",
        "group": "FORD",
        "countries": {
            "DE": {"api": "https://www.ford.de/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "FR": {"api": "https://www.ford.fr/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
            "ES": {"api": "https://www.ford.es/api/used-vehicles/search", "params": {"pageSize": 100, "page": 0}},
        },
        "parser": "_parse_stellantis",
    },
    # ── Hyundai/Kia ──────────────────────────────────────────────────────
    {
        "brand": "HYUNDAI",
        "group": "HYUNDAI_KIA",
        "countries": {
            "DE": {"api": "https://www.hyundai.de/api/used-cars", "params": {"pageSize": 100, "page": 0}},
            "FR": {"api": "https://www.hyundai.fr/api/used-cars", "params": {"pageSize": 100, "page": 0}},
            "ES": {"api": "https://www.hyundai.es/api/used-cars", "params": {"pageSize": 100, "page": 0}},
        },
        "parser": "_parse_generic_oem",
    },
    {
        "brand": "KIA",
        "group": "HYUNDAI_KIA",
        "countries": {
            "DE": {"api": "https://www.kia.com/de/api/used-cars", "params": {"pageSize": 100, "page": 0}},
            "FR": {"api": "https://www.kia.com/fr/api/used-cars", "params": {"pageSize": 100, "page": 0}},
            "ES": {"api": "https://www.kia.com/es/api/used-cars", "params": {"pageSize": 100, "page": 0}},
        },
        "parser": "_parse_generic_oem",
    },
]


# ── Vehicle Parsers ──────────────────────────────────────────────────────────
# Each OEM returns JSON in a different schema. Parsers normalize to RawListing.

def _safe_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(float(str(val).replace(",", "").replace(".", "").strip()))
    except (ValueError, TypeError):
        return None


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def _stable_listing_id(brand: str, raw_id: str) -> str:
    return hashlib.sha256(f"{brand}:{raw_id}".encode()).hexdigest()[:16]


class OEMVehicle:
    """Intermediate parsed vehicle from an OEM API response."""
    __slots__ = (
        "make", "model", "year", "price", "mileage", "fuel", "transmission",
        "color", "source_url", "image_url", "oem_vehicle_id",
        "dealer_name", "dealer_city", "dealer_postcode", "oem_dealer_id",
    )

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        for slot in self.__slots__:
            if not hasattr(self, slot):
                setattr(self, slot, None)


def _parse_bmw(data: dict, brand: str, country: str) -> list[OEMVehicle]:
    """Parse BMW Group used-car API response."""
    vehicles: list[OEMVehicle] = []
    results = data.get("results") or data.get("vehicles") or data.get("hits") or []
    if isinstance(data.get("data"), dict):
        results = data["data"].get("results") or data["data"].get("vehicles") or results

    for item in results:
        if not isinstance(item, dict):
            continue
        dealer_info = item.get("dealer") or item.get("retailer") or {}
        vehicles.append(OEMVehicle(
            make=item.get("brand") or item.get("make") or brand,
            model=item.get("model") or item.get("modelRange") or "",
            year=_safe_int(item.get("firstRegistration", "")[:4]) if item.get("firstRegistration") else _safe_int(item.get("year")),
            price=_safe_int(item.get("price") or item.get("grossPrice") or _nested_float(item, "price", "amount")),
            mileage=_safe_int(item.get("mileage") or item.get("mileageKm")),
            fuel=item.get("fuel") or item.get("fuelType") or "",
            transmission=item.get("transmission") or item.get("gearbox") or "",
            color=item.get("color") or item.get("exteriorColor") or "",
            source_url=item.get("detailUrl") or item.get("url") or item.get("vehicleUrl") or "",
            image_url=item.get("imageUrl") or item.get("mainImage") or "",
            oem_vehicle_id=item.get("id") or item.get("vehicleId") or item.get("vin") or "",
            dealer_name=dealer_info.get("name") or dealer_info.get("dealerName") or "",
            dealer_city=dealer_info.get("city") or dealer_info.get("town") or "",
            dealer_postcode=dealer_info.get("postalCode") or dealer_info.get("zipCode") or "",
            oem_dealer_id=str(dealer_info.get("id") or dealer_info.get("dealerId") or ""),
        ))
    return vehicles


def _parse_mercedes(data: dict, brand: str, country: str) -> list[OEMVehicle]:
    """Parse Mercedes-Benz vehicle search API response."""
    vehicles: list[OEMVehicle] = []
    results = data.get("vehicles") or data.get("results") or data.get("data", {}).get("vehicles") or []

    for item in results:
        if not isinstance(item, dict):
            continue
        dealer_info = item.get("dealer") or item.get("outlet") or {}
        price_info = item.get("price") or {}
        vehicles.append(OEMVehicle(
            make="Mercedes-Benz",
            model=item.get("modelName") or item.get("model") or "",
            year=_safe_int(item.get("firstRegistration", "")[:4]) if item.get("firstRegistration") else _safe_int(item.get("modelYear")),
            price=_safe_int(price_info.get("amount") if isinstance(price_info, dict) else price_info),
            mileage=_safe_int(item.get("mileage") or item.get("mileageKm")),
            fuel=item.get("fuelType") or "",
            transmission=item.get("transmissionType") or "",
            color=item.get("exteriorColor") or "",
            source_url=item.get("detailPageUrl") or item.get("url") or "",
            image_url=item.get("imageUrl") or "",
            oem_vehicle_id=item.get("vehicleId") or item.get("id") or "",
            dealer_name=dealer_info.get("name") or "",
            dealer_city=dealer_info.get("city") or "",
            dealer_postcode=dealer_info.get("postalCode") or "",
            oem_dealer_id=str(dealer_info.get("id") or dealer_info.get("outletId") or ""),
        ))
    return vehicles


def _parse_vag(data: dict, brand: str, country: str) -> list[OEMVehicle]:
    """Parse VAG (VW/Audi/Porsche/SEAT/Skoda) used-car API response."""
    vehicles: list[OEMVehicle] = []
    results = data.get("results") or data.get("vehicles") or data.get("data", {}).get("results") or []

    for item in results:
        if not isinstance(item, dict):
            continue
        dealer_info = item.get("dealer") or item.get("partner") or {}
        vehicles.append(OEMVehicle(
            make=item.get("make") or item.get("brand") or brand,
            model=item.get("model") or item.get("modelName") or "",
            year=_safe_int(item.get("modelYear") or item.get("year")),
            price=_safe_int(item.get("price") or item.get("grossPrice")),
            mileage=_safe_int(item.get("mileage") or item.get("km")),
            fuel=item.get("fuelType") or item.get("fuel") or "",
            transmission=item.get("transmission") or item.get("gearbox") or "",
            color=item.get("exteriorColor") or item.get("color") or "",
            source_url=item.get("detailUrl") or item.get("url") or "",
            image_url=item.get("imageUrl") or item.get("mainImage") or "",
            oem_vehicle_id=item.get("id") or item.get("vehicleId") or "",
            dealer_name=dealer_info.get("name") or dealer_info.get("partnerName") or "",
            dealer_city=dealer_info.get("city") or "",
            dealer_postcode=dealer_info.get("postalCode") or dealer_info.get("zip") or "",
            oem_dealer_id=str(dealer_info.get("id") or dealer_info.get("partnerId") or ""),
        ))
    return vehicles


def _parse_stellantis(data: dict, brand: str, country: str) -> list[OEMVehicle]:
    """Parse Stellantis used-car API (Peugeot, Citroën, Opel, Fiat, Jeep, DS, Ford)."""
    vehicles: list[OEMVehicle] = []
    results = (data.get("results") or data.get("vehicles") or data.get("data", {}).get("results")
               or data.get("offers") or data.get("items") or [])

    for item in results:
        if not isinstance(item, dict):
            continue
        dealer_info = item.get("dealer") or item.get("seller") or item.get("point_of_sale") or {}
        price_val = item.get("price") or item.get("displayPrice") or item.get("grossPrice")
        if isinstance(price_val, dict):
            price_val = price_val.get("amount") or price_val.get("value")

        vehicles.append(OEMVehicle(
            make=item.get("make") or item.get("brand") or brand,
            model=item.get("model") or item.get("commercialName") or item.get("version") or "",
            year=_safe_int(item.get("year") or item.get("registrationYear") or (item.get("firstRegistrationDate", "") or "")[:4]),
            price=_safe_int(price_val),
            mileage=_safe_int(item.get("mileage") or item.get("km") or item.get("mileageKm")),
            fuel=item.get("fuel") or item.get("fuelType") or item.get("energy") or "",
            transmission=item.get("transmission") or item.get("gearbox") or "",
            color=item.get("color") or item.get("exteriorColor") or item.get("bodyColor") or "",
            source_url=item.get("url") or item.get("detailUrl") or item.get("vehicleUrl") or "",
            image_url=item.get("imageUrl") or item.get("mainImage") or item.get("photo") or "",
            oem_vehicle_id=str(item.get("id") or item.get("vehicleId") or item.get("offerId") or ""),
            dealer_name=dealer_info.get("name") or dealer_info.get("dealerName") or dealer_info.get("label") or "",
            dealer_city=dealer_info.get("city") or dealer_info.get("town") or dealer_info.get("locality") or "",
            dealer_postcode=str(dealer_info.get("postalCode") or dealer_info.get("zipCode") or dealer_info.get("zip") or ""),
            oem_dealer_id=str(dealer_info.get("id") or dealer_info.get("dealerId") or dealer_info.get("siteCode") or ""),
        ))
    return vehicles


def _parse_renault(data: dict, brand: str, country: str) -> list[OEMVehicle]:
    """Parse Renault Group used-car API (Renault, Dacia)."""
    vehicles: list[OEMVehicle] = []
    # Renault's wired/commerce API nests data differently
    results = (data.get("results") or data.get("vehicles") or data.get("data", {}).get("vehicles")
               or data.get("offers") or data.get("items") or [])

    for item in results:
        if not isinstance(item, dict):
            continue
        dealer_info = item.get("dealer") or item.get("seller") or item.get("distributeur") or {}
        price_val = item.get("price") or item.get("displayPrice")
        if isinstance(price_val, dict):
            price_val = price_val.get("amount") or price_val.get("value") or price_val.get("raw")

        vehicles.append(OEMVehicle(
            make=item.get("make") or item.get("brand") or item.get("marque") or brand,
            model=item.get("model") or item.get("commercialName") or item.get("modele") or "",
            year=_safe_int(item.get("year") or item.get("registrationYear") or (item.get("dateImmatriculation", "") or "")[:4]),
            price=_safe_int(price_val),
            mileage=_safe_int(item.get("mileage") or item.get("km") or item.get("kilometrage")),
            fuel=item.get("fuel") or item.get("fuelType") or item.get("energie") or "",
            transmission=item.get("transmission") or item.get("gearbox") or item.get("boiteVitesse") or "",
            color=item.get("color") or item.get("couleur") or "",
            source_url=item.get("url") or item.get("detailUrl") or item.get("lien") or "",
            image_url=item.get("imageUrl") or item.get("photo") or "",
            oem_vehicle_id=str(item.get("id") or item.get("vehicleId") or item.get("offerId") or ""),
            dealer_name=dealer_info.get("name") or dealer_info.get("nom") or "",
            dealer_city=dealer_info.get("city") or dealer_info.get("ville") or "",
            dealer_postcode=str(dealer_info.get("postalCode") or dealer_info.get("codePostal") or ""),
            oem_dealer_id=str(dealer_info.get("id") or dealer_info.get("rCode") or dealer_info.get("dealerId") or ""),
        ))
    return vehicles


def _parse_toyota(data: dict, brand: str, country: str) -> list[OEMVehicle]:
    """Parse Toyota/Lexus used-car API."""
    vehicles: list[OEMVehicle] = []
    results = (data.get("results") or data.get("vehicles") or data.get("data", {}).get("vehicles")
               or data.get("usedCars") or [])

    for item in results:
        if not isinstance(item, dict):
            continue
        dealer_info = item.get("dealer") or item.get("retailer") or {}
        vehicles.append(OEMVehicle(
            make=item.get("make") or item.get("brand") or brand,
            model=item.get("model") or item.get("modelName") or "",
            year=_safe_int(item.get("year") or item.get("registrationYear")),
            price=_safe_int(item.get("price") or item.get("displayPrice")),
            mileage=_safe_int(item.get("mileage") or item.get("km")),
            fuel=item.get("fuelType") or item.get("fuel") or "",
            transmission=item.get("transmission") or item.get("gearbox") or "",
            color=item.get("color") or item.get("exteriorColor") or "",
            source_url=item.get("url") or item.get("detailUrl") or "",
            image_url=item.get("imageUrl") or "",
            oem_vehicle_id=str(item.get("id") or item.get("vehicleId") or ""),
            dealer_name=dealer_info.get("name") or "",
            dealer_city=dealer_info.get("city") or "",
            dealer_postcode=str(dealer_info.get("postalCode") or ""),
            oem_dealer_id=str(dealer_info.get("id") or dealer_info.get("dealerId") or ""),
        ))
    return vehicles


def _parse_generic_oem(data: dict, brand: str, country: str) -> list[OEMVehicle]:
    """Generic OEM parser — tries common field names across all known patterns."""
    vehicles: list[OEMVehicle] = []
    # Try every known wrapper key
    results = []
    for key in ("results", "vehicles", "items", "data", "offers", "hits", "cars", "listings"):
        val = data.get(key)
        if isinstance(val, list) and val:
            results = val
            break
        if isinstance(val, dict):
            for sub_key in ("results", "vehicles", "items"):
                sub_val = val.get(sub_key)
                if isinstance(sub_val, list) and sub_val:
                    results = sub_val
                    break
            if results:
                break
    if not results and isinstance(data, list):
        results = data

    for item in results:
        if not isinstance(item, dict):
            continue
        dealer_info = item.get("dealer") or item.get("seller") or item.get("retailer") or {}
        price_val = item.get("price") or item.get("displayPrice") or item.get("grossPrice")
        if isinstance(price_val, dict):
            price_val = price_val.get("amount") or price_val.get("value")

        vehicles.append(OEMVehicle(
            make=item.get("make") or item.get("brand") or brand,
            model=item.get("model") or item.get("modelName") or "",
            year=_safe_int(item.get("year") or item.get("registrationYear") or item.get("modelYear")),
            price=_safe_int(price_val),
            mileage=_safe_int(item.get("mileage") or item.get("km") or item.get("mileageKm")),
            fuel=item.get("fuel") or item.get("fuelType") or "",
            transmission=item.get("transmission") or item.get("gearbox") or "",
            color=item.get("color") or item.get("exteriorColor") or "",
            source_url=item.get("url") or item.get("detailUrl") or "",
            image_url=item.get("imageUrl") or item.get("mainImage") or "",
            oem_vehicle_id=str(item.get("id") or item.get("vehicleId") or ""),
            dealer_name=dealer_info.get("name") or "",
            dealer_city=dealer_info.get("city") or "",
            dealer_postcode=str(dealer_info.get("postalCode") or dealer_info.get("zipCode") or ""),
            oem_dealer_id=str(dealer_info.get("id") or dealer_info.get("dealerId") or ""),
        ))
    return vehicles


def _nested_float(d: dict, *keys: str) -> float | None:
    current = d
    for k in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(k)
    return _safe_float(current)


_PARSERS = {
    "_parse_bmw": _parse_bmw,
    "_parse_mercedes": _parse_mercedes,
    "_parse_vag": _parse_vag,
    "_parse_stellantis": _parse_stellantis,
    "_parse_renault": _parse_renault,
    "_parse_toyota": _parse_toyota,
    "_parse_generic_oem": _parse_generic_oem,
}


# ── Dealer Reconciliation ────────────────────────────────────────────────────

async def _reconcile_dealer(
    pg: asyncpg.Pool,
    vehicle: OEMVehicle,
    brand: str,
    country: str,
) -> str | None:
    """
    Match an OEM vehicle's dealer info against our dealers table.
    Returns the dealer_id (place_id or generated) for the matched dealer.

    Matching priority:
      1. oem_dealer_id exact match (if we stored it from discovery)
      2. Name + city fuzzy match within same country
      3. Name + postcode match
      4. Create a stub record if no match found
    """
    dealer_name = (vehicle.dealer_name or "").strip()
    dealer_city = (vehicle.dealer_city or "").strip()
    dealer_postcode = (vehicle.dealer_postcode or "").strip()
    oem_did = (vehicle.oem_dealer_id or "").strip()

    if not dealer_name:
        return None

    # Strategy 1: Match by oem_dealer_id
    if oem_did:
        row = await pg.fetchrow(
            "SELECT id, name FROM dealers WHERE oem_dealer_id = $1 AND country = $2 LIMIT 1",
            oem_did, country,
        )
        if row:
            return str(row["id"])

    # Strategy 2: Fuzzy name + city match
    if dealer_city:
        row = await pg.fetchrow(
            """SELECT id, name FROM dealers
               WHERE country = $1
                 AND lower(city) = lower($2)
                 AND (lower(name) = lower($3) OR name ILIKE $4)
               LIMIT 1""",
            country, dealer_city, dealer_name, f"%{dealer_name[:20]}%",
        )
        if row:
            # Store oem_dealer_id for faster future matches
            if oem_did:
                await pg.execute(
                    "UPDATE dealers SET oem_dealer_id = $1, updated_at = now() WHERE id = $2",
                    oem_did, row["id"],
                )
            return str(row["id"])

    # Strategy 3: Name + postcode
    if dealer_postcode:
        row = await pg.fetchrow(
            """SELECT id, name FROM dealers
               WHERE country = $1
                 AND postcode = $2
                 AND (lower(name) = lower($3) OR name ILIKE $4)
               LIMIT 1""",
            country, dealer_postcode, dealer_name, f"%{dealer_name[:20]}%",
        )
        if row:
            if oem_did:
                await pg.execute(
                    "UPDATE dealers SET oem_dealer_id = $1, updated_at = now() WHERE id = $2",
                    oem_did, row["id"],
                )
            return str(row["id"])

    # Strategy 4: Create stub dealer record
    result = await pg.fetchrow(
        """INSERT INTO dealers (name, country, city, postcode, source, dealer_type,
                                spider_status, brand_affiliation, oem_dealer_id, created_at, updated_at)
           VALUES ($1, $2, $3, $4, $5, 'OEM_FRANCHISE', 'OEM_FRANCHISE', ARRAY[$6]::text[], $7, now(), now())
           ON CONFLICT (name, country) WHERE COALESCE(place_id,'')='' AND COALESCE(registry_id,'')='' AND COALESCE(osm_id,'')=''
           DO UPDATE SET oem_dealer_id = COALESCE(EXCLUDED.oem_dealer_id, dealers.oem_dealer_id),
                         updated_at = now()
           RETURNING id""",
        dealer_name, country, dealer_city or None, dealer_postcode or None,
        f"OEM_{brand}", brand, oem_did or None,
    )
    return str(result["id"]) if result else None


# ── OEM Gateway Engine ───────────────────────────────────────────────────────

class OEMGateway:
    """
    Queries OEM used-car APIs at national level and reconciles vehicles
    to physical dealers in our database.
    """

    def __init__(self) -> None:
        self._pg: asyncpg.Pool | None = None
        self._rdb: Any = None
        self._gateway: GatewayClient | None = None
        self._stats: dict[str, int] = {}

    async def _setup(self) -> None:
        self._pg = await asyncpg.create_pool(_DATABASE_URL, min_size=2, max_size=8)
        self._rdb = redis_from_url(_REDIS_URL, decode_responses=True)
        self._gateway = GatewayClient()

    async def _teardown(self) -> None:
        if self._gateway:
            await self._gateway.close()
        if self._pg:
            await self._pg.close()
        if self._rdb:
            await self._rdb.aclose()

    async def run(self, countries: list[str] | None = None) -> dict[str, int]:
        """Main entry: iterate all OEM APIs for all countries."""
        countries = countries or ["DE", "ES", "FR", "NL", "BE", "CH"]
        await self._setup()
        assert self._pg and self._gateway

        total_vehicles = 0
        total_reconciled = 0

        log.info("oem_gateway: starting — %d APIs × %d countries",
                 len(_OEM_USED_CAR_APIS), len(countries))

        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "application/json, */*",
                "Accept-Language": "en-US,en;q=0.9",
            },
        ) as client:
            for oem_cfg in _OEM_USED_CAR_APIS:
                brand = oem_cfg["brand"]
                parser_name = oem_cfg["parser"]
                parser_fn = _PARSERS.get(parser_name)
                if not parser_fn:
                    continue

                for country in countries:
                    country_cfg = oem_cfg.get("countries", {}).get(country)
                    if not country_cfg:
                        continue

                    api_url = country_cfg["api"]
                    base_params = country_cfg.get("params", {})

                    try:
                        vehicles = await self._fetch_all_pages(
                            client, api_url, base_params, parser_fn, brand, country,
                        )
                    except Exception as exc:
                        log.warning("oem_gateway: %s/%s API failed: %s", brand, country, exc)
                        continue

                    if not vehicles:
                        log.info("oem_gateway: %s/%s — 0 vehicles", brand, country)
                        continue

                    # Reconcile and publish
                    published = 0
                    for v in vehicles:
                        dealer_id = await _reconcile_dealer(self._pg, v, brand, country)
                        if not dealer_id:
                            continue

                        listing = RawListing(
                            source_platform=f"oem:{brand.lower()}",
                            source_listing_id=_stable_listing_id(brand, v.oem_vehicle_id or f"{v.make}{v.model}{v.year}"),
                            dealer_id=dealer_id,
                            dealer_name=v.dealer_name or "",
                            make=v.make or brand,
                            model=v.model or "",
                            year=v.year,
                            price_raw=v.price,
                            mileage_raw=v.mileage,
                            fuel=v.fuel or "",
                            transmission=v.transmission or "",
                            color=v.color or "",
                            source_url=v.source_url or "",
                            image_url=v.image_url or "",
                            country=country,
                        )

                        # Validate
                        if not listing.make or not listing.model:
                            continue
                        if listing.source_url and not listing.source_url.startswith("http"):
                            continue

                        try:
                            await self._gateway.ingest(listing)
                            published += 1
                        except Exception as exc:
                            if published == 0:
                                log.warning("oem_gateway: ingest error: %s", exc)

                    total_vehicles += len(vehicles)
                    total_reconciled += published

                    log.info("oem_gateway: %s/%s — %d vehicles, %d published",
                             brand, country, len(vehicles), published)

                    self._stats[f"{brand}_{country}"] = published

        # Update OEM_FRANCHISE dealers that got vehicles to DONE
        if self._pg:
            await self._pg.execute("""
                UPDATE dealers SET spider_status = 'DONE', updated_at = now()
                WHERE spider_status = 'OEM_FRANCHISE'
                  AND id IN (
                      SELECT DISTINCT d.id FROM dealers d
                      JOIN vehicles v ON v.dealer_name = d.name AND v.country = d.country
                      WHERE d.spider_status = 'OEM_FRANCHISE'
                  )
            """)

        await self._teardown()

        log.info("oem_gateway: complete — %d vehicles fetched, %d published",
                 total_vehicles, total_reconciled)
        return self._stats

    async def _fetch_all_pages(
        self,
        client: httpx.AsyncClient,
        api_url: str,
        base_params: dict,
        parser_fn,
        brand: str,
        country: str,
    ) -> list[OEMVehicle]:
        """Paginate through an OEM API until exhausted."""
        all_vehicles: list[OEMVehicle] = []
        seen_ids: set[str] = set()
        page = base_params.get("page", 0)
        page_size = base_params.get("pageSize", 100)
        max_pages = 200  # safety cap

        for _ in range(max_pages):
            params = {**base_params, "page": page}

            try:
                resp = await client.get(api_url, params=params)
                if resp.status_code in (403, 429):
                    log.warning("oem_gateway: %s/%s blocked at page %d (HTTP %d)",
                                brand, country, page, resp.status_code)
                    break
                if resp.status_code == 404:
                    log.info("oem_gateway: %s/%s 404 at page %d", brand, country, page)
                    break
                resp.raise_for_status()

                ct = resp.headers.get("content-type", "")
                if "json" not in ct and "javascript" not in ct:
                    # Server returned HTML instead of JSON — endpoint likely wrong
                    body_snippet = resp.text[:200].replace("\n", " ")
                    log.warning("oem_gateway: %s/%s non-JSON response (ct=%s): %s",
                                brand, country, ct, body_snippet)
                    break

                data = resp.json()

                # Log first response structure for debugging new APIs
                if page == (base_params.get("page", 0)):
                    top_keys = list(data.keys())[:10] if isinstance(data, dict) else f"list[{len(data)}]"
                    log.info("oem_gateway: %s/%s response keys: %s", brand, country, top_keys)

            except httpx.HTTPStatusError as exc:
                log.warning("oem_gateway: %s/%s HTTP %d at page %d",
                            brand, country, exc.response.status_code, page)
                break
            except json.JSONDecodeError as exc:
                body_snippet = resp.text[:200].replace("\n", " ")
                log.warning("oem_gateway: %s/%s JSON decode error: %s — body: %s",
                            brand, country, exc, body_snippet)
                break
            except Exception as exc:
                log.warning("oem_gateway: %s/%s page %d error: %s", brand, country, page, exc)
                break

            vehicles = parser_fn(data, brand, country)
            if not vehicles:
                break

            new_count = 0
            for v in vehicles:
                vid = v.oem_vehicle_id or f"{v.make}_{v.model}_{v.year}_{v.price}"
                if vid not in seen_ids:
                    seen_ids.add(vid)
                    all_vehicles.append(v)
                    new_count += 1

            if new_count == 0:
                break  # all dupes

            page += 1

            # Politeness delay
            await asyncio.sleep(1.0)

            if len(all_vehicles) % 500 == 0:
                log.info("oem_gateway: %s/%s — %d vehicles so far (page %d)",
                         brand, country, len(all_vehicles), page)

        return all_vehicles


# ── Entry Point ──────────────────────────────────────────────────────────────

async def run(countries: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [oem_gateway] %(message)s",
    )
    gateway = OEMGateway()
    stats = await gateway.run(countries)
    log.info("oem_gateway: final stats — %s", json.dumps(stats, indent=2))
