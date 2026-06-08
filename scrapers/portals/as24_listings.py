"""
AutoScout24 listing-page extractor (strategy ``faceted_ssr``) — vehicles from __NEXT_DATA__.

A single ``/lst?page=N`` fetch yields ~20 fully-structured listings in
``props.pageProps.listings`` (make/model/year/mileage/price/url all present) — NO per-detail
fetch needed for the core fields. That makes giant harvest far higher-throughput than the
per-PDP dealer model (20 cars/request vs 1), and one parser covers AS24's 6 TLDs (identical
__NEXT_DATA__ shape). Proxy-free reachable with the approved curl_cffi Chrome stack
(verified 2026-06-09: AS24-FR sustained pagination, numberOfResults gate-trustworthy).

Pure functions over already-fetched HTML so extraction is deterministic and unit-testable;
the fetch (curl_cffi, JA3-coherent session) and the seam are the caller's job.
"""
from __future__ import annotations

import json
import re
from typing import Any

_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_DIGITS = re.compile(r"\d+")


def extract_next_data(html: str) -> dict:
    """Parse the page's ``__NEXT_DATA__`` JSON blob, or {} when absent/invalid."""
    m = _NEXT_DATA_RE.search(html or "")
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except (ValueError, TypeError):
        return {}


def number_of_results(next_data: dict) -> int | None:
    """The page's own declared total (independent count for the count_verify gate)."""
    pp = next_data.get("props", {}).get("pageProps", {}) if isinstance(next_data, dict) else {}
    v = pp.get("numberOfResults")
    return int(v) if isinstance(v, (int, float)) else None


def _year_from_registration(reg: Any) -> int | None:
    """'01-2020' / '2020' -> 2020 (first 4-digit run)."""
    if not reg:
        return None
    for n in _DIGITS.findall(str(reg)):
        if len(n) == 4:
            return int(n)
    return None


def _int_or_none(v: Any) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    digits = "".join(_DIGITS.findall(str(v)))
    return int(digits) if digits else None


def plan_price_partitions(
    count_fn,
    *,
    lo: int = 0,
    hi: int = 1_000_000,
    cap: int = 4000,
    min_width: int = 250,
    max_segments: int = 4000,
) -> list[tuple[int, int, int]]:
    """
    Plan price-range segments each below the source's hard result cap, by recursive bisection.

    AS24 (like most T1) caps deep pagination at ~4.000 results/segment (200 pages × 20). To
    enumerate ALL of a 90k+ inventory you partition the price axis until every segment's own
    ``numberOfResults`` is < ``cap``, then enumerate each segment's pages and union+dedup.

    ``count_fn(lo, hi) -> int`` returns the source's declared count for the price filter
    ``[lo, hi)`` (the caller wires it to a live ``/lst?pricefrom=lo&priceto=hi`` fetch +
    ``number_of_results``). Pure control flow otherwise → unit-testable with a mock count_fn.
    A bucket that stays >= cap below ``min_width`` is kept anyway (a price spike denser than the
    cap — accept the small leak, log at the call site) so the planner always terminates.

    Returns leaf ``(lo, hi, count)`` segments with count > 0. The count_verify gate then checks
    ``sum(counts)`` against the unfiltered base count.
    """
    segments: list[tuple[int, int, int]] = []
    stack: list[tuple[int, int]] = [(lo, hi)]
    while stack and len(segments) < max_segments:
        a, b = stack.pop()
        if b <= a:
            continue
        count = count_fn(a, b)
        if count <= 0:
            continue
        if count < cap or (b - a) <= min_width:
            segments.append((a, b, count))
        else:
            mid = a + (b - a) // 2
            stack.append((mid, b))
            stack.append((a, mid))
    segments.sort()
    return segments


def parse_listings(next_data: dict, *, base_url: str, currency: str = "EUR") -> list[dict]:
    """
    Normalize AS24 ``__NEXT_DATA__`` listings into seam-ready vehicle dicts.

    Prefers the numeric ``tracking.*`` fields (price/mileage as ints, firstRegistration) over
    the display-formatted ``price.priceFormatted``. ``base_url`` resolves the relative ``url``;
    ``currency`` is EUR for de/fr/es/nl/be and CHF for the .ch TLD.
    """
    if not isinstance(next_data, dict):
        return []
    listings = next_data.get("props", {}).get("pageProps", {}).get("listings")
    if not isinstance(listings, list):
        return []
    out: list[dict] = []
    for it in listings:
        if not isinstance(it, dict):
            continue
        veh = it.get("vehicle") or {}
        trk = it.get("tracking") or {}
        url = it.get("url") or ""
        if url.startswith("/"):
            url = base_url.rstrip("/") + url
        if not url:
            continue
        out.append({
            "source_url": url,
            "source_listing_id": str(it.get("id") or it.get("identifier") or ""),
            "make": veh.get("make"),
            "model": veh.get("model") or veh.get("modelGroup"),
            "variant": veh.get("variant") or veh.get("modelVersionInput"),
            "year": _year_from_registration(trk.get("firstRegistration")),
            "mileage_km": _int_or_none(trk.get("mileage") if trk.get("mileage") is not None
                                       else veh.get("mileageInKm")),
            "price_raw": _int_or_none(trk.get("price")),
            "currency_raw": currency,
            "fuel_type": veh.get("fuel"),
            "transmission": veh.get("transmission"),
        })
    return out
