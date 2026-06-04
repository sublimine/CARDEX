"""
paruvendu.fr — France classified (cars, ~120,066 listings).

paruvendu.fr is served by plain Apache with no Cloudflare/Akamai/DataDome on any
surface researched. A naked `curl_cffi` `impersonate="chrome"` GET passes for the
home, the listing index and the search endpoint. Tier.T1. The coordinator still
injects a curl_cffi session; this scraper only issues GETs through the duck-typed
`session` and parses `response.text` as HTML, so it imports and unit-tests without
curl_cffi present, exactly like the marktplaats / coches.net family.

Gold nuggets [VERIFIED 2026-06-03 against the live site — docs/research/paruvendu-fr.md]:

  Search URL  GET https://www.paruvendu.fr/auto-moto/listefo/default/default
                  ?r=VVO00000&p={N}&px0={Pf}&px1={Pt}&a0={Yf}&a1={Yt}
  Rubric      r=VVO00000   "voiture occasion"; the cars rubric.   [VERIFIED via form]
  Filters     px0/px1  price floor/ceiling (EUR; integers).        [VERIFIED counter]
              a0/a1    first-registration year floor/ceiling.      [VERIFIED counter]
              km0/km1  km floor/ceiling (NOT used — year×price is sufficient).
              p        page number, 1-based.                       [VERIFIED]
  Listings    Server-rendered HTML; 25 unique ads/page (a 26th anchor is a
              sponsored-slot duplicate, deduped within page).
  Detail URL  /a/voiture-occasion/<brand>/<model>/<AD_ID>           [VERIFIED]
              AD_ID matches `[A-Z0-9]+`. Host is fixed at https://www.paruvendu.fr.
  Pagination  HARD CAP at page 500 (~12,500 ads/query). p>=501 silently rewinds
              and re-serves page 1 ad-for-ad — `seen` would absorb the duplicates
              but we'd waste requests. With 120k inventory, year×price partitioning
              is mandatory.                                         [VERIFIED binary search]
  Block sig   Apache plain 4xx/5xx; no challenge body observed.

Partition: year band × price band over all makes — the make filter would require a
make-code table (`VVOAU000`=Audi, etc.) which is a refdata dependency we avoid. A
capped cell is subdivided into per-year × finer-price sub-cells; cross-cell dedup is
the base `seen` set on canonical /a/voiture-occasion/.../<AD_ID> URLs.
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

# ── search grid (verified filter vocabulary) ──────────────────────────────────
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

_CARS_RUBRIC: str = "VVO00000"  # voiture-occasion

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 500, 502, 503})


class ParuVenduFRScraper(BasePortalScraper):
    """paruvendu.fr cars via the Apache-served listefo HTML endpoint (T1)."""

    DOMAIN = "paruvendu.fr"
    COUNTRY = "FR"

    HOST = "www.paruvendu.fr"

    # 25 unique ads per page after dedup; pager caps at 500 (VERIFIED binary search).
    PAGE_SIZE = 25
    MAX_PAGES = 500

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
        return f"https://{self.HOST}/auto-moto/listefo/default/default"

    @cached_property
    def _listing_re(self) -> re.Pattern[str]:
        """Match the brand, model and id of `/a/voiture-occasion/<brand>/<model>/<id>` hrefs."""
        return re.compile(r"/a/voiture-occasion/([a-z0-9\-]+)/([a-z0-9\-]+)/([A-Z0-9]+)")

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
        """Fetch one listing page; retry transient blocks; return canonical ad URLs."""
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

    # ── helpers ────────────────────────────────────────────────────────────────
    def _build_url(self, params: dict[str, Any], page_num: int) -> str:
        # Mirror the verified query: r + p + px0/px1 + a0/a1. Open top band drops px1.
        parts = [
            f"r={_CARS_RUBRIC}",
            f"p={page_num}",
            f"px0={params['price_from']}",
        ]
        pt = params.get("price_to")
        if pt is not None:
            parts.append(f"px1={pt}")
        parts.append(f"a0={params['year_from']}")
        parts.append(f"a1={params['year_to']}")
        return f"{self._search_base}?{'&'.join(parts)}"

    def _extract(self, html: str) -> list[str]:
        """Canonical detail URLs from /a/voiture-occasion/.../<ID> hrefs, within-page deduped."""
        seen: set[str] = set()
        out: list[str] = []
        for match in self._listing_re.finditer(html):
            brand, model, ad_id = match.group(1), match.group(2), match.group(3)
            canonical = f"{self._base_url}/a/voiture-occasion/{brand}/{model}/{ad_id}"
            if canonical not in seen:
                seen.add(canonical)
                out.append(canonical)
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
