r"""
mobile.de — Germany's largest car marketplace (~1.4M listings).

mobile.de fronts every HTML document and its SRP JSON route with Akamai Bot
Manager. Plain curl_cffi is 403-blocked on the SRP document (TLS impersonation
alone is insufficient — Akamai wants a valid `_abck` sensor payload that only
real browser JS produces), so this portal is Tier.T2: the coordinator injects a
stealth-browser session that performs top-level navigations. This scraper only
issues GETs through the duck-typed `session`, so it imports and unit-tests
without a browser present, exactly like the AutoScout24 family.

Gold nuggets [VERIFIED 2026-06-03 against live mobile.de — docs/research/mobile-de.md]:

  Search URL  GET https://suchen.mobile.de/fahrzeuge/search.html
                  ?vc=Car&s=Car&fr={Yf}:{Yt}&p={Pf}:{Pt}&dam=false
                  &sb=rel&od=up&ref=srp&isSearchRequest=true&pageNumber={N}
  Listings    server-rendered <a href="/fahrzeuge/details.html?id=...">, 24/page.
              The pre-hydration __INITIAL_STATE__ blob is cleared during React
              hydration, so the durable surface is the hrefs in the raw HTML.
  Listing re  /\/fahrzeuge\/details\.html\?id=(\d+)/  → canonical strips tracking.
  Pagination  pageNumber=1..50. Page size ~20-24. Pager HARD-CAPS at page 50
              (~1000 listings/search) even when hit-count reports 14,205 →
              search-grid partitioning is mandatory.
  Block sig   403 + `server: AkamaiGHost` + branded "Zugriff verweigert /
              Access denied" body. The `_abck` cookie ending `~-1~` means the
              sensor was not validated; but the cookie is set opportunistically
              on 200s too, so we key off status + deny-body, not cookie presence.

Partition strategy: year band × price band over ALL makes, so we never depend on
the make-id reference map (which mobile.de delivers only inside its app bundle —
[ASSUMED], not a clean route). When a cell hits the page-50 ceiling we subdivide
it into per-year × finer-price sub-cells (verified `fr`/`p` params only), the
single most effective one-level split the BasePortalScraper contract allows.
Segments overlap on year boundaries, but cap detection is structural (pagination
exhausted MAX_PAGES) and the base `seen` set dedupes, so overlap costs fetches
but never double-emits.
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

# ── search grid (verified gold nuggets) ───────────────────────────────────────
# Year ranges are inclusive `fr=from:to`. Bands touch on boundary years; the
# resulting overlap is absorbed by the base `seen` dedup set.
_YEAR_BANDS: tuple[tuple[int, int], ...] = (
    (1990, 2000), (2000, 2005), (2005, 2008), (2008, 2011),
    (2011, 2014), (2014, 2016), (2016, 2018), (2018, 2020),
    (2020, 2022), (2022, 2024), (2024, 2026),
)
# Non-overlapping `p=min:max` EUR bands. The top band is open-ended (max=None).
_PRICE_BANDS: tuple[tuple[int, int | None], ...] = (
    (0, 5_000), (5_000, 10_000), (10_000, 15_000), (15_000, 20_000),
    (20_000, 30_000), (30_000, 50_000), (50_000, 100_000), (100_000, None),
)
# When subdividing the open-ended top band we need a concrete ceiling to split.
_OPEN_PRICE_CEILING: int = 1_000_000
# Each capped price band is split into this many finer sub-bands on subdivision.
_PRICE_SUBSPLITS: int = 5

# ── HTTP / WAF behaviour ──────────────────────────────────────────────────────
_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 503})
# Akamai's branded deny page can also arrive as a 200 body in edge cases; detect
# it by content. Lowercased substring match against the response body.
_AKAMAI_MARKERS: tuple[str, ...] = (
    "zugriff verweigert",
    "access denied",
    "akamai",
    "you don't have permission to access",
)


def _is_softblocked(html: str) -> bool:
    """True when a 200 body is actually an Akamai deny/challenge page."""
    lo = html.lower()
    return any(marker in lo for marker in _AKAMAI_MARKERS)


class MobileDeScraper(BasePortalScraper):
    """mobile.de SRP enumeration via Akamai-gated top-level navigations (T2)."""

    DOMAIN = "mobile.de"
    COUNTRY = "DE"

    HOST = "suchen.mobile.de"

    # Page size ~20-24; treat as 20 for short-page detection. Pager caps at 50.
    PAGE_SIZE = 20
    MAX_PAGES = 50

    # Akamai is aggressive; back off harder than the AS24 default on blocks.
    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 2.5
    REQUEST_TIMEOUT: int = 25

    YEAR_BANDS: tuple[tuple[int, int], ...] = _YEAR_BANDS
    PRICE_BANDS: tuple[tuple[int, int | None], ...] = _PRICE_BANDS

    # ── derived request shape ─────────────────────────────────────────────────
    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    @property
    def _search_base(self) -> str:
        return f"https://{self.HOST}/fahrzeuge/search.html"

    @cached_property
    def _listing_re(self) -> re.Pattern[str]:
        """Match the numeric ad id in `/fahrzeuge/details.html?id=<id>` hrefs."""
        return re.compile(r"/fahrzeuge/details\.html\?id=(\d+)")

    # ── primitives ─────────────────────────────────────────────────────────────
    def partition_params(self) -> list[dict[str, Any]]:
        """Year band × price band over all makes — no make-id refdata dependency."""
        return [
            {"year_from": yf, "year_to": yt, "price_from": pf, "price_to": pt}
            for (yf, yt), (pf, pt) in product(self.YEAR_BANDS, self.PRICE_BANDS)
        ]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """
        A capped cell is exploded into (per-year) × (finer-price) sub-cells.

        This is the strongest split the one-level subdivision contract permits:
        a year *band* becomes individual years and the price band is cut into
        `_PRICE_SUBSPLITS` finer ranges, using only VERIFIED `fr`/`p` params.
        Sub-cells already carry single years and fine prices, so a sub-cell that
        is fed back here cannot split further and returns [].
        """
        if params.get("_fine"):
            return []
        years = range(params["year_from"], params["year_to"] + 1)
        price_bands = self._split_price(params["price_from"], params["price_to"])
        return [
            {
                "year_from": y,
                "year_to": y,
                "price_from": pf,
                "price_to": pt,
                "_fine": True,
            }
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
        # Re-open the final band's ceiling when the original band was open-ended.
        if pt is None:
            last_lo, _ = bands[-1]
            bands[-1] = (last_lo, None)
        return bands

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch one SRP page; retry Akamai blocks; return canonical detail URLs."""
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
            if _is_softblocked(html):
                log.warning("akamai softblock (%d/%d) %s", attempt, self.RETRY_ATTEMPTS, url[:90])
                await self._retry_backoff(attempt, factor=2.0)
                continue

            return self._extract(html)

        log.warning("all %d attempts failed: %s", self.RETRY_ATTEMPTS, url[:90])
        return []

    # ── helpers ────────────────────────────────────────────────────────────────
    def _build_url(self, params: dict[str, Any], page_num: int) -> str:
        pf = params["price_from"]
        pt = params.get("price_to")
        price = f"{pf}:{pt if pt is not None else ''}"
        return (
            f"{self._search_base}?vc=Car&s=Car"
            f"&fr={params['year_from']}:{params['year_to']}"
            f"&p={price}"
            f"&dam=false&sb=rel&od=up&ref=srp&isSearchRequest=true"
            f"&pageNumber={page_num}"
        )

    def _extract(self, html: str) -> list[str]:
        """Canonical detail URLs (tracking stripped), deduped within the page."""
        seen: set[str] = set()
        out: list[str] = []
        for match in self._listing_re.finditer(html):
            ad_id = match.group(1)
            canonical = f"{self._base_url}/fahrzeuge/details.html?id={ad_id}"
            if canonical not in seen:
                seen.add(canonical)
                out.append(canonical)
        return out

    async def _get(self, session: Any, url: str) -> Any | None:
        """One GET; None on transport error so the retry loop can back off."""
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:  # transport-level: DNS, reset, timeout, proxy drop
            log.debug("transport error %s: %s", url[:90], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        """Exponential backoff, skipped on the final attempt (about to give up)."""
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(self.RETRY_BACKOFF_BASE**attempt * factor + random.uniform(0, 0.25))
