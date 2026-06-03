"""
Quality gates — the four §C3 checks a normalized record passes before ingestion.

    GATE 1  structural validity   price/year/mileage ranges + deep-link URL
    GATE 2  poison detection      delegated to intelligence.poison.detect
    GATE 3  cross-source coherence same VIN, divergent price → discrepancy event
    GATE 4  staleness             last_seen older than 30d → automatic GONE

Every gate is a pure function. GATE 1/2 judge a single record (`evaluate`); GATE 3
operates over a batch (`coherence_discrepancies`); GATE 4 is a time comparison
(`is_stale`). Structural checks validate only *present* values — a missing field is
a completeness concern (handled by `VehicleRecord.missing_critical`), not a
validity failure, so None always passes the range checks.

GATE 2 imports the single poison implementation from the intelligence package
rather than re-deriving signals; this module never re-implements detection.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from scrapers.intelligence.poison import PoisonVerdict, detect
from scrapers.pipeline.delta import is_deep_link
from scrapers.pipeline.schema import VehicleRecord

# GATE 1 ranges (§C3). Price 0 is rejected (a "free" car is implausible/poison);
# mileage 0 is allowed (a genuinely new listing). Year ceiling is current+1 to
# admit next-model-year listings sold ahead of the calendar.
PRICE_MIN = Decimal("0")
PRICE_MAX = Decimal("500000")
YEAR_MIN = 1980
MILEAGE_MIN = 0
MILEAGE_MAX = 1_500_000

# GATE 4 (§C3): a listing unconfirmed for this many days is treated as gone.
STALE_DAYS = 30


class QualityFailure(str, Enum):
    """A specific gate failure; absence of any means the record is ingestible."""

    PRICE_OUT_OF_RANGE = "price_out_of_range"
    YEAR_OUT_OF_RANGE = "year_out_of_range"
    MILEAGE_OUT_OF_RANGE = "mileage_out_of_range"
    URL_NOT_DEEP_LINK = "url_not_deep_link"
    POISON_DETECTED = "poison_detected"


@dataclass(frozen=True)
class QualityVerdict:
    """Result of GATE 1+2 for one record. `ok` is True only with zero failures."""

    ok: bool
    failures: tuple[QualityFailure, ...]
    poison: PoisonVerdict | None = None

    @property
    def reason(self) -> str:
        """Comma-joined failure names for logs/DLQ, or 'ok' when the record passes."""
        return ", ".join(f.value for f in self.failures) if self.failures else "ok"


@dataclass(frozen=True)
class PriceDiscrepancy:
    """GATE 3 event: one VIN priced differently across sources."""

    vin: str
    prices: tuple[Decimal, ...]


def check_structural(record: VehicleRecord, *, current_year: int) -> list[QualityFailure]:
    """GATE 1 — range-validate every *present* field; None values pass through."""
    failures: list[QualityFailure] = []
    price = record.price
    if price is not None and not (PRICE_MIN < price <= PRICE_MAX):
        failures.append(QualityFailure.PRICE_OUT_OF_RANGE)
    if record.year is not None and not (YEAR_MIN <= record.year <= current_year + 1):
        failures.append(QualityFailure.YEAR_OUT_OF_RANGE)
    if record.mileage_km is not None and not (MILEAGE_MIN <= record.mileage_km <= MILEAGE_MAX):
        failures.append(QualityFailure.MILEAGE_OUT_OF_RANGE)
    if not is_deep_link(record.source_url):
        failures.append(QualityFailure.URL_NOT_DEEP_LINK)
    return failures


def evaluate(
    record: VehicleRecord,
    *,
    html: str | None = None,
    current_year: int | None = None,
    portal_always_prices: bool = False,
    portal_always_vins: bool = False,
    is_duplicate_body: bool = False,
) -> QualityVerdict:
    """
    Run GATE 1 (always) and GATE 2 (when `html` is supplied) for one record.

    Poison context is derived from the record itself — price/VIN presence — so the
    caller only states portal expectations (`portal_always_*`) and the cross-URL
    `is_duplicate_body` verdict. Returns the combined verdict; `poison` is attached
    whenever GATE 2 ran.
    """
    year_ceiling = date.today().year if current_year is None else current_year
    failures = check_structural(record, current_year=year_ceiling)

    poison: PoisonVerdict | None = None
    if html is not None:
        poison = detect(
            html,
            image_urls=record.images,
            portal_always_prices=portal_always_prices,
            price_present=record.price is not None,
            portal_always_vins=portal_always_vins,
            vin_present=bool(record.vin),
            is_duplicate_body=is_duplicate_body,
        )
        if poison.is_poison:
            failures.append(QualityFailure.POISON_DETECTED)

    return QualityVerdict(ok=not failures, failures=tuple(failures), poison=poison)


def coherence_discrepancies(records: list[VehicleRecord]) -> list[PriceDiscrepancy]:
    """
    GATE 3 — group by VIN and flag any VIN whose effective prices disagree.

    Only records carrying both a VIN and a price participate. The returned prices
    are de-duplicated and sorted so the event is stable regardless of input order.
    """
    by_vin: dict[str, set[Decimal]] = {}
    for rec in records:
        if rec.vin and rec.price is not None:
            by_vin.setdefault(rec.vin, set()).add(rec.price)
    return [
        PriceDiscrepancy(vin=vin, prices=tuple(sorted(prices)))
        for vin, prices in sorted(by_vin.items())
        if len(prices) > 1
    ]


def is_stale(last_seen: int, now: int | None = None, max_age_days: int = STALE_DAYS) -> bool:
    """GATE 4 — True when `last_seen` (epoch s) is older than `max_age_days` from now."""
    current = int(time.time()) if now is None else now
    return (current - last_seen) > max_age_days * 86_400
