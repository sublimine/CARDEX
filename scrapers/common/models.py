"""
Canonical listing model — what every scraper must produce.
All fields are optional except the identifiers; normalizer fills what it can.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


FuelType = Literal["PETROL", "DIESEL", "ELECTRIC", "HYBRID_PETROL", "HYBRID_DIESEL", "LPG", "CNG", "HYDROGEN", "OTHER"]
Transmission = Literal["MANUAL", "AUTOMATIC", "SEMI_AUTO", "UNKNOWN"]
BodyType = Literal["SEDAN", "HATCHBACK", "ESTATE", "SUV", "COUPE", "CABRIO", "VAN", "PICKUP", "OTHER"]
ListingStatus = Literal["ACTIVE", "SOLD", "EXPIRED", "UNKNOWN"]


class RawListing(BaseModel):
    """
    Output contract for every scraper adapter.
    Scrapers fill what they have; pipeline normalizes and enriches the rest.
    """
    # --- Identity ---
    source_platform: str                    # e.g. "autoscout24_de"
    source_country: str                     # ISO 3166-1 alpha-2, e.g. "DE"
    source_url: str                         # canonical URL of the original listing
    source_listing_id: str                  # platform-internal ID (for dedup/cursor)
    scraped_at: datetime = Field(default_factory=datetime.utcnow)

    # --- Vehicle ---
    make: str | None = None
    model: str | None = None
    variant: str | None = None
    year: int | None = None
    mileage_km: int | None = None
    fuel_type: FuelType | None = None
    transmission: Transmission | None = None
    body_type: BodyType | None = None
    color: str | None = None
    power_kw: int | None = None
    co2_gkm: int | None = None
    doors: int | None = None
    seats: int | None = None

    # --- Price ---
    price_raw: float | None = None
    currency_raw: str = "EUR"              # ISO 4217

    # --- Location ---
    city: str | None = None
    region: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    # --- Seller ---
    seller_type: Literal["DEALER", "PRIVATE", "UNKNOWN"] = "UNKNOWN"
    seller_name: str | None = None
    seller_phone: str | None = None        # NEVER stored — PII, pipeline drops it
    seller_address: str | None = None      # NEVER stored — PII, pipeline drops it

    # --- Media ---
    photo_urls: list[str] = Field(default_factory=list)
    thumbnail_url: str | None = None

    # --- Listing metadata ---
    first_seen_at: datetime | None = None
    listing_status: ListingStatus = "ACTIVE"
    description_snippet: str | None = None  # first 300 chars max, no PII
