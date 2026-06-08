"""
leboncoin listing extractor — vehicles from __NEXT_DATA__.props.pageProps.searchData.ads.

leboncoin (FR classifieds, DataDome) is Next.js: each ``/recherche?category=2`` page embeds ~35
ads in ``searchData.ads``. Each ad carries ``url``/``list_id``/``price[0]``/``subject`` plus an
``attributes`` list of ``{key, value, value_label}`` (brand/model/regdate/mileage/fuel/gearbox/…).

Proxy-free reachable today with the approved curl_cffi Chrome stack (verified 2026-06-09: HTTP 200,
``searchData.total``=777.636). CAVEAT: DataDome may challenge under SUSTAINED pagination — validate
bulk-harvest sustainability before trusting volume (a single count/extract works; deep paging is the
open question, see PROOF_TIER1_PROXYFREE.md §caveat). Pure parser over fetched HTML, like as24_listings.
"""
from __future__ import annotations

import re
from typing import Any

from scrapers.portals.as24_listings import extract_next_data  # shared Next.js __NEXT_DATA__ reader

_DIGITS = re.compile(r"\d+")


def number_of_results(next_data: dict) -> int | None:
    """leboncoin's own declared total (independent count for the count_verify gate)."""
    sd = (next_data.get("props", {}).get("pageProps", {}).get("searchData", {})
          if isinstance(next_data, dict) else {})
    v = sd.get("total")
    return int(v) if isinstance(v, (int, float)) else None


def _int_or_none(v: Any) -> int | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    digits = "".join(_DIGITS.findall(str(v)))
    return int(digits) if digits else None


def _attr_map(ad: dict) -> dict[str, dict]:
    return {a.get("key"): a for a in ad.get("attributes", []) if isinstance(a, dict) and a.get("key")}


def parse_listings(next_data: dict, *, base_url: str = "https://www.leboncoin.fr",
                   currency: str = "EUR") -> list[dict]:
    """Normalize leboncoin ``searchData.ads`` into seam-ready vehicle dicts."""
    if not isinstance(next_data, dict):
        return []
    ads = next_data.get("props", {}).get("pageProps", {}).get("searchData", {}).get("ads")
    if not isinstance(ads, list):
        return []
    out: list[dict] = []
    for ad in ads:
        if not isinstance(ad, dict):
            continue
        attrs = _attr_map(ad)

        def a(key: str, field: str = "value") -> Any:
            x = attrs.get(key)
            return x.get(field) if isinstance(x, dict) else None

        url = ad.get("url") or ""
        if url.startswith("/"):
            url = base_url.rstrip("/") + url
        if not url:
            continue
        price = ad.get("price")
        price_raw = price[0] if isinstance(price, list) and price else None
        if price_raw is None and ad.get("price_cents"):
            cents = _int_or_none(ad.get("price_cents"))
            price_raw = cents // 100 if cents else None
        out.append({
            "source_url": url,
            "source_listing_id": str(ad.get("list_id") or ""),
            "make": a("brand") or a("u_car_brand"),
            "model": a("model"),
            "variant": a("u_car_version", "value_label") or a("u_car_finition", "value_label"),
            "year": _int_or_none(a("regdate")),
            "mileage_km": _int_or_none(a("mileage")),
            "price_raw": _int_or_none(price_raw),
            "currency_raw": currency,
            "fuel_type": a("fuel", "value_label"),
            "transmission": a("gearbox", "value_label"),
            "color": a("vehicule_color", "value_label"),
        })
    return out
