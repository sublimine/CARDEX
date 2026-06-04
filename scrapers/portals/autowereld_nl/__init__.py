"""
autowereld.nl — Netherlands, largest free classified portal (~270,000 occasions).

PHP SSR HTML site with brand-based path segmentation and query-param pagination.
Both dealers and private sellers list for free.

Gold nuggets [research 2026-06-04]:

  Search base   GET https://www.autowereld.nl/
  Brand filter  /{brand-slug}/                                        [VERIFIED via Google index]
                e.g. /audi/, /fiat/, /volvo/, /mclaren/
  Pagination    ?pagina=N  (assumed 1-indexed, common NL pattern)      [ASSUMED]
  Detail URL    /{brand}/{model}-{slug}-{numeric-id}.html             [ASSUMED from PHP SSR pattern]
  Listing re    href="/{brand}/[^"]+\\.html"                          [ASSUMED]
  WAF           Unknown — empty response on web_fetch probe, possible
                geo-block or bot detection                             [NEEDS live probe]
  Inventory     ~270,000 occasions from dealers + private sellers     [VERIFIED via search]
  Tech stack    PHP SSR (classic, no SPA framework detected)          [ASSUMED from .html extensions]
  API           Deprecated (no new API keys issued)                   [VERIFIED via FAQ]
  Sort          relevance, newest, price asc/desc, brand A-Z          [VERIFIED via search]

Strategy: partition by brand slug (high-volume brands like VW, BMW, Audi).
Extract detail URLs from SSR HTML. 30 items/page assumed (common NL portal pattern).
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 500, 502, 503})

# Match detail hrefs: /{brand}/{model-slug-with-id}.html or similar
_LISTING_RE: re.Pattern[str] = re.compile(
    r'href="(/[a-z0-9-]+/[a-z0-9][a-z0-9_-]{6,}\.html[^"]*)"',
    re.IGNORECASE,
)

# Alternative: some PHP sites use /occasion/{id}/ or /auto/{slug}/
_LISTING_RE_ALT: re.Pattern[str] = re.compile(
    r'href="(/(?:occasion|auto|voertuig)/[a-z0-9][a-z0-9_-]{5,}[^"]*)"',
    re.IGNORECASE,
)

# Brand slugs from Google index — lowercase path segments used by the site.
_BRANDS: tuple[str, ...] = (
    "abarth", "alfa-romeo", "audi", "bmw", "citroen", "cupra", "dacia",
    "ds", "fiat", "ford", "honda", "hyundai", "jaguar", "jeep", "kia",
    "land-rover", "lexus", "mazda", "mclaren", "mercedes-benz", "mg",
    "mini", "mitsubishi", "nissan", "opel", "peugeot", "porsche",
    "renault", "seat", "skoda", "smart", "subaru", "suzuki", "tesla",
    "toyota", "volkswagen", "volvo",
)

# Price bands for subdivision of high-volume brand segments (EUR).
_PRICE_BANDS: tuple[tuple[int, int | None], ...] = (
    (0, 5_000), (5_000, 10_000), (10_000, 15_000), (15_000, 20_000),
    (20_000, 30_000), (30_000, 50_000), (50_000, 100_000), (100_000, None),
)


class AutowereldNLScraper(BasePortalScraper):
    """autowereld.nl occasions via SSR HTML brand pages (T1)."""

    DOMAIN = "autowereld.nl"
    COUNTRY = "NL"

    HOST = "www.autowereld.nl"

    PAGE_SIZE = 30
    MAX_PAGES = 300  # 30 × 300 = 9,000 per brand — triggers subdivide for VW/BMW

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    BRANDS: tuple[str, ...] = _BRANDS
    PRICE_BANDS: tuple[tuple[int, int | None], ...] = _PRICE_BANDS

    # ── primitives ────────────────────────────────────────────────────────────

    def partition_params(self) -> list[dict[str, Any]]:
        """One segment per brand — 37 brands covering the full ~270k inventory."""
        return [{"brand": b} for b in self.BRANDS]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Split a capped brand segment into price-band sub-segments."""
        if params.get("_fine"):
            return []
        return [
            {
                "brand": params["brand"],
                "prijs_van": pf,
                "prijs_tot": pt,
                "_fine": True,
            }
            for pf, pt in self.PRICE_BANDS
        ]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
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

    # ── helpers ───────────────────────────────────────────────────────────────

    def _build_url(self, params: dict[str, Any], page_num: int) -> str:
        brand = params["brand"]
        base = f"https://{self.HOST}/{brand}/"

        qp: list[str] = []
        if "prijs_van" in params:
            qp.append(f"prijs_van={params['prijs_van']}")
        if params.get("prijs_tot") is not None:
            qp.append(f"prijs_tot={params['prijs_tot']}")
        if page_num > 1:
            qp.append(f"pagina={page_num}")

        if qp:
            return f"{base}?{'&'.join(qp)}"
        return base

    def _extract(self, html: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for pattern in (_LISTING_RE, _LISTING_RE_ALT):
            for match in pattern.finditer(html):
                path = match.group(1)
                url = f"https://{self.HOST}{path}"
                if url not in seen:
                    seen.add(url)
                    out.append(url)
        return out

    async def _get(self, session: Any, url: str) -> Any | None:
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:
            log.debug("transport error %s: %s", url[:90], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(
                self.RETRY_BACKOFF_BASE ** attempt * factor + random.uniform(0, 0.25)
            )
