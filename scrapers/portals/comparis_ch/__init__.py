"""
comparis.ch -- Switzerland, meta-aggregator (~214k used-car listings).

comparis.ch is a Swiss comparison portal that aggregates vehicle listings from
autoscout24, autolina, carmarket, drive-in.ch, carweb, and other Swiss dealer
platforms. The car-finder surface at /carfinder/marktplatz is a Next.js SSR app
(indicated by the `meta-next-head-count` header) that returns server-rendered
HTML with listing cards. No Cloudflare WAF observed -- naked curl_cffi
`impersonate="chrome"` passes. Tier T1.

Gold nuggets [VERIFIED 2026-06-04]:

  Search URL  GET https://www.comparis.ch/carfinder/marktplatz
                  ?sort=2&page={N}&yearfrom={Y1}&yearto={Y2}
                  &pricefrom={P1}&priceto={P2}&condition=occasion
  Page index  0-based (page=0 is the first page).
  Listings    SSR HTML <a href="/carfinder/marktplatz/details/show/{ID}">
              where ID is a numeric listing identifier (e.g. 32911044).
  Detail URL  https://www.comparis.ch/carfinder/marktplatz/details/show/{ID}
  Pagination  ~10 items per page. page=0, page=1, ... up to exhaustion.
  Filters     make={brand}, yearfrom/yearto, pricefrom/priceto,
              bodytype, fuel, condition=occasion|neuwagen
  WAF         None observed (T1). Next.js SSR, no DataDome/Akamai/PerimeterX.
  Inventory   ~214k listings across aggregated sources.

Partition: year band x price band. With ~214k listings and a 10-per-page cap,
the scraper needs aggressive segmentation to stay under MAX_PAGES per cell.
Each cell is capped at 200 pages (2,000 listings); overflow triggers per-year
x finer-price subdivision.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from itertools import product
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

# -- search grid ----------------------------------------------------------------
# Year bands: tighter recent bands where density is highest.
_YEAR_BANDS: tuple[tuple[int, int], ...] = (
    (1990, 2000),
    (2000, 2005),
    (2005, 2008),
    (2008, 2011),
    (2011, 2014),
    (2014, 2016),
    (2016, 2018),
    (2018, 2020),
    (2020, 2022),
    (2022, 2024),
    (2024, 2026),
)

# Price bands in CHF. The Swiss market skews higher than EU averages.
_PRICE_BANDS: tuple[tuple[int, int | None], ...] = (
    (0, 5_000),
    (5_000, 10_000),
    (10_000, 15_000),
    (15_000, 20_000),
    (20_000, 30_000),
    (30_000, 40_000),
    (40_000, 50_000),
    (50_000, 75_000),
    (75_000, 100_000),
    (100_000, None),
)

_OPEN_PRICE_CEILING: int = 1_000_000
_PRICE_SUBSPLITS: int = 5

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 500, 502, 503})

# Regex to extract detail-page listing IDs from SSR HTML href attributes.
_DETAIL_HREF_RE: re.Pattern[str] = re.compile(
    r'/carfinder/marktplatz/details/show/(\d+)',
)


class ComparisCHScraper(BasePortalScraper):
    """comparis.ch cars via SSR HTML scraping (T1, meta-aggregator)."""

    DOMAIN = "comparis.ch"
    COUNTRY = "CH"

    HOST = "www.comparis.ch"

    # ~10 listing cards per SSR page.
    PAGE_SIZE = 10
    MAX_PAGES = 200

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 25

    YEAR_BANDS: tuple[tuple[int, int], ...] = _YEAR_BANDS
    PRICE_BANDS: tuple[tuple[int, int | None], ...] = _PRICE_BANDS

    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    @property
    def _search_base(self) -> str:
        return f"https://{self.HOST}/carfinder/marktplatz"

    # -- primitives --------------------------------------------------------------

    def partition_params(self) -> list[dict[str, Any]]:
        """Year x price grid covering the full used-car inventory."""
        return [
            {"year_from": yf, "year_to": yt, "price_from": pf, "price_to": pt}
            for (yf, yt), (pf, pt) in product(self.YEAR_BANDS, self.PRICE_BANDS)
        ]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Explode a capped cell into per-year x finer-price sub-cells."""
        if params.get("_fine"):
            return []
        years = range(params["year_from"], params["year_to"] + 1)
        price_bands = self._split_price(params["price_from"], params["price_to"])
        return [
            {"year_from": y, "year_to": y, "price_from": pf, "price_to": pt, "_fine": True}
            for y, (pf, pt) in product(years, price_bands)
        ]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch one SSR HTML page; retry transient blocks; return detail URLs."""
        url = self._build_url(params, page_num)

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

            if status != 200:
                log.debug("HTTP %d (no retry) %s", status, url[:90])
                return []

            return self._extract(response.text)

        log.warning("all %d attempts failed: %s", self.RETRY_ATTEMPTS, url[:90])
        return []

    # -- helpers -----------------------------------------------------------------

    def _build_url(self, params: dict[str, Any], page_num: int) -> str:
        """Construct the search URL with year/price filters.

        comparis.ch uses 0-indexed pages, so page_num (1-based from the base
        class paginator) is decremented by 1.
        """
        page_index = page_num - 1

        pf = params["price_from"]
        pt = params.get("price_to")
        price_to_param = "" if pt is None else f"&priceto={pt}"

        return (
            f"{self._search_base}"
            f"?sort=2"
            f"&page={page_index}"
            f"&yearfrom={params['year_from']}"
            f"&yearto={params['year_to']}"
            f"&pricefrom={pf}"
            f"{price_to_param}"
            f"&condition=occasion"
        )

    def _extract(self, body: str) -> list[str]:
        """Extract detail URLs from SSR HTML by matching href attributes.

        Finds all hrefs matching /carfinder/marktplatz/details/show/{digits},
        deduplicates, and returns full canonical URLs.
        """
        if not body or not isinstance(body, str):
            return []

        seen: set[str] = set()
        out: list[str] = []

        for match in _DETAIL_HREF_RE.finditer(body):
            listing_id = match.group(1)
            url = f"{self._base_url}/carfinder/marktplatz/details/show/{listing_id}"
            if url not in seen:
                seen.add(url)
                out.append(url)

        return out

    @staticmethod
    def _split_price(pf: int, pt: int | None) -> list[tuple[int, int | None]]:
        """Split a price range into finer sub-bands for overflow subdivision."""
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

    async def _get(self, session: Any, url: str) -> Any | None:
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:  # transport-level
            log.debug("transport error %s: %s", url[:90], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(
                self.RETRY_BACKOFF_BASE ** attempt * factor + random.uniform(0, 0.25)
            )
