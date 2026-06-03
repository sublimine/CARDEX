"""
CARDEX pipeline — raw listing → canonical, validated VehicleRecord.

Stages (SCRAPING_ENGINE.md § C, grounded in _research/GOLD_NUGGETS.md §6-§9):

    parse      HTML/JSON → RawListing      (JSON-LD → OG/meta → heuristics cascade)
    normalize  RawListing → VehicleRecord  (canonical enums, numeric coercion)
    quality    VehicleRecord → Verdict     (structural · poison · coherence · staleness)
    delta      URL set + price hash → DeltaResult (new / gone / price-change)
    dlq        failure → engine.db dlq      (per-reason recovery routing)

Every stage is a pure function (or a thin DB writer) so the whole pipeline is
unit-testable without Postgres, Redis, or a live network — the decoupling the
previous monolith lacked.
"""
from __future__ import annotations

from scrapers.pipeline.schema import (
    CRITICAL_FIELDS,
    BodyType,
    FuelType,
    Transmission,
    VatMode,
    VehicleRecord,
    content_fingerprint,
    price_hash,
)

__all__ = [
    "VehicleRecord",
    "FuelType",
    "Transmission",
    "BodyType",
    "VatMode",
    "CRITICAL_FIELDS",
    "content_fingerprint",
    "price_hash",
]
