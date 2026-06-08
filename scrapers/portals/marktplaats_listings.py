"""
Marktplaats listing extractor — vehicles from __NEXT_DATA__.searchRequestAndResponse.listings.

Marktplaats (NL generalist, CloudFront — proxy-free) is Next.js: ``/l/auto-s/`` embeds ~30
listings in ``searchRequestAndResponse.listings`` + ``totalResultCount``. Each listing has
``itemId``/``vipUrl``/``priceInfo.priceCents`` + an ``attributes`` list of ``{key,value,values}``
(constructionYear/mileage/fuel/transmission/model). The MAKE is not an attribute — it is the
category path segment in ``vipUrl`` (``/v/auto-s/<make>/<itemId-slug>``).

Verified proxy-free 2026-06-09 (HTTP 200, totalResultCount=264.907). NOTE: offset pagination
dies ~3.000 (the advertised maxAllowedPageNumber=5000 is a lie, DOSSIER §) → full enumeration
needs facet-partition by ``constructionYear`` (harness concern). Pure parser, like as24_listings.
"""
from __future__ import annotations

import re
from typing import Any

from scrapers.portals.as24_listings import extract_next_data  # shared Next.js reader

_DIGITS = re.compile(r"\d+")
_ITEMID = re.compile(r"^m\d")


def number_of_results(next_data: dict) -> int | None:
    srr = (next_data.get("props", {}).get("pageProps", {}).get("searchRequestAndResponse", {})
           if isinstance(next_data, dict) else {})
    v = srr.get("totalResultCount")
    return int(v) if isinstance(v, (int, float)) else None


def _int_or_none(v: Any) -> int | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    digits = "".join(_DIGITS.findall(str(v)))
    return int(digits) if digits else None


def _make_from_vipurl(url: str) -> str | None:
    """Make is the category segment after ``auto-s`` in the vipUrl (/v/auto-s/<make>/<id-slug>)."""
    parts = [p for p in url.split("/") if p]
    if "auto-s" in parts:
        i = parts.index("auto-s")
        if i + 1 < len(parts):
            seg = parts[i + 1]
            if not _ITEMID.match(seg):  # guard: not the itemId slug
                return seg.replace("-", " ").title()
    return None


def parse_listings(next_data: dict, *, base_url: str = "https://www.marktplaats.nl",
                   currency: str = "EUR") -> list[dict]:
    """Normalize Marktplaats ``listings`` into seam-ready vehicle dicts."""
    if not isinstance(next_data, dict):
        return []
    listings = (next_data.get("props", {}).get("pageProps", {})
                .get("searchRequestAndResponse", {}).get("listings"))
    if not isinstance(listings, list):
        return []
    out: list[dict] = []
    for it in listings:
        if not isinstance(it, dict):
            continue
        attrs = {a.get("key"): a.get("value") for a in it.get("attributes", [])
                 if isinstance(a, dict) and a.get("key")}
        url = it.get("vipUrl") or it.get("url") or ""
        if url.startswith("/"):
            url = base_url.rstrip("/") + url
        if not url:
            continue
        cents = (it.get("priceInfo") or {}).get("priceCents")
        price_raw = (int(cents) // 100) if isinstance(cents, (int, float)) and cents > 0 else None
        out.append({
            "source_url": url,
            "source_listing_id": str(it.get("itemId") or ""),
            "make": _make_from_vipurl(url),
            "model": attrs.get("model"),
            "year": _int_or_none(attrs.get("constructionYear")),
            "mileage_km": _int_or_none(attrs.get("mileage")),
            "price_raw": price_raw,
            "currency_raw": currency,
            "fuel_type": attrs.get("fuel"),
            "transmission": attrs.get("transmission"),
        })
    return out
