"""
Parse — extract raw listing fields from a detail page, JSON-LD first.

Three-stage cascade (SCRAPING_ENGINE.md §C2, selectors verified in GOLD_NUGGETS §9):

    STAGE 1  JSON-LD   schema.org Vehicle/Car objects in
                       <script type="application/ld+json"> (~60% of listings)
    STAGE 2  OG/meta   Open Graph + product:* meta tags (fallback)
    STAGE 3  heuristic verified §9 E03 regexes for year / mileage / price

Only standard, published vocabularies are read — schema.org terms and the Open
Graph protocol — plus the three regexes salvaged verbatim from the previous
system. No portal-specific CSS selector is invented here; LLM extraction
(§C2 stage 3) is an offline concern handled outside the hot path.

Output is a flat `dict[str, Any]` consumed by `normalize.to_record`. Higher
stages never overwrite a field a more reliable stage already filled, so the
JSON-LD result always wins over a heuristic guess.
"""
from __future__ import annotations

import json
import re
from typing import Any

# schema.org @type values that denote a vehicle (GOLD_NUGGETS §9 E01).
_VEHICLE_TYPES = {"vehicle", "car", "motorvehicle", "busorcoach", "motorcycle"}

_JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_META_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_META_KEY_RE = re.compile(r'(?:property|name)\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_META_CONTENT_RE = re.compile(r'content\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)

# Verified §9 E03 heuristics.
_YEAR_RE = re.compile(r"\b(19[89]\d|20[012]\d)\b")
_MILEAGE_RE = re.compile(r"\b(\d[\d\s.]*)\s*(?:km|kms|kilometre|kilometer)\b", re.IGNORECASE)
_PRICE_RE = re.compile(r"(\d[\d\s.,]*)\s*(€|eur|euro)\b", re.IGNORECASE)


# ── JSON-LD (stage 1) ────────────────────────────────────────────────────────
def _iter_jsonld_objects(html: str):
    """Yield every dict embedded across all ld+json blocks (flattening @graph/lists)."""
    for block in _JSONLD_RE.finditer(html):
        raw = block.group(1).strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            continue
        yield from _walk(data)


def _walk(node: Any):
    """Depth-first walk yielding every dict node (objects may nest in @graph/itemListElement)."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _type_set(obj: dict) -> set[str]:
    t = obj.get("@type")
    if isinstance(t, str):
        return {t.lower()}
    if isinstance(t, list):
        return {str(x).lower() for x in t}
    return set()


def _scalar(value: Any) -> str | None:
    """schema.org values are often {name|url|value:...}; reduce to a scalar string."""
    if value is None:
        return None
    if isinstance(value, (str, int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in ("name", "value", "url", "@value"):
            if key in value:
                return _scalar(value[key])
    if isinstance(value, list) and value:
        return _scalar(value[0])
    return None


def _images(value: Any) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    out: list[str] = []
    for item in items:
        s = _scalar(item)
        if s:
            out.append(s)
    return out


def _offer_price(obj: dict) -> tuple[str | None, str | None]:
    """Pull (price, currency) from offers — Offer, AggregateOffer, or a list thereof."""
    offers = obj.get("offers")
    for candidate in _walk(offers):
        if not isinstance(candidate, dict):
            continue
        price = candidate.get("price") or candidate.get("lowPrice")
        if price is not None:
            return _scalar(price), _scalar(candidate.get("priceCurrency"))
    return None, None


def _jsonld_fields(obj: dict) -> dict[str, Any]:
    """Map a schema.org Vehicle/Car object onto the raw-field contract."""
    price, currency = _offer_price(obj)
    engine = obj.get("vehicleEngine")
    power = None
    if isinstance(engine, dict):
        power = _scalar(engine.get("enginePower"))
    fields: dict[str, Any] = {
        "make": _scalar(obj.get("brand") or obj.get("manufacturer")),
        "model": _scalar(obj.get("model")),
        "year": _scalar(obj.get("vehicleModelDate") or obj.get("modelDate") or obj.get("productionDate")),
        "mileage": _scalar(obj.get("mileageFromOdometer")),
        "fuel": _scalar(obj.get("fuelType")),
        "transmission": _scalar(obj.get("vehicleTransmission")),
        "power_kw": power,
        "body": _scalar(obj.get("bodyType")),
        "color": _scalar(obj.get("color")),
        "doors": _scalar(obj.get("numberOfDoors")),
        "seats": _scalar(obj.get("vehicleSeatingCapacity")),
        "vin": _scalar(obj.get("vehicleIdentificationNumber")),
        "price": price,
        "currency": currency,
        "images": _images(obj.get("image")),
        "listing_id": _scalar(obj.get("sku") or obj.get("productID") or obj.get("@id")),
    }
    return {k: v for k, v in fields.items() if v not in (None, [], "")}


def parse_jsonld(html: str) -> dict[str, Any]:
    """Return raw fields from the first schema.org vehicle object, or {} if none."""
    for obj in _iter_jsonld_objects(html):
        if _type_set(obj) & _VEHICLE_TYPES:
            fields = _jsonld_fields(obj)
            if fields:
                return fields
    return {}


def jsonld_types(html: str) -> set[str]:
    """All lowercased @type values across every ld+json block — used by poison detection."""
    types: set[str] = set()
    for obj in _iter_jsonld_objects(html):
        types |= _type_set(obj)
    return types


# ── OG / meta (stage 2) ──────────────────────────────────────────────────────
def _meta_map(html: str) -> dict[str, str]:
    """Order-independent map of <meta property|name=...> → content."""
    out: dict[str, str] = {}
    for tag in _META_RE.finditer(html):
        raw = tag.group(0)
        key = _META_KEY_RE.search(raw)
        content = _META_CONTENT_RE.search(raw)
        if key and content:
            out.setdefault(key.group(1).lower(), content.group(1))
    return out


def parse_og_meta(html: str) -> dict[str, Any]:
    """Open Graph + product:* fallback fields (GOLD_NUGGETS §C2 stage 2)."""
    meta = _meta_map(html)
    fields: dict[str, Any] = {}
    if "og:title" in meta:
        fields["title"] = meta["og:title"]
    if meta.get("og:image"):
        fields["images"] = [meta["og:image"]]
    if "product:price:amount" in meta:
        fields["price"] = meta["product:price:amount"]
    if "product:price:currency" in meta:
        fields["currency"] = meta["product:price:currency"]
    return fields


# ── heuristics (stage 3) ─────────────────────────────────────────────────────
def parse_heuristics(html: str) -> dict[str, Any]:
    """Last-resort year/mileage/price extraction via the verified §9 E03 regexes."""
    fields: dict[str, Any] = {}
    year = _YEAR_RE.search(html)
    if year:
        fields["year"] = year.group(1)
    mileage = _MILEAGE_RE.search(html)
    if mileage:
        fields["mileage"] = mileage.group(1)
    price = _PRICE_RE.search(html)
    if price:
        fields["price"] = price.group(1)
        fields["currency"] = price.group(2)
    return fields


def parse_listing(html: str) -> dict[str, Any]:
    """
    Run the full cascade and merge, most-reliable-stage-wins.

    JSON-LD fills first and is never overwritten; OG/meta then heuristics only
    fill fields still absent. Returns the merged raw-field dict for normalization.
    """
    merged: dict[str, Any] = {}
    for stage in (parse_jsonld(html), parse_og_meta(html), parse_heuristics(html)):
        for key, value in stage.items():
            if key not in merged or merged[key] in (None, [], ""):
                merged[key] = value
    return merged
