"""
marktplaats.nl — Netherlands' largest classifieds, cars vertical (~268k listings).

The easiest target in the fleet: the internal LRP search API is an open JSON
route behind AWS CloudFront with NO Cloudflare/Akamai/DataDome and no required
auth, cookie or TLS gate (it answers 200 to a naked client). Tier.T0. The
coordinator still injects a curl_cffi session for hygiene; this scraper only
issues GETs through the duck-typed `session` and parses `response.text` as JSON,
so it imports and unit-tests without curl_cffi present.

Gold nuggets [VERIFIED 2026-06-03 — docs/research/marktplaats-nl.md]:

  Search URL  GET https://www.marktplaats.nl/lrp/api/search
                  ?l1CategoryId=91&offset={O}&limit=30
                  &attributeRanges[]=constructionYear:{Yf}:{Yt}
                  &attributeRanges[]=PriceCents:{Pf*100}:{Pt*100}
  Category    l1CategoryId=91 = "Auto's" (cars), echoed back in searchRequest.
  Listings    JSON `listings[]`; per-ad `vipUrl` (relative) + `itemId` ("m"+digits).
  Year filter attributeRanges[]=constructionYear:from:to (inclusive).
  Price filter attributeRanges[]=PriceCents:from:to  — value in CENTS.
  Pagination  offset/limit. `maxAllowedPageNumber=167`; ~5,010 listings reachable
              per query (167×30). offset past the window yields empty listings[]
              (no error) → search-grid partitioning is mandatory (268k ≫ 5k).

Partition: year band × price band over all makes — no make-id table dependency
(marktplaats delivers make ids only as opaque attribute ids). A capped cell is
subdivided into per-year × finer-price sub-cells. Cross-cell dedup is the base
`seen` set on itemId-bearing URLs.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from functools import cached_property  # noqa: F401  (kept for parity; not required)
from itertools import product
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

# ── search grid (verified gold nuggets) ───────────────────────────────────────
_YEAR_BANDS: tuple[tuple[int, int], ...] = (
    (1990, 2000), (2000, 2005), (2005, 2008), (2008, 2011),
    (2011, 2014), (2014, 2016), (2016, 2018), (2018, 2020),
    (2020, 2022), (2022, 2024), (2024, 2026),
)
# Non-overlapping EUR bands (converted to cents at request time). Top is open.
_PRICE_BANDS: tuple[tuple[int, int | None], ...] = (
    (0, 5_000), (5_000, 10_000), (10_000, 15_000), (15_000, 20_000),
    (20_000, 30_000), (30_000, 50_000), (50_000, 100_000), (100_000, None),
)
_OPEN_PRICE_CEILING: int = 1_000_000
_PRICE_SUBSPLITS: int = 5

_CARS_CATEGORY_ID: int = 91  # "Auto's"

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 503})


class MarktplaatsNLScraper(BasePortalScraper):
    """marktplaats.nl cars via the open LRP JSON search API (T0)."""

    DOMAIN = "marktplaats.nl"
    COUNTRY = "NL"

    HOST = "www.marktplaats.nl"

    # offset/limit paging. limit=30 (site default); window tops at page 167.
    PAGE_SIZE = 30
    MAX_PAGES = 167

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    YEAR_BANDS: tuple[tuple[int, int], ...] = _YEAR_BANDS
    PRICE_BANDS: tuple[tuple[int, int | None], ...] = _PRICE_BANDS

    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    @property
    def _search_base(self) -> str:
        return f"https://{self.HOST}/lrp/api/search"

    # ── primitives ─────────────────────────────────────────────────────────────
    def partition_params(self) -> list[dict[str, Any]]:
        return [
            {"year_from": yf, "year_to": yt, "price_from": pf, "price_to": pt}
            for (yf, yt), (pf, pt) in product(self.YEAR_BANDS, self.PRICE_BANDS)
        ]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Explode a capped cell into per-year × finer-price sub-cells."""
        if params.get("_fine"):
            return []
        years = range(params["year_from"], params["year_to"] + 1)
        price_bands = self._split_price(params["price_from"], params["price_to"])
        return [
            {"year_from": y, "year_to": y, "price_from": pf, "price_to": pt, "_fine": True}
            for y, (pf, pt) in product(years, price_bands)
        ]

    @staticmethod
    def _split_price(pf: int, pt: int | None) -> list[tuple[int, int | None]]:
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
        """Fetch one offset window; retry transient blocks; return detail URLs."""
        offset = (page_num - 1) * self.PAGE_SIZE
        url = self._build_url(params, offset)
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

    # ── helpers ────────────────────────────────────────────────────────────────
    def _build_url(self, params: dict[str, Any], offset: int) -> str:
        # Mirror the VERIFIED raw query exactly: `:` and `[]` are left unescaped,
        # which the LRP backend accepts (and which matches the captured request).
        pf_cents = params["price_from"] * 100
        pt = params.get("price_to")
        price_to_cents = "" if pt is None else str(pt * 100)
        ranges = (
            f"&attributeRanges[]=constructionYear:{params['year_from']}:{params['year_to']}"
            f"&attributeRanges[]=PriceCents:{pf_cents}:{price_to_cents}"
        )
        return (
            f"{self._search_base}?l1CategoryId={_CARS_CATEGORY_ID}"
            f"&offset={offset}&limit={self.PAGE_SIZE}"
            f"{ranges}&sortBy=SORT_INDEX&sortOrder=DECREASING"
        )

    def _extract(self, body: str) -> list[str]:
        """Pull `vipUrl` detail links from the JSON `listings[]`, deduped per page."""
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            log.debug("non-JSON body from marktplaats LRP")
            return []
        listings = payload.get("listings") if isinstance(payload, dict) else None
        if not isinstance(listings, list):
            return []
        seen: set[str] = set()
        out: list[str] = []
        for ad in listings:
            vip = ad.get("vipUrl") if isinstance(ad, dict) else None
            if not isinstance(vip, str) or not vip:
                continue
            full = vip if vip.startswith("http") else f"{self._base_url}{vip}"
            if full not in seen:
                seen.add(full)
                out.append(full)
        return out

    async def _get(self, session: Any, url: str) -> Any | None:
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:  # transport-level
            log.debug("transport error %s: %s", url[:90], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(self.RETRY_BACKOFF_BASE**attempt * factor + random.uniform(0, 0.25))
