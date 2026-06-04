"""
nederlandmobiel.nl -- Netherlands classifieds (PHP SSR, ~313,584 auto listings).

nederlandmobiel.nl is a traditional PHP server-rendered site. Content-Type is
``text/html; charset=ISO-8859-15``. There is NO WAF — plain requests pass. Tier.T0.

Gold nuggets [research 2026-06-04]:

  Search URL    GET https://www.nederlandmobiel.nl/index.php
                    ?module=zoeken&voertuig=auto                        [VERIFIED]
  Pagination    GET params: &pagina={N} (1-based).                      [ASSUMED]
  Detail URL    /tweedehands-auto/{brand}/{slug}/{numeric_id}
                e.g. /tweedehands-auto/fiat/panda-grande.../22273556    [VERIFIED]
  Image URLs    https://images.nederlandmobiel.nl/auto/{id}/320/1.jpg   [VERIFIED]
  Brand filter  Brands use numeric IDs in path-style URLs:
                auto-occasions/17/audi, auto-occasions/29/bmw           [VERIFIED]
  Sort param    ``laatst geplaatst`` (latest first)                     [VERIFIED]
  Price filter  prijs_van, prijs_tm (EUR integer)                       [ASSUMED from HTML form]
  Year filter   bouwjaar_van, bouwjaar_tm                               [ASSUMED from HTML form]
  Items/page    30 results per search page                              [ASSUMED]
  Coverage      ~313,584 auto listings; aggressive price-band
                partitioning required.                                  [VERIFIED count]
  Encoding      ISO-8859-15 (Latin-9). Responses are decoded by the
                session layer; we operate on str.                       [VERIFIED]
  Block sig     Standard transient HTTP errors (403/429/5xx).           [ASSUMED]

Strategy: price-band partitioning (313k needs aggressive splitting). Each price band
paginates up to MAX_PAGES. Capped bands are subdivided into finer price sub-bands.
Listing URLs are regex-extracted from the server-rendered HTML using the autotrack.nl
HTML-scrape pattern.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from functools import cached_property
from itertools import product
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 500, 502, 503})

# -- search grid (price partitioning for 313k inventory) -----------------------
# Aggressive price bands to keep each segment under the pagination ceiling.
_PRICE_BANDS: tuple[tuple[int, int | None], ...] = (
    (0, 1_000), (1_000, 2_000), (2_000, 3_000), (3_000, 4_000),
    (4_000, 5_000), (5_000, 6_000), (6_000, 7_000), (7_000, 8_000),
    (8_000, 9_000), (9_000, 10_000), (10_000, 12_500), (12_500, 15_000),
    (15_000, 17_500), (17_500, 20_000), (20_000, 25_000), (25_000, 30_000),
    (30_000, 40_000), (40_000, 50_000), (50_000, 75_000), (75_000, 100_000),
    (100_000, None),
)
_OPEN_PRICE_CEILING: int = 500_000
_PRICE_SUBSPLITS: int = 5


class NederlandMobielNLScraper(BasePortalScraper):
    """nederlandmobiel.nl auto via PHP SSR HTML regex extraction (T0, price grid)."""

    DOMAIN = "nederlandmobiel.nl"
    COUNTRY = "NL"

    HOST = "www.nederlandmobiel.nl"

    # 30 items/page [ASSUMED]; MAX_PAGES with margin.
    PAGE_SIZE = 30
    MAX_PAGES = 500

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    PRICE_BANDS: tuple[tuple[int, int | None], ...] = _PRICE_BANDS

    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    @cached_property
    def _listing_re(self) -> re.Pattern[str]:
        r"""Match ``href="/tweedehands-auto/{brand}/{slug}/{numeric_id}"`` detail links.

        Captures the full path (group 1) and the trailing numeric ID (group 2)
        for dedup. The regex requires at least three path segments after
        ``/tweedehands-auto/`` to avoid matching category/index pages.
        """
        return re.compile(
            r'href="(/tweedehands-auto/[^"/]+/[^"/]+/(\d+))"',
        )

    # -- primitives ----------------------------------------------------------
    def partition_params(self) -> list[dict[str, Any]]:
        """Price-band grid covering ~313k auto inventory."""
        return [
            {"price_from": pf, "price_to": pt}
            for pf, pt in self.PRICE_BANDS
        ]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Explode a capped price band into finer sub-bands."""
        if params.get("_fine"):
            return []
        price_bands = self._split_price(params["price_from"], params["price_to"])
        return [
            {"price_from": pf, "price_to": pt, "_fine": True}
            for pf, pt in price_bands
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
        """Fetch one listing page; retry transient blocks; return detail URLs."""
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

    # -- helpers --------------------------------------------------------------
    def _build_url(self, params: dict[str, Any], page_num: int) -> str:
        """Construct the search URL with price filters and pagination."""
        base = f"{self._base_url}/index.php?module=zoeken&voertuig=auto"
        pf = params.get("price_from")
        pt = params.get("price_to")
        if pf is not None:
            base += f"&prijs_van={pf}"
        if pt is not None:
            base += f"&prijs_tm={pt}"
        if page_num > 1:
            base += f"&pagina={page_num}"
        return base

    def _extract(self, html: str) -> list[str]:
        """Canonical detail URLs from listing anchors, within-page deduped on NID."""
        seen: set[str] = set()
        out: list[str] = []
        for match in self._listing_re.finditer(html):
            path = match.group(1)  # /tweedehands-auto/{brand}/{slug}/{nid}
            canonical = f"{self._base_url}{path}"
            if canonical not in seen:
                seen.add(canonical)
                out.append(canonical)
        return out

    async def _get(self, session: Any, url: str) -> Any | None:
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:
            log.debug("transport error %s: %s", url[:90], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(self.RETRY_BACKOFF_BASE**attempt * factor + random.uniform(0, 0.25))
