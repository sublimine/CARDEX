"""
coches.net — Spain's largest car marketplace (Adevinta ES, ~249,700 listings).

coches.net is an Adevinta Spain property fronted by AWS CloudFront — NO Cloudflare,
no Akamai, no DataDome on the listing path. Two surfaces expose the same data:

  1. The internal JSON search API `POST https://ms-mt--api-web.spain.advgo.net/search`.
     This is the ONLY partition-capable surface (server-side year/price/make filters),
     so it is the surface we enumerate. The catch: its CloudFront origin is geo/network
     restricted to Spain/Adevinta egress — it answers 502 ("origin domain name could
     not be resolved") from anywhere else. That is an ORIGIN-RESOLUTION block, NOT a
     bot/TLS block (identical under full Chrome impersonation and from a real browser).
     The coordinator routes ES through Spanish egress, exactly as it routes FR/DataDome
     portals through residential FR egress; this scraper only issues requests through
     the duck-typed `session`, so it imports and unit-tests without curl_cffi present.

  2. The server-rendered HTML `GET /segunda-mano/?pagina=N`, reachable from any region,
     which inlines the SAME `items[]` payload. It is the durable fallback, but the SSR
     URL exposes no VERIFIED filter param names, so it cannot grid-partition the 249k
     inventory (it caps at the deep-pagination wall, ~3k). We therefore enumerate via
     the partition-capable JSON API and treat egress as the coordinator's concern.

Tier.T1 (curl_cffi chrome; trends T2 if Adevinta enforces session validation at scale).

Gold nuggets [docs/research/coches-net.md, research 2026-06-03]:

  API URL     POST https://ms-mt--api-web.spain.advgo.net/search   [VERIFIED host,
              502 from non-ES egress; DNS → AWS CloudFront 143.204.55.x]
  Category    filters.categoryType = "Car".                         [VERIFIED vocab]
  Year        filters.year  = {from, to}  — registration year.      [VERIFIED vocab]
  Price       filters.price = {from, to}  — EUR (NOT cents).         [VERIFIED vocab]
  Offer       filters.offerTypeIds = [0]  (Ocasión / used).          [VERIFIED vocab]
  Sort        sort = {term:"relevance", order:"desc"}.               [VERIFIED vocab]
  Page        pagination = {page (1-based), size 30}.                [VERIFIED vocab]
  Listings    JSON `items[]`; per-ad `url` (relative `.aspx`) + `id` (numeric).
              Detail URL = "https://www.coches.net" + url.           [VERIFIED via SSR]
  Pagination  ~100 pages × size 30 ≈ 3,000 ads/query against ~249,700 total →
              search-grid partitioning is mandatory.                 [ASSUMED cap]
  Block sig   CloudFront 5xx / non-200; no challenge body on this path.

  [ASSUMED — reconstructed from the SSR hydration state + research brief, to be
   upgraded to VERIFIED once exercised to a 200 from Spanish egress]:
     • exact request-body nesting (`pagination`/`sort`/`filters` envelope)
     • header enforcement of `x-adevinta-channel` / `x-schibsted-tenant`
     • the ~100-page deep-pagination ceiling

Partition: year band × price band over all makes — no make-id refdata dependency
(coches.net exposes makes as opaque `makeId` ints). A capped cell is subdivided into
per-year × finer-price sub-cells. Cross-cell dedup is the base `seen` set on the
canonical `.aspx` ad URLs.
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

# ── search grid (verified filter vocabulary) ──────────────────────────────────
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
# Concrete ceiling for the open-ended top band: subdivision + the {from,to} body
# both need a number rather than null.
_OPEN_PRICE_CEILING: int = 1_000_000
_PRICE_SUBSPLITS: int = 5

_CARS_CATEGORY: str = "Car"     # filters.categoryType
_USED_OFFER_TYPE: int = 0       # filters.offerTypeIds = [0] → "Ocasión"

# ── HTTP / WAF behaviour ──────────────────────────────────────────────────────
_SEARCH_URL: str = "https://ms-mt--api-web.spain.advgo.net/search"
# CloudFront origin block (502 from non-ES egress) plus generic transient statuses.
_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 500, 502, 503})


class CochesNetScraper(BasePortalScraper):
    """coches.net cars via the Adevinta Spain JSON search API (T1, ES egress)."""

    DOMAIN = "coches.net"
    COUNTRY = "ES"

    HOST = "www.coches.net"

    # pagination.page / size. Site default size 30; Adevinta deep-paging caps ~100.
    PAGE_SIZE = 30
    MAX_PAGES = 100

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 2.0
    REQUEST_TIMEOUT: int = 25

    YEAR_BANDS: tuple[tuple[int, int], ...] = _YEAR_BANDS
    PRICE_BANDS: tuple[tuple[int, int | None], ...] = _PRICE_BANDS

    # ── request shape ──────────────────────────────────────────────────────────
    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    @property
    def _headers(self) -> dict[str, str]:
        # Adevinta `/api-web` gateway convention [ASSUMED enforced]; Origin/Referer
        # mirror the web bundle. The User-Agent is set at session level by the
        # coordinator (JA3 coherence).
        return {
            "x-adevinta-channel": "web-desktop",
            "x-schibsted-tenant": "coches",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            "Origin": self._base_url,
            "Referer": f"{self._base_url}/",
        }

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
        """POST one search page; retry CloudFront/transient blocks; return ad URLs."""
        body = self._build_body(params, page_num)
        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            response = await self._post(session, body)
            if response is None:
                await self._retry_backoff(attempt)
                continue

            status = response.status_code
            if status in _BLOCK_STATUSES:
                log.debug("HTTP %d (%d/%d) coches search", status, attempt, self.RETRY_ATTEMPTS)
                await self._retry_backoff(attempt, factor=2.0)
                continue
            if status != 200:
                log.debug("HTTP %d (no retry) coches search", status)
                return []

            return self._extract(response.text)

        log.warning("all %d attempts failed: coches search", self.RETRY_ATTEMPTS)
        return []

    # ── helpers ────────────────────────────────────────────────────────────────
    def _build_body(self, params: dict[str, Any], page_num: int) -> dict[str, Any]:
        # [ASSUMED] body envelope reconstructed from the SSR hydration state; the
        # filter field names (categoryType/year/price/offerTypeIds) are VERIFIED.
        pt = params.get("price_to")
        price_max = _OPEN_PRICE_CEILING if pt is None else pt
        return {
            "pagination": {"page": page_num, "size": self.PAGE_SIZE},
            "sort": {"order": "desc", "term": "relevance"},
            "filters": {
                "categoryType": _CARS_CATEGORY,
                "offerTypeIds": [_USED_OFFER_TYPE],
                "isFinanced": False,
                "year": {"from": params["year_from"], "to": params["year_to"]},
                "price": {"from": params["price_from"], "to": price_max},
            },
        }

    def _extract(self, body: str) -> list[str]:
        """Pull canonical `.aspx` detail URLs from JSON `items[]`, deduped per page."""
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            log.debug("non-JSON body from coches search")
            return []
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return []
        seen: set[str] = set()
        out: list[str] = []
        for ad in items:
            url = self._ad_url(ad)
            if url and url not in seen:
                seen.add(url)
                out.append(url)
        return out

    def _ad_url(self, ad: Any) -> str | None:
        """Detail URL from the verbatim relative `url` (`.aspx`), host-prefixed."""
        if not isinstance(ad, dict):
            return None
        url = ad.get("url")
        if not isinstance(url, str) or not url:
            return None
        return url if url.startswith("http") else f"{self._base_url}{url}"

    async def _post(self, session: Any, body: dict[str, Any]) -> Any | None:
        try:
            return await session.post(
                _SEARCH_URL, json=body, headers=self._headers, timeout=self.REQUEST_TIMEOUT
            )
        except Exception as exc:  # transport-level
            log.debug("transport error coches search: %s", exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(self.RETRY_BACKOFF_BASE**attempt * factor + random.uniform(0, 0.25))
