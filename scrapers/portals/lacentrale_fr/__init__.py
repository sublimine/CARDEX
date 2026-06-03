r"""
lacentrale.fr — France's reference used-car marketplace (Next.js SSR, DataDome).

lacentrale.fr is hard-blocked by DataDome on 100% of surfaces: plain curl_cffi
(any impersonate profile) returns 403 with `x-datadome: protected` + a `datadome`
cookie on every path — including `/robots.txt` and `/sitemap.xml`. There is NO
exploitable first-party JSON API (`api.lacentrale.fr` is NXDOMAIN; a fully-rendered
page fires only analytics/ad trackers, no search XHR/GraphQL). Listings are rendered
server-side inside `__NEXT_DATA__.props.pageProps.data.content` (a ~491 KB HTML
string of `vehicleCardV2` cards). Tier.T3: the coordinator injects a DataDome-solving
stealth-browser session that performs top-level navigations of `/listing?...&page=N`;
this scraper only issues GETs through the duck-typed `session`, so it imports and
unit-tests without a browser present, exactly like the AutoScout24 / mobile.de family.

Gold nuggets [VERIFIED 2026-06-03 in a real browser — docs/research/lacentrale-fr.md]:

  Search URL  GET https://www.lacentrale.fr/listing?<filters>&page=N
  Filters     (VERIFIED query params, echoed in __NEXT_DATA__.query):
                price  priceMin / priceMax   (EUR; omit max for an open top band)
                year   yearMin  / yearMax    (first-registration year, inclusive)
                make   makesModelsCommercialNames=RENAULT[:CLIO]  (NAME, not id —
                       avoided here so we never depend on a make-name table)
  Listings    server-rendered <a data-testid="vehicleCardV2"
                href="/auto-occasion-annonce-{id}.html">, 24/page.
  Listing re  /auto-occasion-annonce-(\d+)\.html  → host-prefix for the canonical URL.
  Pagination  `page` is 0-BASED (page=0 is the first page; page=120 returns ads with
              IDs disjoint from page 0). 24 ads/page; the SEO pager tops out at ~200
              → effective cap ≈ 200 × 24 ≈ 4,800 ads/query → search-grid partitioning
              is mandatory.
  Block sig   403 + `x-datadome: protected` + a `datadome` cookie; the block body
              loads `ct.captcha-delivery.com/i.js`. Detected by status + body marker.

Partition: year band × price band over all makes (lacentrale's make filter is a
NAME, but enumerating it is still a reference dependency we avoid). A capped cell is
subdivided into per-year × finer-price sub-cells — every DataDome-passing request is
expensive, so we prefer wide cells just under the cap over many tiny ones. Cross-cell
dedup is the base `seen` set on the canonical `/auto-occasion-annonce-{id}.html` URLs.
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
# Non-overlapping EUR price bands. The top band is open-ended (max=None → no
# priceMax param, an unbounded upper search).
_PRICE_BANDS: tuple[tuple[int, int | None], ...] = (
    (0, 5_000), (5_000, 10_000), (10_000, 15_000), (15_000, 20_000),
    (20_000, 30_000), (30_000, 50_000), (50_000, 100_000), (100_000, None),
)
_OPEN_PRICE_CEILING: int = 1_000_000
_PRICE_SUBSPLITS: int = 5

# ── HTTP / WAF behaviour ──────────────────────────────────────────────────────
_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 503})
# DataDome challenge markers — present in the block body (served as 403, but the
# coordinator's browser session may surface a soft challenge body on a 200 too).
_DATADOME_MARKERS: tuple[str, ...] = (
    "captcha-delivery.com",
    "x-datadome",
    "enable js and disable any ad blocker",
)


def _is_datadome_blocked(html: str) -> bool:
    """True when a body is a DataDome challenge rather than rendered listings."""
    lo = html.lower()
    return any(marker in lo for marker in _DATADOME_MARKERS)


class LaCentraleFRScraper(BasePortalScraper):
    """lacentrale.fr cars via DataDome-gated Next.js SSR navigations (T3)."""

    DOMAIN = "lacentrale.fr"
    COUNTRY = "FR"

    HOST = "www.lacentrale.fr"

    # 24 cards/page; the SEO pager tops out at ~200.
    PAGE_SIZE = 24
    MAX_PAGES = 200

    # DataDome is aggressive — back off hard on blocks.
    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 2.5
    REQUEST_TIMEOUT: int = 25

    YEAR_BANDS: tuple[tuple[int, int], ...] = _YEAR_BANDS
    PRICE_BANDS: tuple[tuple[int, int | None], ...] = _PRICE_BANDS

    # ── request shape ──────────────────────────────────────────────────────────
    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    @property
    def _search_base(self) -> str:
        return f"https://{self.HOST}/listing"

    @cached_property
    def _listing_re(self) -> re.Pattern[str]:
        """Match the numeric id in `/auto-occasion-annonce-<id>.html` hrefs."""
        return re.compile(r"/auto-occasion-annonce-(\d+)\.html")

    # ── primitives ─────────────────────────────────────────────────────────────
    def partition_params(self) -> list[dict[str, Any]]:
        """Year band × price band over all makes — no make-name refdata dependency."""
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
        """Fetch one listing page; retry DataDome blocks; return canonical ad URLs."""
        url = self._build_url(params, page_num)
        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            response = await self._get(session, url)
            if response is None:
                await self._retry_backoff(attempt)
                continue

            status = response.status_code
            if status in _BLOCK_STATUSES:
                log.debug("HTTP %d (%d/%d) %s", status, attempt, self.RETRY_ATTEMPTS, url[:90])
                await self._retry_backoff(attempt, factor=2.0)
                continue
            if status != 200:
                log.debug("HTTP %d (no retry) %s", status, url[:90])
                return []

            html = response.text
            if _is_datadome_blocked(html):
                log.warning("datadome challenge (%d/%d) %s", attempt, self.RETRY_ATTEMPTS, url[:90])
                await self._retry_backoff(attempt, factor=2.0)
                continue

            return self._extract(html)

        log.warning("all %d attempts failed: %s", self.RETRY_ATTEMPTS, url[:90])
        return []

    # ── helpers ────────────────────────────────────────────────────────────────
    def _build_url(self, params: dict[str, Any], page_num: int) -> str:
        # `page` is 0-based: base feeds page_num 1..MAX_PAGES, so page=0 is the
        # first page. Open top band omits priceMax for an unbounded upper search.
        parts = [
            f"yearMin={params['year_from']}",
            f"yearMax={params['year_to']}",
            f"priceMin={params['price_from']}",
        ]
        pt = params.get("price_to")
        if pt is not None:
            parts.append(f"priceMax={pt}")
        parts.append(f"page={page_num - 1}")
        return f"{self._search_base}?{'&'.join(parts)}"

    def _extract(self, html: str) -> list[str]:
        """Canonical detail URLs from `vehicleCardV2` hrefs, deduped within page."""
        seen: set[str] = set()
        out: list[str] = []
        for match in self._listing_re.finditer(html):
            ad_id = match.group(1)
            canonical = f"{self._base_url}/auto-occasion-annonce-{ad_id}.html"
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
