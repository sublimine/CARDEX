"""
largus.fr (Occasion) — France classified-aggregator (cars, ~272,145 listings).

The cars marketplace lives at the `occasion.largus.fr` subdomain — the editorial
content stays at `www.largus.fr`. The marketplace is served by bare Drupal HTTP
with no Cloudflare/Akamai/DataDome on any surface researched; naked `curl_cffi`
`impersonate="chrome"` passes. Tier.T1. The coordinator still injects a curl_cffi
session; this scraper only issues GETs through the duck-typed `session` and parses
`response.text` as HTML, so it imports and unit-tests without curl_cffi present.

Gold nuggets [VERIFIED 2026-06-03 against the live site — docs/research/largus-fr.md]:

  Search URL  GET https://occasion.largus.fr/auto/
                  ?price_min={Pf_CENTS}&price_max={Pt_CENTS}
                  &year_min={Yf}&year_max={Yt}&currentpage={N}
  Filters     price_min / price_max  EUR ×100 (CENTS, NOT euros).         [VERIFIED]
              year_min  / year_max   4-digit year, inclusive.             [VERIFIED]
              mileage_min/mileage_max  km (NOT cents — distinct unit).    [VERIFIED]
              currentpage            1-based page number.                 [VERIFIED]
  Listings    Server-rendered HTML, 24 unique ads per page.
  Detail URL  /auto/annonce-<UUID>-<brand>-<model>-<year>-<mileage>km     [VERIFIED]
              The UUID matches [0-9a-f-]{36}; the slug is informative, not a key.
              Canonical URL = "https://occasion.largus.fr" + path.
  Pagination  currentpage caps at 416 (page 417 → HTTP 404). 416 × 24 ≈ 9,984
              ads per filter — vs 272,145 total → year×price partitioning is
              mandatory.                                                  [VERIFIED]
  Block sig   None observed. The 404 ceiling is the only structural signal.

Partition: year band × (price band in CENTS) over all makes — no make-slug refdata
dependency. A capped cell is subdivided into per-year × finer-price sub-cells.
Cross-cell dedup is the base `seen` set on canonical /auto/annonce-<UUID>… URLs.
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

# ── search grid (verified filter vocabulary; prices in EUR, converted to cents on request) ─
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

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 500, 502, 503})


class LargusFRScraper(BasePortalScraper):
    """largus.fr cars via the occasion.largus.fr SSR endpoint (T1)."""

    DOMAIN = "largus.fr"
    COUNTRY = "FR"

    HOST = "occasion.largus.fr"

    # 24 unique ads/page; pager caps at 416 (VERIFIED — page 417 returns 404).
    PAGE_SIZE = 24
    MAX_PAGES = 416

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
        return f"https://{self.HOST}/auto/"

    @cached_property
    def _listing_re(self) -> re.Pattern[str]:
        """Match `/auto/annonce-<UUID>-<slug>` paths; UUID = 8-4-4-4-12 hex with dashes."""
        return re.compile(
            r"/auto/(annonce-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-[a-z0-9\-]+)"
        )

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

            return self._extract(self._read_body(response))

        log.warning("all %d attempts failed: %s", self.RETRY_ATTEMPTS, url[:90])
        return []

    # ── helpers ────────────────────────────────────────────────────────────────
    def _build_url(self, params: dict[str, Any], page_num: int) -> str:
        # price_min/price_max in CENTS (VERIFIED), year_min/year_max in years.
        # Open top band drops price_max entirely.
        pf_cents = params["price_from"] * 100
        parts = [f"price_min={pf_cents}"]
        pt = params.get("price_to")
        if pt is not None:
            parts.append(f"price_max={pt * 100}")
        parts.extend([
            f"year_min={params['year_from']}",
            f"year_max={params['year_to']}",
            f"currentpage={page_num}",
        ])
        return f"{self._search_base}?{'&'.join(parts)}"

    def _extract(self, html: str) -> list[str]:
        """Canonical detail URLs from /auto/annonce-<UUID>-<slug>, within-page deduped."""
        seen: set[str] = set()
        out: list[str] = []
        for match in self._listing_re.finditer(html):
            slug = match.group(1)
            canonical = f"{self._base_url}/auto/{slug}"
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
