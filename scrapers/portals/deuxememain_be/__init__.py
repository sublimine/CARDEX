"""
2ememain.be — Belgium, French-language classified portal (~102k cars).

2ememain.be is the francophone mirror of 2dehands.be (same Adevinta/Marktplaats
backend, same LRP API, same CloudFront CDN, same database). The only difference
is the hostname and the UI language. The search API at /lrp/api/search is
identical in parameters, pagination shape, and JSON response schema.

Since tweedehands_be already scrapes via 2dehands.be, this scraper targets
the *same inventory* through the French-language hostname. In a production
deployment the coordinator would typically run EITHER tweedehands_be OR
deuxememain_be, not both — but both are registered so the router can dispatch
whichever domain appears in a work_queue row.

Gold nuggets [VERIFIED 2026-06-04 — web_fetch confirms identical Adevinta layout]:

  Search URL  GET https://www.2ememain.be/lrp/api/search
                  ?l1CategoryId=91&offset={O}&limit=30
                  &attributeRanges[]=constructionYear:{Yf}:{Yt}
                  &attributeRanges[]=PriceCents:{Pf*100}:{Pt*100}
  Category    l1CategoryId=91 = "Autos" (same category ID as 2dehands).
  Listings    JSON `listings[]`; per-ad `vipUrl` (relative) + `itemId` ("m"+digits).
  Detail URL  /v/autos/{brand}/m{ITEM_ID}-{slug}   [VERIFIED from page HTML]
  Pagination  offset/limit. maxAllowedPageNumber=167; ~5,010 listings per query.
  Block sig   CloudFront 403/429; no DataDome/Akamai observed.

Partition: year band × price band (identical grid to tweedehands_be).
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

# ── search grid (identical to 2dehands.be / marktplaats.nl) ──────────────────
_YEAR_BANDS: tuple[tuple[int, int], ...] = (
    (1990, 2000), (2000, 2005), (2005, 2008), (2008, 2011),
    (2011, 2014), (2014, 2016), (2016, 2018), (2018, 2020),
    (2020, 2022), (2022, 2024), (2024, 2026),
)
_PRICE_BANDS: tuple[tuple[int, int | None], ...] = (
    (0, 5_000), (5_000, 10_000), (10_000, 15_000), (15_000, 20_000),
    (20_000, 30_000), (30_000, 50_000), (50_000, 100_000), (100_000, None),
)
_OPEN_PRICE_CEILING: int = 1_000_000
_PRICE_SUBSPLITS: int = 5

_CARS_CATEGORY_ID: int = 91  # "Autos"

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 503})


class DeuxememainBEScraper(BasePortalScraper):
    """2ememain.be cars via the LRP JSON API (T0, French mirror of 2dehands.be)."""

    DOMAIN = "2ememain.be"
    COUNTRY = "BE"

    HOST = "www.2ememain.be"

    # offset/limit paging. limit=30 (site default); window caps at page 167.
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
        """Extract detail links from JSON `listings[]`, deduped per page."""
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            log.debug("non-JSON body from 2ememain LRP")
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
