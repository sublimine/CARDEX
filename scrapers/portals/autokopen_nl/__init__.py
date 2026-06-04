"""
autokopen.nl -- Netherlands aggregator (Dealerdirect Media B.V., ~106,645 listings).

autokopen.nl is a Next.js SSR site (confirmed by `meta-next-size-adjust` header)
with NO WAF. Vehicle search data is served via the Next.js internal data route in
JSON format. The buildId is extracted from ``__NEXT_DATA__`` in the SSR HTML and
used to construct ``/_next/data/{buildId}/...`` requests. Tier.T1.

Gold nuggets [research 2026-06-04]:

  Base URL      https://autokopen.nl                                    [VERIFIED]
  Search URL    https://autokopen.nl/auto                               [VERIFIED]
  Query params  brand=volkswagen, fuel=benzine, year_min=2020,
                year_max=2026, price_min=, price_max=, sort=date_desc    [VERIFIED]
  Pagination    ?page=2 etc; 24 items per page; 605 pages unfiltered    [VERIFIED]
  Detail URL    /auto/detail/{slug}
                e.g. /auto/detail/bmw-x5-2020-sc-autounit_52420900      [VERIFIED]
  Next.js       meta-next-size-adjust header present; __NEXT_DATA__
                JSON embedded in SSR HTML.                              [VERIFIED]
  Data route    GET https://autokopen.nl/_next/data/{buildId}/auto.json
                    ?page={N}&year_min={Y1}&year_max={Y2}
                    &price_min={P1}&price_max={P2}                      [ASSUMED from Next.js convention]
  buildId       Changes with each deploy; extracted from __NEXT_DATA__
                JSON in the SSR HTML.                                   [ASSUMED from Next.js convention]
  Items         JSON pageProps containing a listing array; field name
                likely one of: results, vehicles, listings, items, data. [ASSUMED]
  Coverage      ~106,645 listings; requires year x price partitioning.  [VERIFIED count]
  Block sig     Standard transient HTTP errors (403/429/5xx).           [ASSUMED]

Strategy: year band x price band grid partitioning. The buildId is resolved on the
first request via SSR HTML and cached for the full scrape cycle. If the buildId
expires mid-cycle (404 on the data route), we re-resolve once before giving up.
A capped segment is subdivided into per-year x finer-price sub-cells.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from itertools import product
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 500, 502, 503})

# Regex to extract buildId from __NEXT_DATA__ embedded in SSR HTML.
_BUILD_ID_RE: re.Pattern[str] = re.compile(
    r'"buildId"\s*:\s*"([A-Za-z0-9_-]+)"',
)

# -- search grid (year x price partitioning for 106k inventory) ---------------
_YEAR_BANDS: tuple[tuple[int, int], ...] = (
    (2000, 2005), (2005, 2008), (2008, 2011), (2011, 2014),
    (2014, 2016), (2016, 2018), (2018, 2020), (2020, 2022),
    (2022, 2024), (2024, 2026),
)
_PRICE_BANDS: tuple[tuple[int, int | None], ...] = (
    (0, 5_000), (5_000, 10_000), (10_000, 15_000), (15_000, 20_000),
    (20_000, 30_000), (30_000, 50_000), (50_000, 100_000), (100_000, None),
)
_OPEN_PRICE_CEILING: int = 500_000
_PRICE_SUBSPLITS: int = 5

# Known field paths where Next.js sites store listing arrays in pageProps.
_LISTING_ARRAY_KEYS: tuple[str, ...] = (
    "results", "vehicles", "listings", "items", "data", "cars", "ads",
)
# Known field names for the detail URL within a listing object.
_URL_FIELD_KEYS: tuple[str, ...] = (
    "url", "href", "link", "detailUrl", "canonical",
)
# Known field names for slug that can be composed into a URL.
_SLUG_FIELD_KEYS: tuple[str, ...] = ("slug", "friendlyUrl", "seoSlug", "urlSlug")


class AutoKopenNLScraper(BasePortalScraper):
    """autokopen.nl cars via the Next.js data route (T1, year x price grid)."""

    DOMAIN = "autokopen.nl"
    COUNTRY = "NL"

    HOST = "autokopen.nl"

    # 24 items/page [VERIFIED]; MAX_PAGES with margin for segment pagination.
    PAGE_SIZE = 24
    MAX_PAGES = 700

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 25

    YEAR_BANDS: tuple[tuple[int, int], ...] = _YEAR_BANDS
    PRICE_BANDS: tuple[tuple[int, int | None], ...] = _PRICE_BANDS

    # Search path used for SSR HTML (buildId resolution) and data route.
    _SEARCH_PATH: str = "auto"

    def __init__(self) -> None:
        super().__init__()
        self._build_id: str | None = None

    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    # -- primitives ----------------------------------------------------------
    def partition_params(self) -> list[dict[str, Any]]:
        """Year band x price band grid covering ~106k inventory."""
        return [
            {"year_min": yf, "year_max": yt, "price_min": pf, "price_max": pt}
            for (yf, yt), (pf, pt) in product(self.YEAR_BANDS, self.PRICE_BANDS)
        ]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Explode a capped cell into per-year x finer-price sub-cells."""
        if params.get("_fine"):
            return []
        years = range(params["year_min"], params["year_max"] + 1)
        price_bands = self._split_price(params["price_min"], params["price_max"])
        return [
            {"year_min": y, "year_max": y, "price_min": pf, "price_max": pt, "_fine": True}
            for y, (pf, pt) in product(years, price_bands)
        ]

    @staticmethod
    def _split_price(pf: int, pt: int | None) -> list[tuple[int, int | None]]:
        """Cut [pf, pt) into ``_PRICE_SUBSPLITS`` contiguous sub-bands."""
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
        """Fetch one page via the Next.js data route; retry transient blocks."""
        # Resolve buildId on the first call.
        if self._build_id is None:
            resolved = await self._resolve_build_id(session)
            if resolved is None:
                log.warning("could not resolve buildId for autokopen.nl")
                return []
            self._build_id = resolved

        url = self._build_data_url(params, page_num)
        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            response = await self._get(session, url)
            if response is None:
                await self._retry_backoff(attempt)
                continue

            status = response.status_code
            if status in _BLOCK_STATUSES:
                log.debug("HTTP %d (%d/%d) %s", status, attempt, self.RETRY_ATTEMPTS, url[:90])
                await self._retry_backoff(attempt)
                continue
            if status == 404:
                # buildId expired (new deploy). Try to re-resolve once.
                if attempt == 1:
                    log.info("buildId expired (404), re-resolving...")
                    resolved = await self._resolve_build_id(session)
                    if resolved is not None:
                        self._build_id = resolved
                        url = self._build_data_url(params, page_num)
                        continue
                return []
            if status != 200:
                log.debug("HTTP %d (no retry) %s", status, url[:90])
                return []

            return self._extract(response.text)

        log.warning("all %d attempts failed: %s", self.RETRY_ATTEMPTS, url[:90])
        return []

    # -- helpers --------------------------------------------------------------
    def _build_data_url(self, params: dict[str, Any], page_num: int) -> str:
        base = f"{self._base_url}/_next/data/{self._build_id}/{self._SEARCH_PATH}.json"
        qs_parts = [f"page={page_num}"]
        if "year_min" in params:
            qs_parts.append(f"year_min={params['year_min']}")
        if "year_max" in params:
            qs_parts.append(f"year_max={params['year_max']}")
        if params.get("price_min") is not None:
            qs_parts.append(f"price_min={params['price_min']}")
        if params.get("price_max") is not None:
            qs_parts.append(f"price_max={params['price_max']}")
        return f"{base}?{'&'.join(qs_parts)}"

    def _extract(self, body: str) -> list[str]:
        """Extract detail URLs from the Next.js data route JSON.

        Robust against unknown JSON structure: tries multiple known field paths
        for the listing array and URL fields.
        """
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            log.debug("non-JSON body from autokopen data route")
            return []

        page_props = payload.get("pageProps", {}) if isinstance(payload, dict) else {}
        if not isinstance(page_props, dict):
            return []

        # Find the listing array.
        listings = self._find_listing_array(page_props)
        if not listings:
            return []

        seen: set[str] = set()
        out: list[str] = []
        for item in listings:
            if not isinstance(item, dict):
                continue
            url = self._item_url(item)
            if url and url not in seen:
                seen.add(url)
                out.append(url)
        return out

    def _find_listing_array(self, props: dict[str, Any]) -> list[Any]:
        """Walk pageProps looking for a list of listings under known key names."""
        # Direct lookup in pageProps.
        for key in _LISTING_ARRAY_KEYS:
            candidate = props.get(key)
            if isinstance(candidate, list) and candidate:
                return candidate
        # One level deeper (e.g. pageProps.searchResults.vehicles).
        for val in props.values():
            if not isinstance(val, dict):
                continue
            for key in _LISTING_ARRAY_KEYS:
                candidate = val.get(key)
                if isinstance(candidate, list) and candidate:
                    return candidate
        return []

    def _item_url(self, item: dict[str, Any]) -> str | None:
        """Resolve detail URL from a listing object via known field names."""
        # Try direct URL fields.
        for key in _URL_FIELD_KEYS:
            val = item.get(key)
            if isinstance(val, str) and val:
                return val if val.startswith("http") else f"{self._base_url}{val}"

        # Try slug composition: /auto/detail/{slug}  [VERIFIED URL pattern]
        for key in _SLUG_FIELD_KEYS:
            val = item.get(key)
            if isinstance(val, str) and val:
                return f"{self._base_url}/auto/detail/{val}"
        return None

    async def _resolve_build_id(self, session: Any) -> str | None:
        """Fetch SSR HTML to extract buildId from __NEXT_DATA__."""
        html_url = f"{self._base_url}/{self._SEARCH_PATH}"
        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            response = await self._get(session, html_url)
            if response is None:
                await self._retry_backoff(attempt)
                continue
            if response.status_code != 200:
                await self._retry_backoff(attempt)
                continue
            match = _BUILD_ID_RE.search(response.text)
            if match:
                bid = match.group(1)
                log.info("autokopen buildId resolved: %s", bid)
                return bid
            log.debug("buildId not found in SSR HTML of /%s", self._SEARCH_PATH)
            return None
        return None

    async def _get(self, session: Any, url: str) -> Any | None:
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:
            log.debug("transport error %s: %s", url[:90], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(self.RETRY_BACKOFF_BASE**attempt * factor + random.uniform(0, 0.25))
