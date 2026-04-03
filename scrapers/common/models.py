"""
Canonical listing model — what every scraper must produce.
All fields are optional except the identifiers; normalizer fills what it can.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


FuelType = Literal["PETROL", "DIESEL", "ELECTRIC", "HYBRID_PETROL", "HYBRID_DIESEL", "LPG", "CNG", "HYDROGEN", "OTHER"]
Transmission = Literal["MANUAL", "AUTOMATIC", "SEMI_AUTO", "UNKNOWN"]
BodyType = Literal["SEDAN", "HATCHBACK", "ESTATE", "SUV", "COUPE", "CABRIO", "VAN", "PICKUP", "OTHER"]
ListingStatus = Literal["ACTIVE", "SOLD", "EXPIRED", "UNKNOWN"]


class RawListing(BaseModel):
    """
    Output contract for every scraper adapter.
    Scrapers fill what they have; pipeline normalizes and enriches the rest.

    Field aliases accepted for convenience (old naming):
      platform         → source_platform
      source_platform  → source_platform
      country          → source_country   (note: differs from location.country)
      source_country   → source_country
      listing_id       → source_listing_id
      source_listing_id→ source_listing_id
      price_eur        → price_raw (with currency_raw forced to EUR)
    """
    model_config = {"populate_by_name": True}

    # --- Identity ---
    source_platform: str                     # e.g. "autoscout24_de"
    source_country: str                      # ISO 3166-1 alpha-2, e.g. "DE"
    source_url: str                          # canonical URL of the original listing
    source_listing_id: str                   # platform-internal ID (for dedup/cursor)
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
    vin: str | None = None                   # VIN-17 if available
    power_kw: int | None = None
    co2_gkm: int | None = None
    doors: int | None = None
    seats: int | None = None

    # --- Price ---
    price_raw: float | None = None
    currency_raw: str = "EUR"               # ISO 4217

    # --- Location ---
    city: str | None = None
    region: str | None = None
    country: str | None = None              # location country (may differ from source_country)
    latitude: float | None = None
    longitude: float | None = None

    # --- Seller ---
    seller_type: Literal["DEALER", "PRIVATE", "UNKNOWN"] = "UNKNOWN"
    seller_name: str | None = None
    seller_phone: str | None = None         # NEVER stored — PII, pipeline drops it
    seller_address: str | None = None       # NEVER stored — PII, pipeline drops it

    # --- Media ---
    photo_urls: list[str] = Field(default_factory=list)
    thumbnail_url: str | None = None

    # --- Listing metadata ---
    first_seen_at: datetime | None = None
    listing_status: ListingStatus = "ACTIVE"
    description_snippet: str | None = None  # first 300 chars max, no PII

    # Internal — stripped before publishing to pipeline
    raw: Any = Field(default=None, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _handle_aliases(cls, data: Any) -> Any:
        """
        Accept legacy / shorthand field names used by scraper adapters.
        This prevents silent Pydantic validation failures when adapters
        use convenience names instead of the canonical schema names.
        """
        if not isinstance(data, dict):
            return data

        # platform= / source_platform= → source_platform
        if "platform" in data and "source_platform" not in data:
            data["source_platform"] = data.pop("platform")

        # country= → source_country (only when source_country absent)
        # Adapters that pass country= mean the listing's origin country,
        # NOT the vehicle's physical location.
        if "country" in data and "source_country" not in data:
            data["source_country"] = data.pop("country")

        # listing_id= → source_listing_id
        if "listing_id" in data and "source_listing_id" not in data:
            data["source_listing_id"] = data.pop("listing_id")

        # price_eur= → price_raw (EUR implied)
        if "price_eur" in data and "price_raw" not in data:
            data["price_raw"] = data.pop("price_eur")
            data.setdefault("currency_raw", "EUR")

        # Sanitize: reject negative or absurdly high prices
        if data.get("price_raw") is not None:
            p = data["price_raw"]
            if p is not None and (p < 0 or p > 10_000_000):
                data["price_raw"] = None

        # Sanitize: reject negative mileage
        if data.get("mileage_km") is not None and data["mileage_km"] < 0:
            data["mileage_km"] = None

        # Sanitize: year sanity check
        if data.get("year") is not None:
            y = data["year"]
            if not (1885 <= y <= datetime.utcnow().year + 1):
                data["year"] = None

        return data
