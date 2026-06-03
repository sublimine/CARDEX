r"""
kleinanzeigen.de — Germany's largest classifieds (ex-eBay Kleinanzeigen), cars.

kleinanzeigen sits behind Akamai, but its category result pages are served
*passively*: a plain top-level GET returns the fully server-rendered listing HTML
without a validated `_abck` sensor (the sensor is only enforced on interactive /
write flows). It is therefore Tier.T2 in the registry (Akamai, escalates to T3)
but reads like a T1 HTML target in practice. The coordinator injects a session;
this scraper only issues GETs through the duck-typed `session`, so it imports and
unit-tests without curl_cffi / a browser present, like the AS24 family.

Gold nuggets [VERIFIED 2026-06-03 against live kleinanzeigen — docs/research/kleinanzeigen-de.md]:

  Base URL    GET https://www.kleinanzeigen.de/s-autos/c216   (c216 = "Autos")
  Filters     are URL PATH segments, not query params:
                price  /preis:{min}:{max}/   (before the c-node; max empty = open)
                year   c216+autos.ez_i:{from},{to}   (COMMA range, glued to c216)
                page   /seite:{n}/           (before the c-node)
              Combined: /s-autos/preis:5000:10000/seite:2/c216+autos.ez_i:2018,2019
  Listings    server-rendered <a href="/s-anzeige/<slug>/<id>-216-<n>">, ~27/page.
  Listing re  /s-anzeige/[^"']+/\d+-216-\d+   → prefix host for the canonical URL.
  Pagination  /seite:{n}/, HARD-CAPS at page 50 (~1,350 ads/search) regardless of
              the reported hit count → search-grid partitioning is mandatory.
  Block sig   403 + Akamai deny body ("Zugriff verweigert" / "Access denied").

Partition: year band × price band over all makes (kleinanzeigen exposes makes as
opaque `autos.marke_s` attribute ids — avoided). A capped cell is subdivided into
per-year × finer-price sub-cells. Cross-cell dedup is the base `seen` set on the
canonical ad URLs.
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
_YEAR_BANDS: tuple[tuple[int, int], ...] = (
    (1990, 2000), (2000, 2005), (2005, 2008), (2008, 2011),
    (2011, 2014), (2014, 2016), (2016, 2018), (2018, 2020),
    (2020, 2022), (2022, 2024), (2024, 2026),
)
# Non-overlapping EUR price bands. The top band is open-ended (max=None → empty).
_PRICE_BANDS: tuple[tuple[int, int | None], ...] = (
    (0, 5_000), (5_000, 10_000), (10_000, 15_000), (15_000, 20_000),
    (20_000, 30_000), (30_000, 50_000), (50_000, 100_000), (100_000, None),
)
_OPEN_PRICE_CEILING: int = 1_000_000
_PRICE_SUBSPLITS: int = 5

# ── HTTP / WAF behaviour ──────────────────────────────────────────────────────
_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 503})
_AKAMAI_MARKERS: tuple[str, ...] = (
    "zugriff verweigert",
    "access denied",
    "you don't have permission to access",
    "reference #",  # Akamai/edge deny pages carry an edge reference id
)


def _is_softblocked(html: str) -> bool:
    """True when a 200 body is actually an Akamai deny/challenge page."""
    lo = html.lower()
    return any(marker in lo for marker in _AKAMAI_MARKERS)


class KleinanzeigenDEScraper(BasePortalScraper):
    """kleinanzeigen.de cars via passively-served Akamai category HTML (T2)."""

    DOMAIN = "kleinanzeigen.de"
    COUNTRY = "DE"

    HOST = "www.kleinanzeigen.de"

    # ~27 listings/page; the pager hard-caps at 50.
    PAGE_SIZE = 27
    MAX_PAGES = 50

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 2.0
    REQUEST_TIMEOUT: int = 25

    YEAR_BANDS: tuple[tuple[int, int], ...] = _YEAR_BANDS
    PRICE_BANDS: tuple[tuple[int, int | None], ...] = _PRICE_BANDS

    # ── request shape ──────────────────────────────────────────────────────────
    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    @cached_property
    def _listing_re(self) -> re.Pattern[str]:
        """Match `/s-anzeige/<slug>/<id>-216-<n>` listing hrefs in the raw HTML."""
        return re.compile(r"/s-anzeige/[^\"']+?/\d+-216-\d+")

    # ── primitives ─────────────────────────────────────────────────────────────
    def partition_params(self) -> list[dict[str, Any]]:
        """Year band × price band over all makes — no make-id refdata dependency."""
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
        """Fetch one category page; retry Akamai blocks; return canonical ad URLs."""
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
        # Path-segment grammar: price + page node come before the c-node; the year
        # interval is glued onto c216 as `+autos.ez_i:{from},{to}`. Open top band
        # leaves the price max empty (`preis:{from}:`).
        pt = params.get("price_to")
        price_max = "" if pt is None else str(pt)
        return (
            f"{self._base_url}/s-autos"
            f"/preis:{params['price_from']}:{price_max}"
            f"/seite:{page_num}"
            f"/c216+autos.ez_i:{params['year_from']},{params['year_to']}"
        )

    def _extract(self, html: str) -> list[str]:
        """Canonical detail URLs from `/s-anzeige/...` hrefs, deduped within page."""
        seen: set[str] = set()
        out: list[str] = []
        for match in self._listing_re.finditer(html):
            canonical = f"{self._base_url}{match.group(0)}"
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
