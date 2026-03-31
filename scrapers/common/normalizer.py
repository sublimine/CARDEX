"""
Normalizer utilities shared across scrapers.
- Fuel type / transmission canonicalization
- Mileage unit conversion
- Currency symbol → ISO 4217
- Price string parsing (handles "15.990 €", "£ 12,500", "15 990 EUR")
- CO2 / power extraction from raw text
"""
from __future__ import annotations

import re

from .models import FuelType, Transmission

# ---------------------------------------------------------------------------
# Fuel type
# ---------------------------------------------------------------------------

_FUEL_MAP: list[tuple[re.Pattern[str], FuelType]] = [
    (re.compile(r"electric|elektro|électrique|eléctric|100.*bev|bev", re.I), "ELECTRIC"),
    (re.compile(r"plug.?in|phev|hybrid.*petrol|petrol.*hybrid", re.I), "HYBRID_PETROL"),
    (re.compile(r"plug.?in|phev|hybrid.*diesel|diesel.*hybrid", re.I), "HYBRID_DIESEL"),
    (re.compile(r"hybrid", re.I), "HYBRID_PETROL"),  # generic hybrid → petrol hybrid
    (re.compile(r"diesel", re.I), "DIESEL"),
    (re.compile(r"petrol|essence|gasolina|benzin|benzine", re.I), "PETROL"),
    (re.compile(r"lpg|autogas|gpl|autogas", re.I), "LPG"),
    (re.compile(r"cng|gas naturel|erdgas|metano", re.I), "CNG"),
    (re.compile(r"hydrogen|wasserstoff|hydrog", re.I), "HYDROGEN"),
]


def normalize_fuel(raw: str | None) -> FuelType | None:
    if not raw:
        return None
    for pattern, fuel in _FUEL_MAP:
        if pattern.search(raw):
            return fuel
    return "OTHER"


# ---------------------------------------------------------------------------
# Transmission
# ---------------------------------------------------------------------------

_TX_MAP: list[tuple[re.Pattern[str], Transmission]] = [
    (re.compile(r"auto(matic)?|dsg|cvt|pdk|tiptronic|s.tronic|sequentiel", re.I), "AUTOMATIC"),
    (re.compile(r"semi.?auto|manumatic|robotized|r-tronic|amt", re.I), "SEMI_AUTO"),
    (re.compile(r"manual|manu[ae]l|schalt", re.I), "MANUAL"),
]


def normalize_transmission(raw: str | None) -> Transmission | None:
    if not raw:
        return None
    for pattern, tx in _TX_MAP:
        if pattern.search(raw):
            return tx
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Price parsing
# ---------------------------------------------------------------------------

_PRICE_STRIP = re.compile(r"[^\d.,]")
_PRICE_CLEAN = re.compile(r"[.,](?=\d{3}(?:[.,]|$))")  # thousands separators


def parse_price(raw: str | None) -> float | None:
    """Parse price string into float EUR value. Returns None if unparseable."""
    if not raw:
        return None
    s = raw.strip()
    # Detect currency (crude)
    # Strip non-numeric except last decimal separator
    digits_only = _PRICE_STRIP.sub("", s)
    # Remove thousands separators: if last separator appears before >= 3 trailing digits
    # Strategy: if there's a comma AND a period, the last one is decimal
    if "." in digits_only and "," in digits_only:
        if s.rfind(".") > s.rfind(","):
            # 1.234,56 → European format
            digits_only = digits_only.replace(".", "").replace(",", ".")
        else:
            # 1,234.56 → English format
            digits_only = digits_only.replace(",", "")
    elif "," in s and not "." in s:
        # Could be 15,990 (European thousands) or 15,5 (decimal)
        parts = digits_only.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            digits_only = digits_only.replace(",", ".")  # decimal
        else:
            digits_only = digits_only.replace(",", "")  # thousands
    try:
        return float(digits_only)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Mileage
# ---------------------------------------------------------------------------

def parse_mileage(raw: str | None, unit: str = "km") -> int | None:
    """Parse mileage string to km integer."""
    if not raw:
        return None
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        return None
    km = int(digits)
    if unit.lower() in ("mi", "miles"):
        km = int(km * 1.60934)
    return km


# ---------------------------------------------------------------------------
# Power / CO2
# ---------------------------------------------------------------------------

def parse_power_kw(raw: str | None) -> int | None:
    """Extract kW value from strings like '110 kW (150 PS)' or '150 HP'."""
    if not raw:
        return None
    kw_match = re.search(r"(\d+)\s*kw", raw, re.I)
    if kw_match:
        return int(kw_match.group(1))
    hp_match = re.search(r"(\d+)\s*(hp|ps|cv|ch|pk)\b", raw, re.I)
    if hp_match:
        return int(int(hp_match.group(1)) * 0.7457)
    return None


def parse_co2(raw: str | None) -> int | None:
    """Extract CO2 value from strings like '142 g/km'."""
    if not raw:
        return None
    m = re.search(r"(\d+)\s*g", raw, re.I)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Currency
# ---------------------------------------------------------------------------

_CURRENCY_MAP = {
    "€": "EUR", "eur": "EUR",
    "£": "GBP", "gbp": "GBP",
    "chf": "CHF", "fr.": "CHF",
    "$": "USD", "usd": "USD",
    "czk": "CZK", "kč": "CZK",
    "pln": "PLN", "zł": "PLN",
}


def detect_currency(raw: str | None) -> str:
    if not raw:
        return "EUR"
    lower = raw.lower()
    for symbol, iso in _CURRENCY_MAP.items():
        if symbol in lower:
            return iso
    return "EUR"
