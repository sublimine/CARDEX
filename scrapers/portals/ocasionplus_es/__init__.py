"""
ocasionplus.com -- Spain, multi-brand used-car dealer (~20,000+ listings).

ocasionplus.com is a Next.js SSR site (confirmed by `meta-next-size-adjust` header)
with NO WAF. Vehicle search data is served via the Next.js internal data route in
JSON format. The buildId is extracted from ``__NEXT_DATA__`` in the SSR HTML and
used to construct ``/_next/data/{buildId}/...`` requests. Tier.T1.

Gold nuggets [research 2026-06-04]:

  Base URL      https://www.ocasionplus.com                             [VERIFIED]
  Search page   /coches-segunda-mano                                    [ASSUMED]
  Next.js       meta-next-size-adjust header present; __NEXT_DATA__
                JSON embedded in SSR HTML.                              [VERIFIED]
  Data route    GET https://www.ocasionplus.com/_next/data/{buildId}/
                    coches-segunda-mano.json?page={N}                   [ASSUMED]
  buildId       Changes with each deploy; extracted from __NEXT_DATA__
                JSON in the SSR HTML.                                   [ASSUMED from Next.js convention]
  Items         JSON pageProps containing a vehicle array; field name
                likely one of: results, vehicles, listings, items, data. [ASSUMED]
  Detail URL    /coches-segunda-mano/{slug}/{id} — extracted from the
                data route JSON via url/href/link/slug fields.          [ASSUMED from site crawl]
  Pagination    Page param in the data route query string; 24 items
                per page.                                               [ASSUMED]
  Coverage      ~20,000 listings; single-segment global pager is
                sufficient without partitioning.                        [ASSUMED]
  Block sig     Standard transient HTTP errors (403/429/5xx).           [ASSUMED]

Strategy: single-segment global paginator. The buildId is resolved on the first
request via SSR HTML and cached for the full scrape cycle. If the buildId expires
mid-cycle (404 on the data route), we re-resolve once before giving up.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 500, 502, 503})

# Regex to extract buildId from __NEXT_DATA__ embedded in SSR HTML.
_BUILD_ID_RE: re.Pattern[str] = re.compile(
    r'"buildId"\s*:\s*"([A-Za-z0-9_-]+)"',
)

# Known field paths where Next.js sites store listing arrays in pageProps.
_LISTING_ARRAY_KEYS: tuple[str, ...] = (
    "results", "vehicles", "listings", "items", "data", "cars", "ads",
)
# Known field names for the detail URL within a listing object.
_URL_FIELD_KEYS: tuple[str, ...] = (
    "url", "href", "link", "detailUrl", "canonical",
)
# Known field names for slug/id that can be composed into a URL.
_SLUG_FIELD_KEYS: tuple[str, ...] = ("slug", "friendlyUrl", "seoSlug", "urlSlug")
_ID_FIELD_KEYS: tuple[str, ...] = ("id", "vehicleId", "adId", "listingId")


class OcasionPlusESScraper(BasePortalScraper):
    """ocasionplus.com cars via the Next.js data route (T1, single segment)."""

    DOMAIN = "ocasionplus.com"
    COUNTRY = "ES"

    HOST = "www.ocasionplus.com"

    # 24 items/page [ASSUMED]; MAX_PAGES with margin for growth.
    PAGE_SIZE = 24
    MAX_PAGES = 1000

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 25

    # Search path used for both SSR HTML (buildId resolution) and data route.
    _SEARCH_PATH: str = "coches-segunda-mano"

    def __init__(self) -> None:
        super().__init__()
        self._build_id: str | None = None

    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    # -- primitives ----------------------------------------------------------
    def partition_params(self) -> list[dict[str, Any]]:
        """Single empty segment -- the global pager covers ~20k listings."""
        return [{}]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch one page via the Next.js data route; retry transient blocks."""
        # Resolve buildId on the first call.
        if self._build_id is None:
            resolved = await self._resolve_build_id(session)
            if resolved is None:
                log.warning("could not resolve buildId for ocasionplus.com")
                return []
            self._build_id = resolved

        url = self._build_data_url(page_num)
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
                        url = self._build_data_url(page_num)
                        continue
                return []
            if status != 200:
                log.debug("HTTP %d (no retry) %s", status, url[:90])
                return []

            return self._extract(response.text)

        log.warning("all %d attempts failed: %s", self.RETRY_ATTEMPTS, url[:90])
        return []

    # -- helpers --------------------------------------------------------------
    def _build_data_url(self, page_num: int) -> str:
        base = f"{self._base_url}/_next/data/{self._build_id}/{self._SEARCH_PATH}.json"
        return f"{base}?page={page_num}"

    def _extract(self, body: str) -> list[str]:
        """Extract detail URLs from the Next.js data route JSON.

        Robust against unknown JSON structure: tries multiple known field paths
        for the listing array and URL fields.
        """
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            log.debug("non-JSON body from ocasionplus data route")
            return []

        page_props = payload.get("pageProps", {}) if isinstance(payload, dict) else {}
        if not isinstance(page_props, dict):
            return []

        # Find the listing array: check top-level pageProps keys and one level deeper.
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

        # Try slug + id composition.
        slug = None
        for key in _SLUG_FIELD_KEYS:
            val = item.get(key)
            if isinstance(val, str) and val:
                slug = val
                break
        item_id = None
        for key in _ID_FIELD_KEYS:
            val = item.get(key)
            if val is not None:
                item_id = str(val)
                break

        if slug and item_id:
            return f"{self._base_url}/{self._SEARCH_PATH}/{slug}/{item_id}"
        if slug:
            return f"{self._base_url}/{self._SEARCH_PATH}/{slug}"
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
                log.info("ocasionplus buildId resolved: %s", bid)
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
