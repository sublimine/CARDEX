"""
Canonical vehicle schema — the single contract every portal normalizes into.

Source of truth: _research/GOLD_NUGGETS.md §6 (canonical schema, salvaged from the
previous system's extraction/internal/pipeline/types.go) and §8 (fingerprint/dedup).

Design:
  * `None` distinguishes *absent* from *zero* (§6: "Nullable pointers distinguish
    absent from zero"). A missing price is None, never 0.
  * Money is `Decimal`, never float — listing arbitrage cannot tolerate binary
    rounding drift.
  * The record is frozen: normalization produces a new object, never mutates
    (coding-style.md immutability rule).
  * `content_fingerprint` (§8) drives change detection; `price_hash` (§C1) isolates
    the price/availability axis so a PRICE_CHANGE event fires without a full diff.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class FuelType(str, Enum):
    """Canonical fuel taxonomy (GOLD_NUGGETS §7)."""

    GASOLINE = "gasoline"
    DIESEL = "diesel"
    ELECTRIC = "electric"
    HYBRID = "hybrid"
    LPG = "lpg"
    CNG = "cng"
    HYDROGEN = "hydrogen"


class Transmission(str, Enum):
    """Canonical transmission taxonomy (GOLD_NUGGETS §7)."""

    MANUAL = "manual"
    AUTOMATIC = "automatic"
    SEMI_AUTOMATIC = "semi-automatic"


class BodyType(str, Enum):
    """Canonical body taxonomy (GOLD_NUGGETS §7)."""

    SEDAN = "sedan"
    HATCHBACK = "hatchback"
    SUV = "suv"
    ESTATE = "estate"
    COUPE = "coupe"
    CONVERTIBLE = "convertible"
    VAN = "van"
    PICKUP = "pickup"


class VatMode(str, Enum):
    """Whether the price is net of VAT, gross, or unknown (GOLD_NUGGETS §6)."""

    NET = "net"
    GROSS = "gross"
    UNKNOWN = "unknown"


# Critical fields for FullSuccess (GOLD_NUGGETS §6): Make, Model, Year,
# (PriceNet OR PriceGross), SourceURL, ImageURLs(>=1). FullSuccess = >=80% of
# vehicles carry all of these. `has_critical_fields` enforces the OR on price.
CRITICAL_FIELDS: tuple[str, ...] = ("make", "model", "year", "price", "source_url", "images")


@dataclass(frozen=True)
class VehicleRecord:
    """One normalized vehicle listing. Frozen — normalization returns a new copy."""

    # ── pointers (never fingerprinted; identity, not content) ─────────────────
    source_url: str
    source_domain: str
    country: str
    source_listing_id: str | None = None

    # ── facts ─────────────────────────────────────────────────────────────────
    vin: str | None = None
    make: str | None = None
    model: str | None = None
    year: int | None = None
    mileage_km: int | None = None
    fuel_type: FuelType | None = None
    transmission: Transmission | None = None
    power_kw: int | None = None
    body_type: BodyType | None = None
    color: str | None = None
    doors: int | None = None
    seats: int | None = None

    # ── price ───────────────────────────────────────────────────────────────
    price_net: Decimal | None = None
    price_gross: Decimal | None = None
    currency: str | None = None  # ISO 4217, upper
    vat_mode: VatMode = VatMode.UNKNOWN

    # ── collections / extras ──────────────────────────────────────────────────
    images: tuple[str, ...] = ()
    equipment: tuple[str, ...] = ()
    additional: dict[str, str] = field(default_factory=dict)

    @property
    def price(self) -> Decimal | None:
        """The effective price: gross preferred, else net (GOLD_NUGGETS §6 OR rule)."""
        return self.price_gross if self.price_gross is not None else self.price_net

    def has_critical_fields(self) -> bool:
        """True when every FullSuccess field is present (price = net OR gross, >=1 image)."""
        return (
            bool(self.make)
            and bool(self.model)
            and self.year is not None
            and self.price is not None
            and bool(self.source_url)
            and len(self.images) >= 1
        )

    def missing_critical(self) -> tuple[str, ...]:
        """Which critical fields are absent — drives null_field_rate telemetry."""
        missing: list[str] = []
        if not self.make:
            missing.append("make")
        if not self.model:
            missing.append("model")
        if self.year is None:
            missing.append("year")
        if self.price is None:
            missing.append("price")
        if not self.source_url:
            missing.append("source_url")
        if len(self.images) < 1:
            missing.append("images")
        return tuple(missing)


def _norm_money(value: Decimal | None) -> str:
    """Stable money string for hashing — normalized exponent, no scientific notation."""
    if value is None:
        return ""
    return format(value.normalize(), "f")


def price_hash(record: VehicleRecord) -> str:
    """
    SHA256 over the price/availability axis (GOLD_NUGGETS §C1).

    Components: effective price · currency · vat_mode. A change here emits a
    PRICE_CHANGE event — the signal that matters for arbitrage — without a full
    content diff.
    """
    parts = (
        _norm_money(record.price),
        record.currency or "",
        record.vat_mode.value,
    )
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]


def content_fingerprint(record: VehicleRecord) -> str:
    """
    SHA256 of the full content axis (GOLD_NUGGETS §8) for change detection.

    Excludes pure pointers (source_url/domain/listing_id) so the same vehicle
    re-listed at a new URL is recognised as content-identical. Order-stable.
    """
    parts: tuple[str, ...] = (
        record.vin or "",
        record.make or "",
        record.model or "",
        str(record.year or ""),
        str(record.mileage_km or ""),
        record.fuel_type.value if record.fuel_type else "",
        record.transmission.value if record.transmission else "",
        str(record.power_kw or ""),
        record.body_type.value if record.body_type else "",
        record.color or "",
        str(record.doors or ""),
        str(record.seats or ""),
        _norm_money(record.price_net),
        _norm_money(record.price_gross),
        record.currency or "",
        record.vat_mode.value,
        "\x1e".join(record.images),
        "\x1e".join(record.equipment),
    )
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
