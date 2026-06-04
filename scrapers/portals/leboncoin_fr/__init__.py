"""
leboncoin.fr — France's largest classifieds, cars vertical (~400k+ listings).

leboncoin fronts its whole stack with DataDome. The HTML storefront is hard
behind a behavioural challenge, but the SAME data the site renders comes from a
public JSON finder API that the web bundle calls directly. That route still sits
behind DataDome (residential egress + a warmed identity are required — Tier.T3),
yet it answers JSON rather than a hydrated React tree, so enumeration is a clean
POST loop instead of HTML scraping. This scraper only issues requests through the
duck-typed `session` (`.post(url, json=, headers=, timeout=)`), so it imports and
unit-tests without curl_cffi / a browser present, exactly like the AS24 family.

Gold nuggets [VERIFIED 2026-06-03 against live leboncoin — docs/research/leboncoin-fr.md]:

  Search URL  POST https://api.leboncoin.fr/finder/search   (JSON body, JSON reply)
  REQUIRED    header `api_key: ba0c2dad52b3ec` — the web app's PUBLIC client key
              (shipped in the JS bundle, not a user secret). Without it → 401/403.
              Plus Content-Type/Origin/Referer/Accept-Language (browser parity).
  Category    body filters.category.id = "2" = "Voitures" (cars).
  Year        body filters.ranges.regdate {min,max} — registration year, inclusive.
  Price       body filters.ranges.price   {min,max} — EUR (NOT cents), inclusive.
  Location    body filters.location.locations[] = [{locationType:"department",
              department_id:"75"}] — INSEE department code as string.
  Listings    JSON `ads[]`; per-ad `list_id` (int) + ready `url`
              (https://www.leboncoin.fr/ad/voitures/{list_id}). `total`/`max_pages`
              echoed for sizing.
  Pagination  body {limit, offset}; offset = (page-1)*limit. Page size 35. The
              finder HARD-CAPS at ~100 pages (~3,500 ads/query) regardless of the
              reported `total` → search-grid partitioning is mandatory.
  Block sig   DataDome: 403/401/429 and/or a body containing
              `captcha-delivery.com` (the challenge host) even on a 200.

Partition: department × year band × price band. This is the finest practical base
grid (≈101 departments × 11 years × 8 prices), so individual cells sit far below
the ~3,500 cap and the page ceiling is essentially never hit — full national
coverage without depending on a brand-id table (leboncoin's `u_car_brand` enum is
opaque). A residual capped cell is still subdivided into per-year × finer-price
sub-cells within the same department. Cross-cell dedup is the base `seen` set on
the canonical ad URLs.
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

# ── search grid (verified gold nuggets) ───────────────────────────────────────
_YEAR_BANDS: tuple[tuple[int, int], ...] = (
    (1990, 2000), (2000, 2005), (2005, 2008), (2008, 2011),
    (2011, 2014), (2014, 2016), (2016, 2018), (2018, 2020),
    (2020, 2022), (2022, 2024), (2024, 2026),
)
# Non-overlapping EUR price bands. The top band is open-ended (max=None).
_PRICE_BANDS: tuple[tuple[int, int | None], ...] = (
    (0, 5_000), (5_000, 10_000), (10_000, 15_000), (15_000, 20_000),
    (20_000, 30_000), (30_000, 50_000), (50_000, 100_000), (100_000, None),
)
# Concrete ceiling for the open-ended top band: subdivision + the verified
# {min,max} body both need a number (the finder rejects a null max).
_OPEN_PRICE_CEILING: int = 1_000_000
_PRICE_SUBSPLITS: int = 5

_CARS_CATEGORY_ID: str = "2"  # "Voitures"


def _french_departments() -> tuple[str, ...]:
    """
    The 101 INSEE department codes (public administrative reference data).

    Metropolitan 01–19, Corsica 2A/2B (replacing 20), 21–95, plus the five
    overseas departments 971–974/976. Codes are two-digit zero-padded strings
    (three digits overseas) — exactly the `department_id` the finder expects.
    """
    metro = [f"{n:02d}" for n in range(1, 20)]          # 01..19
    metro += ["2A", "2B"]                                # Corsica
    metro += [f"{n:02d}" for n in range(21, 96)]         # 21..95
    overseas = ["971", "972", "973", "974", "976"]       # DOM
    return tuple(metro + overseas)


_DEPARTMENTS: tuple[str, ...] = _french_departments()

# ── HTTP / WAF behaviour ──────────────────────────────────────────────────────
_SEARCH_URL: str = "https://api.leboncoin.fr/finder/search"
# Public web-client key from the leboncoin JS bundle — required, not a user secret.
_API_KEY: str = "ba0c2dad52b3ec"
_BLOCK_STATUSES: frozenset[int] = frozenset({401, 403, 429, 503})
# DataDome challenge marker — present in a challenge body even when served as 200.
_DATADOME_MARKERS: tuple[str, ...] = ("captcha-delivery.com", "datadome")


def _is_datadome_blocked(body: str) -> bool:
    """True when a body is actually a DataDome challenge rather than results."""
    lo = body.lower()
    return any(marker in lo for marker in _DATADOME_MARKERS)


class LeboncoinFRScraper(BasePortalScraper):
    """leboncoin.fr cars via the DataDome-gated finder JSON API (T3)."""

    DOMAIN = "leboncoin.fr"
    COUNTRY = "FR"

    HOST = "www.leboncoin.fr"

    # Finder page size 35; the API caps the reachable window at ~100 pages.
    PAGE_SIZE = 35
    MAX_PAGES = 100

    # DataDome is aggressive — back off hard on blocks.
    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 2.5
    REQUEST_TIMEOUT: int = 25

    YEAR_BANDS: tuple[tuple[int, int], ...] = _YEAR_BANDS
    PRICE_BANDS: tuple[tuple[int, int | None], ...] = _PRICE_BANDS
    DEPARTMENTS: tuple[str, ...] = _DEPARTMENTS

    # ── request shape ──────────────────────────────────────────────────────────
    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    @property
    def _headers(self) -> dict[str, str]:
        # api_key is mandatory; the rest mirror the web bundle for parity. The
        # User-Agent is set at session level by the coordinator (JA3 coherence).
        return {
            "api_key": _API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "Origin": self._base_url,
            "Referer": f"{self._base_url}/",
        }

    # ── primitives ─────────────────────────────────────────────────────────────
    def partition_params(self) -> list[dict[str, Any]]:
        """Department × year band × price band — finest practical national grid."""
        return [
            {
                "department": dep,
                "year_from": yf,
                "year_to": yt,
                "price_from": pf,
                "price_to": pt,
            }
            for dep, (yf, yt), (pf, pt) in product(
                self.DEPARTMENTS, self.YEAR_BANDS, self.PRICE_BANDS
            )
        ]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Explode a residual capped cell into per-year × finer-price sub-cells."""
        if params.get("_fine"):
            return []
        years = range(params["year_from"], params["year_to"] + 1)
        price_bands = self._split_price(params["price_from"], params["price_to"])
        return [
            {
                "department": params["department"],
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
        if pt is None:
            last_lo, _ = bands[-1]
            bands[-1] = (last_lo, None)
        return bands

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """POST one finder page; retry DataDome blocks; return canonical ad URLs."""
        offset = (page_num - 1) * self.PAGE_SIZE
        body = self._build_body(params, offset)
        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            response = await self._post(session, body)
            if response is None:
                await self._retry_backoff(attempt)
                continue

            status = response.status_code
            if status in _BLOCK_STATUSES:
                log.debug("HTTP %d (%d/%d) leboncoin finder", status, attempt, self.RETRY_ATTEMPTS)
                await self._retry_backoff(attempt, factor=2.0)
                continue
            if status != 200:
                log.debug("HTTP %d (no retry) leboncoin finder", status)
                return []

            text = response.text
            if _is_datadome_blocked(text):
                log.warning("datadome challenge (%d/%d) leboncoin", attempt, self.RETRY_ATTEMPTS)
                await self._retry_backoff(attempt, factor=2.0)
                continue

            return self._extract(text)

        log.warning("all %d attempts failed: leboncoin finder", self.RETRY_ATTEMPTS)
        return []

    # ── helpers ────────────────────────────────────────────────────────────────
    def _build_body(self, params: dict[str, Any], offset: int) -> dict[str, Any]:
        pt = params.get("price_to")
        price_max = _OPEN_PRICE_CEILING if pt is None else pt
        return {
            "filters": {
                "category": {"id": _CARS_CATEGORY_ID},
                "ranges": {
                    "regdate": {"min": params["year_from"], "max": params["year_to"]},
                    "price": {"min": params["price_from"], "max": price_max},
                },
                "location": {
                    "locations": [
                        {"locationType": "department", "department_id": params["department"]}
                    ]
                },
            },
            "limit": self.PAGE_SIZE,
            "offset": offset,
            "sort_by": "time",
            "sort_order": "desc",
        }

    def _extract(self, body: str) -> list[str]:
        """Pull canonical ad URLs from the JSON `ads[]`, deduped within the page."""
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            log.debug("non-JSON body from leboncoin finder")
            return []
        ads = payload.get("ads") if isinstance(payload, dict) else None
        if not isinstance(ads, list):
            return []
        seen: set[str] = set()
        out: list[str] = []
        for ad in ads:
            url = self._ad_url(ad)
            if url and url not in seen:
                seen.add(url)
                out.append(url)
        return out

    def _ad_url(self, ad: Any) -> str | None:
        """Prefer the ready `url`; fall back to building from `list_id`."""
        if not isinstance(ad, dict):
            return None
        url = ad.get("url")
        if isinstance(url, str) and url:
            return url if url.startswith("http") else f"{self._base_url}{url}"
        list_id = ad.get("list_id")
        if isinstance(list_id, (int, str)) and str(list_id).isdigit():
            return f"{self._base_url}/ad/voitures/{list_id}"
        return None

    async def _post(self, session: Any, body: dict[str, Any]) -> Any | None:
        try:
            return await session.post(
                _SEARCH_URL, json=body, headers=self._headers, timeout=self.REQUEST_TIMEOUT
            )
        except Exception as exc:  # transport-level
            log.debug("transport error leboncoin finder: %s", exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(self.RETRY_BACKOFF_BASE**attempt * factor + random.uniform(0, 0.25))
