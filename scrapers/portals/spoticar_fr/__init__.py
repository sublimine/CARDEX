"""
spoticar.fr — France, Stellantis reconditioning network (~80,000 vehicles).

Spoticar is the official used vehicle brand of Stellantis (Peugeot, Citroën,
DS, Opel, Fiat, Jeep, Alfa Romeo). With 1,200+ sales points and ~80k vehicles,
it is one of the largest used car inventories in France. The site runs a modern
SSR frontend behind Cloudflare CDN.

Gold nuggets [VERIFIED 2026-06-04 — web_fetch returned large SSR HTML]:

  Search URL  GET https://www.spoticar.fr/voitures-occasion
                  ?page={N}&prix-min={Pf}&prix-max={Pt}
                  &annee-min={Yf}&annee-max={Yt}
  Detail URL  /voitures-occasion/{brand}/{model}/{slug}
              Slug contains year, mileage, and a unique identifier.
  Listings    SSR HTML, ~24 ads per page.
  Pagination  ?page=N, 1-based. Large inventory → year×price grid mandatory.
  Filters     prix-min/prix-max (EUR), annee-min/annee-max, carburant, etc.
  Block sig   Cloudflare CDN for images (cdn-cgi/image). SSR HTML served
              without JS challenge at T1 rate. DataDome NOT observed.
  Inventory   ~80,000 vehicles (massive — Stellantis network).

Partition: year band × price band — mandatory for 80k inventory.
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


class SpoticarFRScraper(BasePortalScraper):
    """spoticar.fr used vehicles via SSR HTML search (T1)."""

    DOMAIN = "spoticar.fr"
    COUNTRY = "FR"

    HOST = "www.spoticar.fr"

    PAGE_SIZE = 24
    MAX_PAGES = 200

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
        return f"https://{self.HOST}/voitures-occasion"

    @cached_property
    def _listing_re(self) -> re.Pattern[str]:
        """Match /voitures-occasion/{brand}/{model}/{slug} detail hrefs."""
        return re.compile(
            r'href="(/voitures-occasion/([a-z0-9\-]+)/([a-z0-9\-]+)/([a-z0-9\-]+))"',
            re.IGNORECASE,
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

            return self._extract(response.text)

        log.warning("all %d attempts failed: %s", self.RETRY_ATTEMPTS, url[:90])
        return []

    # ── helpers ────────────────────────────────────────────────────────────────
    def _build_url(self, params: dict[str, Any], page_num: int) -> str:
        parts = []
        if page_num > 1:
            parts.append(f"page={page_num}")
        parts.append(f"prix-min={params['price_from']}")
        pt = params.get("price_to")
        if pt is not None:
            parts.append(f"prix-max={pt}")
        parts.append(f"annee-min={params['year_from']}")
        parts.append(f"annee-max={params['year_to']}")
        return f"{self._search_base}?{'&'.join(parts)}"

    def _extract(self, html: str) -> list[str]:
        """Canonical detail URLs from href attributes, within-page deduped."""
        seen: set[str] = set()
        out: list[str] = []
        for match in self._listing_re.finditer(html):
            path = match.group(1)
            # Skip category-level pages (e.g. /voitures-occasion/peugeot which is 2 segments).
            brand, model, slug = match.group(2), match.group(3), match.group(4)
            canonical = f"{self._base_url}/voitures-occasion/{brand}/{model}/{slug}"
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
