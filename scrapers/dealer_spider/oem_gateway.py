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
    # ── BMW Group — VERIFIED ENDPOINTS (recon 2026-04-07) ────────────────
    # Architecture: 2-step. First GET dealer list → extract buNos.
    # Then POST vehiclesearch with buNos in batches.
    # Handled by dedicated _harvest_bmw_group() method, not generic flow.
    {
        "brand": "BMW",
        "group": "BMW_GROUP",
        "handler": "_harvest_bmw_group",  # dedicated handler, not generic
        "countries": {
            "DE": {"lang": "de-de", "slug": "gebrauchtwagen", "category": "BM"},
            "FR": {"lang": "fr-fr", "slug": "occasions", "category": "BM"},
            "ES": {"lang": "es-es", "slug": "ocasion", "category": "BM"},
            "NL": {"lang": "nl-nl", "slug": "occasions", "category": "BM"},
            "BE": {"lang": "fr-be", "slug": "occasions", "category": "BM"},
            "CH": {"lang": "de-ch", "slug": "gebrauchtwagen", "category": "BM"},
        },
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
    Returns the dealer id as string, or None if unreconcilable.

    Matching priority:
      1. oem_dealer_id exact match
      2. Name + city fuzzy match within same country
      3. Name-only match within same country
      4. Create a stub record (always succeeds)
    """
    dealer_name = (vehicle.dealer_name or "").strip()
    dealer_city = (vehicle.dealer_city or "").strip()
    dealer_postcode = (vehicle.dealer_postcode or "").strip()
    oem_did = (vehicle.oem_dealer_id or "").strip()

    if not dealer_name:
        # Use a synthetic name if we have nothing
        if oem_did:
            dealer_name = f"{brand} Dealer {oem_did}"
        else:
            return None

    try:
        # Strategy 1: Match by oem_dealer_id
        if oem_did:
            row = await pg.fetchrow(
                "SELECT id FROM dealers WHERE oem_dealer_id = $1 AND country = $2 LIMIT 1",
                oem_did, country,
            )
            if row:
                return str(row["id"])

        # Strategy 2: Name + city
        if dealer_city:
            row = await pg.fetchrow(
                "SELECT id FROM dealers WHERE country = $1 AND lower(city) = lower($2) AND name ILIKE $3 LIMIT 1",
                country, dealer_city, f"%{dealer_name[:25]}%",
            )
            if row:
                if oem_did:
                    await pg.execute(
                        "UPDATE dealers SET oem_dealer_id = $1, updated_at = now() WHERE id = $2",
                        oem_did, row["id"],
                    )
                return str(row["id"])

        # Strategy 3: Name-only match
        row = await pg.fetchrow(
            "SELECT id FROM dealers WHERE country = $1 AND lower(name) = lower($2) LIMIT 1",
            country, dealer_name,
        )
        if row:
            if oem_did:
                await pg.execute(
                    "UPDATE dealers SET oem_dealer_id = $1, updated_at = now() WHERE id = $2",
                    oem_did, row["id"],
                )
            return str(row["id"])

        # Strategy 4: Create stub — simple INSERT, no complex ON CONFLICT
        result = await pg.fetchrow(
            """INSERT INTO dealers (name, country, city, postcode, source, dealer_type,
                                    spider_status, brand_affiliation, oem_dealer_id, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, 'OEM_FRANCHISE', 'OEM_FRANCHISE', ARRAY[$6]::text[], $7, now(), now())
               RETURNING id""",
            dealer_name, country, dealer_city or None, dealer_postcode or None,
            f"OEM_{brand}", brand, oem_did or None,
        )
        return str(result["id"]) if result else None

    except Exception as exc:
        log.warning("oem_gateway: reconcile error for '%s' (%s): %s", dealer_name, country, exc)
        return None


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

    async def _publish_vehicles(
        self, vehicles: list[OEMVehicle], brand: str, country: str,
    ) -> int:
        """Reconcile and publish vehicles to the pipeline. Returns count published."""
        assert self._pg and self._gateway
        published = 0
        failed = 0
        skip_no_dealer = 0
        skip_no_url = 0
        skip_no_model = 0
        for v in vehicles:
            dealer_id = await _reconcile_dealer(self._pg, v, brand, country)
            if not dealer_id:
                skip_no_dealer += 1
                continue

            source_url = v.source_url or ""
            if not source_url.startswith("http"):
                skip_no_url += 1
                continue

            model_name = v.model or ""
            if not model_name or not (v.make or brand):
                skip_no_model += 1
                continue

            try:
                listing = RawListing(
                    source_platform=f"oem:{brand.lower()}",
                    source_country=country,
                    source_url=source_url,
                    source_listing_id=_stable_listing_id(brand, v.oem_vehicle_id or f"{v.make}{v.model}{v.year}"),
                    make=v.make or brand,
                    model=model_name,
                    year=v.year,
                    price_raw=float(v.price) if v.price else None,
                    mileage_km=v.mileage,
                    color=v.color or None,
                    seller_type="DEALER",
                    seller_name=v.dealer_name or None,
                    photo_urls=[v.image_url] if v.image_url else [],
                    thumbnail_url=v.image_url or None,
                )
            except Exception as exc:
                if published == 0:
                    log.warning("oem_gateway: RawListing validation failed: %s (vehicle=%s)",
                                exc, v.oem_vehicle_id)
                continue

            try:
                await self._gateway.ingest(listing)
                published += 1
            except Exception as exc:
                if published + failed < 5:
                    log.warning("oem_gateway: ingest error [%d]: %s — listing=%s %s %s url=%s",
                                published + failed, exc,
                                listing.make, listing.model, listing.year,
                                listing.source_url[:80])
                failed += 1

        log.info("oem_gateway: %s/%s — %d vehicles, %d published, %d failed, skips: dealer=%d url=%d model=%d",
                 brand, country, len(vehicles), published, failed,
                 skip_no_dealer, skip_no_url, skip_no_model)
        return published

    # ── BMW Group Dedicated Handler (Hybrid Architecture) ──────────────
    #
    # Phase 1: HTTP puro → GET /dealer/showAll (sin auth)
    #          Extrae 475+ dealers con buNo, coords, address
    #
    # Phase 2: Playwright → navega al Stocklocator, deja que el JS
    #          firme la primera petición con el hash anti-CSRF,
    #          intercepta el hash, luego inyecta un loop fetch()
    #          desde page.evaluate() que pagina con el hash robado.
    #          Zero DOM rendering — puro network layer.

    _BMW_STOLO_BASE = "https://stolo-data-service.prod.stolo.eu-central-1.aws.bmw.cloud"
    _BMW_DEALERS_URL = _BMW_STOLO_BASE + "/dealer/showAll"
    _BMW_PAGE_SIZE = 12

    # Stocklocator URLs per country
    _BMW_SL_URLS = {
        "DE": "https://www.bmw.de/de-de/sl/gebrauchtwagen/results",
        "FR": "https://www.bmw.fr/fr-fr/sl/occasions/results",
        "ES": "https://www.bmw.es/es-es/sl/ocasion/results",
        "NL": "https://www.bmw.nl/nl-nl/sl/occasions/results",
        "BE": "https://www.bmw.be/fr-be/sl/occasions/results",
        "CH": "https://www.bmw.ch/de-ch/sl/gebrauchtwagen/results",
    }

    async def _harvest_bmw_group(
        self,
        client: httpx.AsyncClient,
        brand: str,
        country: str,
        country_cfg: dict,
    ) -> list[OEMVehicle]:
        lang = country_cfg["lang"]
        category = country_cfg["category"]

        # ── Phase 1: HTTP puro — dealer list (no Playwright) ────────────
        try:
            resp = await client.get(
                self._BMW_DEALERS_URL,
                params={
                    "country": country,
                    "category": category,
                    "clientid": "66_STOCK_DLO",
                    "language": lang.replace("-", "_"),
                    "slg": "true",
                },
                headers={"Accept": "application/json", "Origin": "https://www.bmw.de"},
            )
            resp.raise_for_status()
            dealer_data = resp.json()
        except Exception as exc:
            log.warning("oem_gateway: BMW/%s dealer list failed: %s", country, exc)
            return []

        included = dealer_data.get("includedDealers", [])
        bu_nos: list[str] = []
        dealer_map: dict[str, dict] = {}
        for d in included:
            key = d.get("key", "")
            if not key:
                continue
            bu_nos.append(key)
            info = {"name": d.get("name", ""), "city": d.get("city", ""), "postcode": d.get("postalCode", "")}
            dealer_map[key] = info
            dist_id = d.get("attributes", {}).get("distributionPartnerId", "")
            if dist_id:
                dealer_map[dist_id] = info
            prefix = key.split("_")[0]
            if prefix not in dealer_map:
                dealer_map[prefix] = info

        log.info("oem_gateway: BMW/%s — %d dealers loaded via HTTP", country, len(bu_nos))
        if not bu_nos:
            return []

        # ── Phase 2: Playwright session capture (hash + cookies + UA) ───
        sl_url = self._BMW_SL_URLS.get(country)
        if not sl_url:
            return []

        from playwright.async_api import async_playwright

        session_hash = ""
        search_base_url = ""
        session_cookies: list[dict] = []
        session_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            page = await browser.new_page(
                user_agent=session_ua,
                viewport={"width": 1920, "height": 1080},
                locale=lang.split("-")[0] + "-" + lang.split("-")[1].upper(),
            )
            await page.route("**/*", lambda route, req: (
                route.abort() if req.resource_type in ("image", "media", "font") else route.continue_()
            ))
            await page.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)

            # Intercept hash + original POST body from first search request
            captured: list[str] = []
            captured_post_body: list[str] = []

            captured_headers: list[dict] = []

            async def _on_req(req):
                if "/vehiclesearch/search/" in req.url and "hash=" in req.url:
                    from urllib.parse import urlparse, parse_qs
                    p = urlparse(req.url)
                    h = parse_qs(p.query).get("hash", [""])[0]
                    if h and not captured:
                        captured.append(h)
                        captured.append(f"{p.scheme}://{p.netloc}{p.path}")
                        # Capture original POST body + headers
                        try:
                            pd = req.post_data
                            if pd:
                                captured_post_body.append(pd)
                        except Exception:
                            pass
                        try:
                            captured_headers.append(dict(req.headers))
                        except Exception:
                            pass

            page.on("request", _on_req)

            log.info("oem_gateway: BMW/%s Playwright → capturing session", country)
            try:
                await page.goto(sl_url, wait_until="networkidle", timeout=60000)
                for sel in ["#onetrust-accept-btn-handler", 'button:has-text("Alle akzeptieren")']:
                    try:
                        btn = await page.query_selector(sel)
                        if btn and await btn.is_visible():
                            await btn.click()
                            await asyncio.sleep(2)
                            break
                    except Exception:
                        pass
                for _ in range(3):
                    await page.evaluate("window.scrollBy(0, 600)")
                    await asyncio.sleep(2)
                for _ in range(20):
                    if captured:
                        break
                    await asyncio.sleep(1.5)
            except Exception as exc:
                log.warning("oem_gateway: BMW/%s navigation failed: %s", country, exc)
                await browser.close()
                return []

            if len(captured) < 2:
                log.warning("oem_gateway: BMW/%s hash not captured", country)
                await browser.close()
                return []

            session_hash = captured[0]
            search_base_url = captured[1]

            # Extract cookies from browser context
            session_cookies = await page.context.cookies()
            log.info("oem_gateway: BMW/%s session captured — hash=%s...%s, %d cookies",
                     country, session_hash[:8], session_hash[-4:], len(session_cookies))

            await browser.close()

        # ── Phase 3: Python httpx siege with stolen session ─────────────
        # Transfer cookies + UA + hash to a dedicated httpx client.
        # Playwright is CLOSED — zero browser overhead from here.

        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in session_cookies)

        # Use captured headers as base, override with session cookies
        if captured_headers:
            siege_headers = dict(captured_headers[0])
            siege_headers["Cookie"] = cookie_header
            # Log captured headers for debugging
            log.info("oem_gateway: BMW/%s using %d captured headers", country, len(siege_headers))
        else:
            siege_headers = {
                "User-Agent": session_ua,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": "https://www.bmw.de",
                "Referer": sl_url,
                "Cookie": cookie_header,
            }

        async with httpx.AsyncClient(
            timeout=30.0,
            headers=siege_headers,
        ) as siege_client:
            all_vehicles: list[OEMVehicle] = []
            seen_ids: set[str] = set()
            total_count = 0

            # Use captured body as template if available, otherwise construct
            if captured_post_body:
                try:
                    original_body = json.loads(captured_post_body[0])
                    log.info("oem_gateway: BMW/%s using captured POST body template: %s",
                             country, json.dumps(original_body)[:300])
                    search_body = captured_post_body[0]
                except (json.JSONDecodeError, IndexError):
                    search_body = json.dumps({
                        "resultsContext": {"sort": [{"by": "SF_OFFER_INSTALLMENT", "order": "ASC"}]},
                        "searchContext": [{"buNos": bu_nos}],
                    })
            else:
                search_body = json.dumps({
                    "resultsContext": {"sort": [{"by": "SF_OFFER_INSTALLMENT", "order": "ASC"}]},
                    "searchContext": [{"buNos": bu_nos}],
                })

            start_index = 0
            page_size = self._BMW_PAGE_SIZE
            consecutive_errors = 0

            while consecutive_errors < 3:
                url = f"{search_base_url}?maxResults={page_size}&startIndex={start_index}&brand={brand}&hash={session_hash}"

                try:
                    resp = await siege_client.post(url, content=search_body)

                    if resp.status_code in (403, 429):
                        log.warning("oem_gateway: BMW/%s %d at startIndex=%d — refreshing session",
                                    country, resp.status_code, start_index)
                        # Token expired or rate limited — need session refresh
                        # For now, break and report what we have
                        consecutive_errors += 1
                        await asyncio.sleep(5)
                        continue

                    if resp.status_code not in (200, 201):
                        err_body = resp.text[:500] if resp.text else "(empty)"
                        log.warning("oem_gateway: BMW/%s HTTP %d at startIndex=%d — body: %s",
                                    country, resp.status_code, start_index, err_body)
                        consecutive_errors += 1
                        continue

                    data = resp.json()
                    consecutive_errors = 0

                except Exception as exc:
                    log.warning("oem_gateway: BMW/%s request error at startIndex=%d: %s",
                                country, start_index, exc)
                    consecutive_errors += 1
                    continue

                total_count = data.get("metadata", {}).get("totalCount", 0)
                hits = data.get("hits", [])

                if not hits:
                    break

                for hit in hits:
                    v = hit.get("vehicle", {})
                    doc_id = v.get("documentId", "")
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    mo = v.get("vehicleSpecification", {}).get("modelAndOption", {})
                    lc = v.get("vehicleLifeCycle", {})
                    ret = v.get("ordering", {}).get("retailData", {})
                    off = v.get("offering", {}).get("offerPrices", {})
                    media = v.get("media", {})

                    mr_desc = mo.get("modelRange", {}).get("description", {})
                    model_name = next(iter(mr_desc.values()), "") if isinstance(mr_desc, dict) else ""

                    bu_no = ret.get("buNo", "")
                    price_obj = off.get(bu_no, {}) if isinstance(off, dict) else {}
                    price = price_obj.get("offerGrossPrice") or price_obj.get("offerGrossVehiclePrice")
                    km = lc.get("mileage", {}).get("km") if isinstance(lc.get("mileage"), dict) else None
                    first_reg = v.get("ordering", {}).get("orderData", {}).get("firstRegistrationDate", "")
                    year = _safe_int(first_reg[:4]) if first_reg and len(first_reg) >= 4 else None

                    imgs = media.get("usedCarImageList") or media.get("usedCarImages") or []
                    first_img = ""
                    if isinstance(imgs, list) and imgs and isinstance(imgs[0], str):
                        first_img = imgs[0]
                    elif isinstance(imgs, dict) and imgs:
                        first_img = next(iter(imgs.values()), "")

                    dealer_info = dealer_map.get(bu_no) or dealer_map.get(bu_no.split("_")[0], {})

                    all_vehicles.append(OEMVehicle(
                        make=mo.get("brand", brand),
                        model=model_name,
                        year=year,
                        price=_safe_int(price),
                        mileage=_safe_int(km),
                        fuel=mo.get("baseFuelType", ""),
                        transmission="",
                        color="",
                        source_url=f"https://www.bmw.de/{lang}/sl/gebrauchtwagen/detail/{doc_id}",
                        image_url=first_img,
                        oem_vehicle_id=doc_id,
                        dealer_name=dealer_info.get("name", f"BMW Dealer {bu_no}"),
                        dealer_city=dealer_info.get("city", ""),
                        dealer_postcode=dealer_info.get("postcode", ""),
                        oem_dealer_id=bu_no,
                    ))

                start_index += len(hits)

                if start_index >= total_count:
                    break

                # Politeness
                await asyncio.sleep(0.5)

                if start_index % 500 == 0:
                    log.info("oem_gateway: BMW/%s — %d/%d vehicles extracted",
                             country, len(all_vehicles), total_count)

        log.info("oem_gateway: BMW/%s — %d unique vehicles from %d dealers (total available: %d)",
                 country, len(all_vehicles), len(bu_nos), total_count)
        return all_vehicles

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

                # Check for dedicated handler (e.g. BMW Group)
                handler_name = oem_cfg.get("handler")
                if handler_name:
                    handler_fn = getattr(self, handler_name, None)
                    if handler_fn:
                        for country in countries:
                            country_cfg = oem_cfg.get("countries", {}).get(country)
                            if not country_cfg:
                                continue
                            try:
                                vehicles = await handler_fn(client, brand, country, country_cfg)
                            except Exception as exc:
                                import traceback
                                log.warning("oem_gateway: %s/%s handler failed: %s\n%s",
                                            brand, country, exc, traceback.format_exc())
                                continue

                            published = await self._publish_vehicles(vehicles, brand, country)
                            total_vehicles += len(vehicles)
                            total_reconciled += published
                            self._stats[f"{brand}_{country}"] = published
                    continue

                # Generic flow for non-BMW OEMs
                parser_name = oem_cfg.get("parser", "")
                parser_fn = _PARSERS.get(parser_name)
                if not parser_fn:
                    continue

                for country in countries:
                    country_cfg = oem_cfg.get("countries", {}).get(country)
                    if not country_cfg:
                        continue

                    api_url = country_cfg.get("api", "")
                    if not api_url:
                        continue
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

                    published = await self._publish_vehicles(vehicles, brand, country)
                    total_vehicles += len(vehicles)
                    total_reconciled += published
                    self._stats[f"{brand}_{country}"] = published

        # Update OEM_FRANCHISE dealers that got vehicles to DONE
        if self._pg and total_reconciled > 0:
            try:
                await self._pg.execute("""
                    UPDATE dealers SET spider_status = 'DONE', updated_at = now()
                    WHERE spider_status = 'OEM_FRANCHISE'
                      AND id IN (
                          SELECT DISTINCT d.id FROM dealers d
                          JOIN vehicles v ON v.seller_name = d.name AND v.country = d.country
                          WHERE d.spider_status = 'OEM_FRANCHISE'
                      )
                """)
            except Exception as exc:
                log.warning("oem_gateway: reconciliation update failed: %s", exc)

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
