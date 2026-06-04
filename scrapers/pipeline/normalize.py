"""
Normalization — raw extracted fields → canonical VehicleRecord.

Canonical enum mappings are verbatim from _research/GOLD_NUGGETS.md §7 (salvaged
from extraction/internal/normalize/vehicle.go), matched case-insensitively by
substring. Numeric parsing follows §9 E03 heuristics (price/mileage/year regexes).

Token ordering is deliberate, not alphabetical: where one category's token is a
substring of another's the more specific category is tested first, so:
  * diesel before gasoline   — "gasoil" contains the greedy "gas" token
  * hybrid before electric   — "hybrid electric" / PHEV strings carry both
  * semi-automatic before automatic — "semi-automatique" contains "automatique"
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from scrapers.pipeline.schema import (
    BodyType,
    FuelType,
    Transmission,
    VatMode,
    VehicleRecord,
)

# ── canonical token tables (GOLD_NUGGETS §7), ordered specific-first ──────────
_FUEL_TOKENS: tuple[tuple[FuelType, tuple[str, ...]], ...] = (
    (FuelType.HYBRID, ("hybrid", "hybride", "híbrido", "hibrido", "phev", "plug-in", "plugin")),
    (FuelType.ELECTRIC, ("electric", "électrique", "electrique", "eléctrico", "electrico", "elektro", "bev")),
    (FuelType.LPG, ("lpg", "gpl", "autogas")),
    (FuelType.CNG, ("cng", "gnv", "erdgas")),
    (FuelType.HYDROGEN, ("hydrogen", "wasserstoff", "hydrogène", "hydrogene")),
    (FuelType.DIESEL, ("diesel", "gazole", "gasoil")),
    (FuelType.GASOLINE, ("gasoline", "petrol", "benzin", "essence", "gasolina", "gas")),
)

_TRANSMISSION_TOKENS: tuple[tuple[Transmission, tuple[str, ...]], ...] = (
    (Transmission.SEMI_AUTOMATIC, ("semi-automatic", "semi-automatique", "robotized", "robotised")),
    (Transmission.AUTOMATIC, ("automatic", "automatique", "automático", "automatico", "automatik", "dsg", "cvt", "s tronic")),
    (Transmission.MANUAL, ("manual", "manuell", "manuelle", "schaltgetriebe", "mt")),
)

_BODY_TOKENS: tuple[tuple[BodyType, tuple[str, ...]], ...] = (
    (BodyType.CONVERTIBLE, ("convertible", "cabriolet", "cabrio", "roadster", "spider")),
    (BodyType.ESTATE, ("estate", "break", "kombi", "variant", "touring", "sw")),
    (BodyType.SUV, ("suv", "crossover", "4x4", "tout-terrain", "geländewagen", "gelandewagen")),
    (BodyType.PICKUP, ("pickup", "pick-up", "truck")),
    (BodyType.VAN, ("van", "minivan", "mpv", "monospace")),
    (BodyType.COUPE, ("coupe", "coupé", "sports")),
    (BodyType.HATCHBACK, ("hatchback", "hayon", "compacto")),
    (BodyType.SEDAN, ("sedan", "berline", "limousine", "saloon")),
)

_YEAR_RE = re.compile(r"\b(19[89]\d|20[012]\d)\b")
_DIGITS_RE = re.compile(r"\d[\d.,\s]*")

# Currency symbols / codes → ISO 4217 upper. Covers the 6 AS24 countries (EUR, CHF).
_CURRENCY_MAP = {
    "€": "EUR", "eur": "EUR", "euro": "EUR", "euros": "EUR",
    "chf": "CHF", "fr.": "CHF", "sfr": "CHF",
    "$": "USD", "usd": "USD",
    "£": "GBP", "gbp": "GBP",
}


def _match_token(raw: str | None, table) -> object | None:
    """First category whose any token is a case-insensitive substring of `raw`."""
    if not raw:
        return None
    lo = raw.lower()
    for canonical, tokens in table:
        if any(tok in lo for tok in tokens):
            return canonical
    return None


def normalize_fuel(raw: str | None) -> FuelType | None:
    return _match_token(raw, _FUEL_TOKENS)  # type: ignore[return-value]


def normalize_transmission(raw: str | None) -> Transmission | None:
    return _match_token(raw, _TRANSMISSION_TOKENS)  # type: ignore[return-value]


def normalize_body(raw: str | None) -> BodyType | None:
    return _match_token(raw, _BODY_TOKENS)  # type: ignore[return-value]


def normalize_currency(raw: str | None) -> str | None:
    """Map a symbol or loose code to ISO 4217 upper; pass through clean 3-letter codes."""
    if not raw:
        return None
    key = raw.strip().lower()
    if key in _CURRENCY_MAP:
        return _CURRENCY_MAP[key]
    alpha = re.sub(r"[^a-z]", "", key)
    if len(alpha) == 3:
        return alpha.upper()
    return None


def normalize_vin(raw: str | None) -> str | None:
    """A VIN is exactly 17 alphanumerics, uppercased — else dropped (GOLD_NUGGETS §6)."""
    if not raw:
        return None
    candidate = raw.strip().upper()
    if len(candidate) == 17 and candidate.isalnum():
        return candidate
    return None


def _strip_to_number(raw: str) -> str | None:
    """Pull the first numeric run (digits + . , and inner spaces) out of free text."""
    m = _DIGITS_RE.search(raw)
    if not m:
        return None
    return m.group(0).strip()


def parse_decimal(raw: str | float | int | None) -> Decimal | None:
    """
    Parse a monetary amount to Decimal, resolving European/US separator ambiguity.

    Rules (GOLD_NUGGETS §9 E03 price form):
      * both '.' and ',' present → the LAST one is the decimal separator.
      * a single separator followed by exactly 3 digits → thousands grouping.
      * a single separator followed by 1-2 digits → decimal point.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            value = Decimal(str(raw))
        except InvalidOperation:
            return None
        return value if value >= 0 else None
    token = _strip_to_number(raw)
    if not token:
        return None
    token = token.replace(" ", "")
    has_dot, has_comma = "." in token, "," in token
    if has_dot and has_comma:
        dec_sep = "." if token.rfind(".") > token.rfind(",") else ","
        thou_sep = "," if dec_sep == "." else "."
        token = token.replace(thou_sep, "").replace(dec_sep, ".")
    elif has_dot or has_comma:
        sep = "." if has_dot else ","
        tail = token.rsplit(sep, 1)[1]
        token = token.replace(sep, "" if len(tail) == 3 else ".")
    try:
        value = Decimal(token)
    except InvalidOperation:
        return None
    return value if value >= 0 else None


def parse_int_loose(raw: str | float | int | None) -> int | None:
    """Parse an integer count (mileage/power/doors), discarding all grouping separators."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    token = _strip_to_number(raw)
    if not token:
        return None
    digits = re.sub(r"[^\d]", "", token)
    return int(digits) if digits else None


def parse_year(raw: str | int | None) -> int | None:
    """Extract a plausible model year via the verified §9 regex (1980-2029 window)."""
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw if 1980 <= raw <= 2029 else None
    m = _YEAR_RE.search(str(raw))
    return int(m.group(1)) if m else None


def _as_tuple(value) -> tuple[str, ...]:
    """Coerce a scalar/list/None of URLs or labels into a deduped, ordered tuple."""
    if not value:
        return ()
    items = [value] if isinstance(value, str) else list(value)
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        s = str(item).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return tuple(out)


def _vat_mode(raw: dict) -> VatMode:
    value = raw.get("vat_mode")
    if isinstance(value, VatMode):
        return value
    if isinstance(value, str):
        try:
            return VatMode(value.lower())
        except ValueError:
            return VatMode.UNKNOWN
    return VatMode.UNKNOWN


def to_record(
    raw: dict,
    *,
    source_url: str,
    source_domain: str,
    country: str,
) -> VehicleRecord:
    """
    Build a canonical, frozen VehicleRecord from a parsed raw-field dict.

    Pointers (source_url/domain/country) are supplied by the caller — they are
    scrape context, not extracted content. Everything else is coerced through the
    canonical normalizers; absent or unparseable fields stay None (§6).
    """
    return VehicleRecord(
        source_url=source_url,
        source_domain=source_domain,
        country=country.upper(),
        source_listing_id=(str(raw["listing_id"]) if raw.get("listing_id") else None),
        vin=normalize_vin(raw.get("vin")),
        make=(str(raw["make"]).strip() or None) if raw.get("make") else None,
        model=(str(raw["model"]).strip() or None) if raw.get("model") else None,
        year=parse_year(raw.get("year")),
        mileage_km=parse_int_loose(raw.get("mileage")),
        fuel_type=normalize_fuel(raw.get("fuel")),
        transmission=normalize_transmission(raw.get("transmission")),
        power_kw=parse_int_loose(raw.get("power_kw")),
        body_type=normalize_body(raw.get("body")),
        color=(str(raw["color"]).strip() or None) if raw.get("color") else None,
        doors=parse_int_loose(raw.get("doors")),
        seats=parse_int_loose(raw.get("seats")),
        price_net=parse_decimal(raw.get("price_net")),
        price_gross=parse_decimal(raw.get("price_gross") if raw.get("price_gross") is not None else raw.get("price")),
        currency=normalize_currency(raw.get("currency")),
        vat_mode=_vat_mode(raw),
        images=_as_tuple(raw.get("images")),
        equipment=_as_tuple(raw.get("equipment")),
        additional={str(k): str(v) for k, v in (raw.get("additional") or {}).items()},
    )
