"""
wallapop.com — Spain, general marketplace with ~large car inventory.

T0 bypass: wallapop.com's web frontend is protected by PerimeterX, but the
mobile API at api.wallapop.com is unprotected.  A GET to the v3 general search
endpoint with a mobile User-Agent returns clean JSON — no challenge, no token,
no cookie dance.

Gold nuggets [research 2026-06-04]:

  Search URL  GET https://api.wallapop.com/api/v3/general/search
                  ?keywords=coches&category_ids=100
                  &latitude={lat}&longitude={lon}&distance_in_km=100
                  &min_sale_price={Pf}&max_sale_price={Pt}
                  &order_by=newest                                  [VERIFIED]
  Category    category_ids=100 = Cars.                              [VERIFIED]
  Geo filter  latitude + longitude + distance_in_km.
              Wallapop is geo-centric: every search requires a centre point.
              We partition by major Spanish cities with 100 km radius each.
                                                                    [VERIFIED]
  Page size   40 items per response (fixed, server-controlled).     [VERIFIED]
  Pagination  Cursor-based. Response includes `next_page` (opaque base64
              token). Pass as `?start={next_page}` to fetch the next window.
              When `next_page` is absent or null, the segment is exhausted.
                                                                    [VERIFIED]
  Response    {"search_objects": [...], "next_page": "eyJ..."}      [VERIFIED]
  Item shape  Each object has:
                id              (str)  internal item ID
                title           (str)  listing title
                web_slug        (str)  URL-safe slug
                price.amount    (float) sale price in EUR
                images          (list)  image objects
                location        (dict)  lat/lon/city
                                                                    [VERIFIED]
  Detail URL  https://es.wallapop.com/item/{web_slug}               [VERIFIED]
  Price filt  min_sale_price / max_sale_price (EUR, integer).       [VERIFIED]
  Sort        order_by=newest | price_low_to_high | ...             [ASSUMED]
  Headers     Mobile User-Agent required; no auth token observed.   [VERIFIED]
  X-Signature Header may be enforced in the future but currently NOT
              required for the general search endpoint.             [ASSUMED]
  Block sig   PerimeterX on web only. Mobile API: standard HTTP errors
              (429/5xx). No CAPTCHA or JS challenge observed.       [VERIFIED]

Partition: geographic centres (8 major Spanish cities × 100 km radius) ×
price bands.  Each geo-price cell is paginated via cursor.  Subdivision
splits a capped geo-price cell into finer price sub-bands.

Cross-cell dedup is handled by the base `seen` set on canonical detail URLs.
Geo overlap between adjacent cities (e.g. Madrid/Toledo) is intentional —
dedup catches the duplicates cheaply, and the overlap ensures full coverage
of inventory between city centres.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from itertools import product
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

# ── geographic centres (major Spanish cities, 100 km radius each) ────────────
_GEO_CENTRES: tuple[tuple[str, float, float], ...] = (
    ("Madrid",    40.4168, -3.7038),
    ("Barcelona", 41.3874,  2.1686),
    ("Valencia",  39.4699, -0.3763),
    ("Sevilla",   37.3891, -5.9845),
    ("Zaragoza",  41.6488, -0.8891),
    ("Malaga",    36.7213, -4.4214),
    ("Bilbao",    43.2630, -2.9350),
    ("Alicante",  38.3452, -0.4810),
)
_DISTANCE_KM: int = 100

# ── price bands (EUR) ────────────────────────────────────────────────────────
_PRICE_BANDS: tuple[tuple[int, int | None], ...] = (
    (0, 5_000), (5_000, 10_000), (10_000, 15_000), (15_000, 20_000),
    (20_000, 30_000), (30_000, 50_000), (50_000, 100_000), (100_000, None),
)
_OPEN_PRICE_CEILING: int = 1_000_000
_PRICE_SUBSPLITS: int = 5

_CARS_CATEGORY_ID: int = 100

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 500, 502, 503})

# ── mobile UA (bypass PerimeterX) ────────────────────────────────────────────
_MOBILE_USER_AGENT: str = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.6099.230 Mobile Safari/537.36"
)

_SEARCH_URL: str = "https://api.wallapop.com/api/v3/general/search"


class WallapopComScraper(BasePortalScraper):
    """wallapop.com cars via the mobile API (T0 bypass, no PerimeterX)."""

    DOMAIN = "wallapop.com"
    COUNTRY = "ES"

    # API returns exactly 40 items per page (server-controlled).
    PAGE_SIZE = 40
    MAX_PAGES = 50

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 2.0
    REQUEST_TIMEOUT: int = 20

    GEO_CENTRES: tuple[tuple[str, float, float], ...] = _GEO_CENTRES
    PRICE_BANDS: tuple[tuple[int, int | None], ...] = _PRICE_BANDS

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": _MOBILE_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        }

    # ── primitives ─────────────────────────────────────────────────────────────
    def partition_params(self) -> list[dict[str, Any]]:
        """Geographic centre x price band — non-overlapping in price, intentionally
        overlapping in geography (dedup handles it)."""
        return [
            {
                "city": city,
                "latitude": lat,
                "longitude": lon,
                "price_from": pf,
                "price_to": pt,
            }
            for (city, lat, lon), (pf, pt) in product(self.GEO_CENTRES, self.PRICE_BANDS)
        ]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Split a capped geo-price cell into finer price sub-bands."""
        if params.get("_fine"):
            return []
        price_bands = self._split_price(params["price_from"], params["price_to"])
        return [
            {
                "city": params["city"],
                "latitude": params["latitude"],
                "longitude": params["longitude"],
                "price_from": pf,
                "price_to": pt,
                "_fine": True,
            }
            for pf, pt in price_bands
        ]

    @staticmethod
    def _split_price(pf: int, pt: int | None) -> list[tuple[int, int | None]]:
        """Cut [pf, pt) into `_PRICE_SUBSPLITS` contiguous sub-bands."""
        ceiling = pt if pt is not None else _OPEN_PRICE_CEILING
        step = max((ceiling - pf) // _PRICE_SUBSPLITS, 1)
        bands: list[tuple[int, int | None]] = []
        lo = pf
        while lo < ceiling:
            hi = min(lo + step, ceiling)
            bands.append((lo, hi))
            lo = hi
        if not bands:
            return [(pf, pt)]
        if pt is None:
            last_lo, _ = bands[-1]
            bands[-1] = (last_lo, None)
        return bands

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch one cursor page of listings.

        NOTE: page_num is ignored for cursor pagination — the cursor token is
        tracked in `_paginate`. This method is still called by `_paginate` with
        the cursor injected into `params["_cursor"]`.
        """
        url = self._build_url(params)
        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            response = await self._get(session, url)
            if response is None:
                await self._retry_backoff(attempt)
                continue

            status = response.status_code
            if status in _BLOCK_STATUSES:
                log.debug(
                    "HTTP %d (%d/%d) wallapop search",
                    status, attempt, self.RETRY_ATTEMPTS,
                )
                await self._retry_backoff(attempt, factor=2.0)
                continue
            if status != 200:
                log.debug("HTTP %d (no retry) wallapop search", status)
                return []

            urls, next_cursor = self._extract(response.text)
            # Stash the next cursor so _paginate can pick it up.
            params["_next_cursor"] = next_cursor
            return urls

        log.warning("all %d attempts failed: wallapop search", self.RETRY_ATTEMPTS)
        return []

    # ── cursor-based pagination override ──────────────────────────────────────
    async def _paginate(
        self, session: Any, params: dict[str, Any], seen: set[str]
    ) -> tuple[list[str], bool]:
        """Override base _paginate to use cursor-based pagination.

        Wallapop uses an opaque `next_page` cursor instead of offset/limit.
        Each response includes the cursor for the next page; when absent or
        null, the segment is exhausted.

        Returns (fresh_urls, hit_ceiling).  hit_ceiling is True when we
        consumed MAX_PAGES without exhausting the cursor — the structural
        signal that the segment needs subdivision.
        """
        out: list[str] = []
        hit_ceiling = False
        # Work on a shallow copy so cursor state does not pollute the caller.
        work_params = dict(params)
        work_params.pop("_cursor", None)
        work_params.pop("_next_cursor", None)

        for page in range(1, self.MAX_PAGES + 1):
            page_urls = await self.fetch_segment(session, work_params, page)
            fresh = [u for u in page_urls if u not in seen]
            seen.update(fresh)
            out.extend(fresh)

            # Short page → segment exhausted.
            if len(page_urls) < self.PAGE_SIZE:
                break

            # Pick up the cursor stashed by fetch_segment / _extract.
            next_cursor = work_params.pop("_next_cursor", None)
            if not next_cursor:
                # No cursor despite a full page — treat as exhausted.
                break

            if page == self.MAX_PAGES:
                hit_ceiling = True
                break

            # Inject cursor for next iteration.
            work_params["_cursor"] = next_cursor
            await self._sleep()

        return out, hit_ceiling

    # ── helpers ────────────────────────────────────────────────────────────────
    def _build_url(self, params: dict[str, Any]) -> str:
        """Construct the mobile API search URL with geo + price + cursor."""
        parts = [
            f"category_ids={_CARS_CATEGORY_ID}",
            f"latitude={params['latitude']}",
            f"longitude={params['longitude']}",
            f"distance_in_km={_DISTANCE_KM}",
            f"min_sale_price={params['price_from']}",
            "order_by=newest",
        ]
        pt = params.get("price_to")
        if pt is not None:
            parts.append(f"max_sale_price={pt}")

        cursor = params.get("_cursor")
        if cursor:
            parts.append(f"start={cursor}")

        return f"{_SEARCH_URL}?{'&'.join(parts)}"

    def _extract(self, body: str) -> tuple[list[str], str | None]:
        """Parse JSON response into (detail_urls, next_cursor).

        Response shape: {"search_objects": [...], "next_page": "eyJ..."}
        Each item: {"id": "...", "web_slug": "...", "price": {"amount": N}, ...}
        Detail URL: https://es.wallapop.com/item/{web_slug}
        """
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            log.debug("non-JSON body from wallapop API")
            return [], None

        if not isinstance(payload, dict):
            return [], None

        next_cursor: str | None = payload.get("next_page")
        if not isinstance(next_cursor, str) or not next_cursor:
            next_cursor = None

        items = payload.get("search_objects")
        if not isinstance(items, list):
            return [], next_cursor

        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            url = self._item_url(item)
            if url and url not in seen:
                seen.add(url)
                out.append(url)
        return out, next_cursor

    @staticmethod
    def _item_url(item: Any) -> str | None:
        """Build the canonical detail URL from an item's web_slug."""
        if not isinstance(item, dict):
            return None
        slug = item.get("web_slug")
        if not isinstance(slug, str) or not slug:
            return None
        return f"https://es.wallapop.com/item/{slug}"

    async def _get(self, session: Any, url: str) -> Any | None:
        try:
            return await session.get(
                url, headers=self._headers, timeout=self.REQUEST_TIMEOUT,
            )
        except Exception as exc:  # transport-level
            log.debug("transport error wallapop search: %s", exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(
                self.RETRY_BACKOFF_BASE ** attempt * factor + random.uniform(0, 0.25)
            )
