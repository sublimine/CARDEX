"""
motor.es (segunda-mano coches) — Spain classified (cars, ~50,333 listings).

motor.es is fronted by Cloudflare but only enforces JA3 / TLS — no JS challenge
appears for `curl_cffi` `impersonate="chrome"` (every research surface returned
200 first-shot). Tier.T1. The coordinator injects a curl_cffi session; this
scraper only issues GETs through the duck-typed `session` and parses the HTML
response, so it imports and unit-tests without curl_cffi present.

Gold nuggets [VERIFIED 2026-06-03 against the live site — docs/research/motor-es.md]:

  Search URL  GET https://www.motor.es/segunda-mano/coches/?pagina={N}
                  &precio_min={Pf}&precio_max={Pt}&year_min={Yf}&year_max={Yt}
  Surface     The cars-only filter view `/segunda-mano/coches/`. The generic
              `/segunda-mano/` SRP mixes motorcycles (data-goto decoded to
              `/motos/segunda-mano/anuncio/<UUID>/`).
  Filters     pagina (1-based), precio_min/max (EUR), year_min/max (year),
              km_min/max (km). The brief's pmin/pmax/anyomin/anyomax were
              probed and returned the unfiltered set — REJECTED.
  Listings    Server-rendered HTML; 22 unique ad cards per page (verified across
              pagina=1..50). Each card carries `<span data-goto="<BASE64>" …>`
              where data-goto base64-decodes to the absolute detail URL.
  Detail URL  https://www.motor.es/segunda-mano/anuncio/<NUMERIC_ID>/
              (motorcycle entries decode to /motos/.../UUID/ and are filtered out.)
  Pagination  HARD CAP at pagina=50 (~1,100 ads/query). pagina=51 → 404.
              vs ~50k total inventory → year × price partitioning is mandatory.
  Block sig   Cloudflare TLS gating only; no challenge body observed.

Partition: year band × price band over all makes — no make-slug refdata
dependency. A capped cell is subdivided into per-year × finer-price sub-cells.
Cross-cell dedup is the base `seen` set on canonical /segunda-mano/anuncio/<id>/ URLs.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
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

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 500, 502, 503})


class MotorESScraper(BasePortalScraper):
    """motor.es cars via the segunda-mano/coches SSR endpoint (T1)."""

    DOMAIN = "motor.es"
    COUNTRY = "ES"

    HOST = "www.motor.es"

    # 22 unique ad cards per page; pager caps at 50 (VERIFIED — pagina=51 → 404).
    PAGE_SIZE = 22
    MAX_PAGES = 50

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
        return f"https://{self.HOST}/segunda-mano/coches/"

    @cached_property
    def _data_goto_re(self) -> re.Pattern[str]:
        """Match `data-goto="<BASE64>"` on every card anchor."""
        return re.compile(r'data-goto="([^"]+)"')

    @cached_property
    def _car_detail_re(self) -> re.Pattern[str]:
        """Match the cars-only canonical detail path inside a decoded URL."""
        return re.compile(r"^https?://www\.motor\.es/segunda-mano/anuncio/(\d+)/$")

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
        # Spanish underscore-name vocabulary (VERIFIED via live counter overlap).
        parts = [
            f"pagina={page_num}",
            f"precio_min={params['price_from']}",
        ]
        pt = params.get("price_to")
        if pt is not None:
            parts.append(f"precio_max={pt}")
        parts.extend([
            f"year_min={params['year_from']}",
            f"year_max={params['year_to']}",
        ])
        return f"{self._search_base}?{'&'.join(parts)}"

    def _extract(self, html: str) -> list[str]:
        """Decode every data-goto, keep cars-only canonical URLs, dedup within page."""
        seen: set[str] = set()
        out: list[str] = []
        for match in self._data_goto_re.finditer(html):
            decoded = self._b64_decode(match.group(1))
            if decoded is None:
                continue
            m = self._car_detail_re.match(decoded)
            if m is None:
                continue
            canonical = f"{self._base_url}/segunda-mano/anuncio/{m.group(1)}/"
            if canonical not in seen:
                seen.add(canonical)
                out.append(canonical)
        return out

    @staticmethod
    def _b64_decode(value: str) -> str | None:
        """Tolerant base64→str decode. Returns None on any error."""
        try:
            return base64.b64decode(value, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            return None

    async def _get(self, session: Any, url: str) -> Any | None:
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:  # transport-level
            log.debug("transport error %s: %s", url[:90], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(self.RETRY_BACKOFF_BASE**attempt * factor + random.uniform(0, 0.25))
