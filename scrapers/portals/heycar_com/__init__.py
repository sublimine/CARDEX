"""
heycar.com -- France & UK used car marketplace by HeyGroup/Renault (~34k FR, ~75k UK).

HeyCar is a used car aggregator originally launched in Germany by Volkswagen Financial
Services, later acquired by Renault Group. The German market was permanently shut down
mid-2025; France and the UK remain active. The frontend is an SPA backed by a public
REST API hosted on group-mobility-trader.com -- no authentication, no WAF, no
DataDome. The API accepts simple GET requests with page/size pagination (zero-indexed)
and returns a standard Spring Data Page envelope with full car details inlined.

Gold nuggets [VERIFIED 2026-06-04]:

  FR endpoint  GET https://api.fr.prod.group-mobility-trader.com/i15/search
                   ?page={P}&size={S}&priceFrom={Pf}&priceTo={Pt}          [VERIFIED]
  UK endpoint  GET https://api.uk.prod.group-mobility-trader.com/i15/search
                   ?page={P}&size={S}&priceFrom={Pf}&priceTo={Pt}          [VERIFIED]
  DE endpoint  DEAD -- permanently shut down mid-2025                       [VERIFIED]
  Auth         NONE -- completely open, no tokens, no cookies required      [VERIFIED]
  Response     {"content":[...], "totalElements":34239, "totalPages":69,
                "pageable":{"pageNumber":0,"pageSize":500}}                 [VERIFIED]
  Pagination   page/size based, zero-indexed pages, max size=500 works     [VERIFIED]
  Car fields   id, heycarId, make (obj w/ label), model (obj w/ label),
               variant, prettyName, pricing.price, details.year,
               details.mileage, details.registration, spec.fuelType,
               spec.gearbox, spec.bhp, spec.color, dealer.name,
               dealer.city, location.postcode                              [VERIFIED]
  Detail FR    https://www.heycar.com/fr/vehicule/{id}                     [ASSUMED]
  Detail UK    https://www.heycar.co.uk/car/{id}                           [VERIFIED]
  Inventory    FR ~34k listings, UK ~75k listings                          [VERIFIED]
  WAF          NONE -- group-mobility-trader.com, plain API gateway        [VERIFIED]
  Backend      Spring Boot (Spring Data Page response envelope)            [ASSUMED]

Partition: price bands only. FR has ~34k listings; at PAGE_SIZE=500 that is
68 pages total -- easily fits within MAX_PAGES=100 per price band. Price bands
keep individual segments well below the result cap.

This scraper focuses on FR (CARDEX covers FR/DE/ES/NL/BE/CH). A HeycarUKScraper
could be added trivially by changing API_HOST, DETAIL_BASE, and COUNTRY.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

# -- price bands for partitioning inventory ------------------------------------
# Designed so no single band exceeds ~5k listings (100 pages * 500 = 50k cap).
# FR has ~34k total; these bands split that roughly evenly.
_PRICE_BANDS: tuple[tuple[int, int | None], ...] = (
    (0, 5_000),
    (5_000, 10_000),
    (10_000, 15_000),
    (15_000, 20_000),
    (20_000, 25_000),
    (25_000, 30_000),
    (30_000, 40_000),
    (40_000, 50_000),
    (50_000, 75_000),
    (75_000, 100_000),
    (100_000, None),
)

# Open-ended ceiling used when price_to is None (for subdivide_segment).
_OPEN_PRICE_CEILING: int = 500_000

# Number of sub-bands when a price band hits the result cap.
_PRICE_SUBSPLITS: int = 5

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 503})


class HeycarFRScraper(BasePortalScraper):
    """heycar.com FR vehicles via public REST API (T0, no auth)."""

    DOMAIN = "heycar.com"
    COUNTRY = "FR"

    # API host for the French market.
    API_HOST: str = "api.fr.prod.group-mobility-trader.com"

    # Detail page base URL for constructing deep links.
    DETAIL_BASE: str = "https://www.heycar.com/fr/vehicule"

    # The API accepts size=500 per request. FR ~34k / 500 = 68 pages max.
    PAGE_SIZE = 500
    MAX_PAGES = 100

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 25

    PRICE_BANDS: tuple[tuple[int, int | None], ...] = _PRICE_BANDS

    @property
    def _search_url(self) -> str:
        return f"https://{self.API_HOST}/i15/search"

    # -- primitives ------------------------------------------------------------

    def partition_params(self) -> list[dict[str, Any]]:
        """One segment per price band -- covers entire FR inventory."""
        return [
            {"price_from": pf, "price_to": pt}
            for pf, pt in self.PRICE_BANDS
        ]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Split a capped price band into finer sub-bands."""
        if params.get("_fine"):
            return []
        price_bands = self._split_price(params["price_from"], params["price_to"])
        return [
            {"price_from": pf, "price_to": pt, "_fine": True}
            for pf, pt in price_bands
        ]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch one page of one price-band segment; return detail URLs."""
        # Base class paginates 1-based; the API is 0-based.
        api_page = page_num - 1
        url = self._build_url(params, api_page)

        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            response = await self._get(session, url)
            if response is None:
                await self._retry_backoff(attempt)
                continue

            status = response.status_code
            if status in _BLOCK_STATUSES:
                log.debug(
                    "HTTP %d (%d/%d) %s",
                    status,
                    attempt,
                    self.RETRY_ATTEMPTS,
                    url[:120],
                )
                await self._retry_backoff(attempt)
                continue
            if status != 200:
                log.debug("HTTP %d (no retry) %s", status, url[:120])
                return []

            return self._extract(self._read_body(response))

        log.warning(
            "all %d attempts failed: %s",
            self.RETRY_ATTEMPTS,
            url[:120],
        )
        return []

    # -- helpers ---------------------------------------------------------------

    def _build_url(self, params: dict[str, Any], api_page: int) -> str:
        """Construct the search API URL with price range and pagination."""
        parts = [
            f"{self._search_url}?page={api_page}&size={self.PAGE_SIZE}",
        ]
        pf = params["price_from"]
        pt = params.get("price_to")
        if pf is not None:
            parts.append(f"&priceFrom={pf}")
        if pt is not None:
            parts.append(f"&priceTo={pt}")
        return "".join(parts)

    def _extract(self, body: str) -> list[str]:
        """Parse the Spring Data Page JSON envelope into detail URLs."""
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            log.debug("non-JSON body from heycar API")
            return []

        if not isinstance(payload, dict):
            return []

        content = payload.get("content")
        if not isinstance(content, list):
            log.debug("missing 'content' key in heycar API response")
            return []

        seen: set[str] = set()
        out: list[str] = []
        for car in content:
            url = self._car_url(car)
            if url and url not in seen:
                seen.add(url)
                out.append(url)
        return out

    def _car_url(self, car: Any) -> str | None:
        """Build detail URL from a car object's id field."""
        if not isinstance(car, dict):
            return None
        car_id = car.get("id")
        if not car_id:
            # Fall back to heycarId if id is absent.
            car_id = car.get("heycarId")
        if not car_id:
            return None
        return f"{self.DETAIL_BASE}/{car_id}"

    @staticmethod
    def _split_price(pf: int, pt: int | None) -> list[tuple[int, int | None]]:
        """Subdivide a price range into _PRICE_SUBSPLITS equal sub-bands."""
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
        # Preserve open-ended ceiling on the last band.
        if pt is None:
            last_lo, _ = bands[-1]
            bands[-1] = (last_lo, None)
        return bands

    async def _get(self, session: Any, url: str) -> Any | None:
        """Send a GET request with timeout; swallow transport errors."""
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:  # transport-level
            log.debug("transport error %s: %s", url[:120], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        """Jittered exponential backoff between retry attempts."""
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(
                self.RETRY_BACKOFF_BASE ** attempt * factor
                + random.uniform(0, 0.25)
            )
