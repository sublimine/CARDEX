"""
autohero.com — Pan-European used car marketplace by Auto1 Group (~19k vehicles).

Autohero is Auto1 Group's consumer-facing retail brand (B2C). The frontend is a
React SPA backed by a public GraphQL gateway. The searchAdV9AdsV2 query returns
full inventory per country — no authentication, no WAF, no DataDome. The endpoint
accepts POST requests with a JSON body containing a GraphQL query string. The
return type is RawJson so no GraphQL sub-selection is needed; the response is a
plain JSON blob with all car fields inlined.

Gold nuggets [VERIFIED 2026-06-04]:

  Endpoint    POST https://www.autohero.com/v1/retail-customer-gateway/graphql/
              Content-Type: application/json, no auth required.           [VERIFIED]
  Query       {searchAdV9AdsV2(search:{filter:{field:"countryCode",op:"eq",
              value:"XX"},sort:"most_popular",limit:100,offset:0,
              properties:{filterByEligibleDate:true,firstPublishedDays:-30,
              includeProspective:true}})}                                 [VERIFIED]
  Response    {"data":{"searchAdV9AdsV2":{"total":N,"data":[...]}}}      [VERIFIED]
  Car fields  id, stockNumber, manufacturer, model, subType, offerPrice,
              mileage, builtYear, countryCode, firstRegistrationYear,
              fuelType, gearType, kw, carUrlTitle, mainImageUrl          [VERIFIED]
  Detail URL  https://www.autohero.com/{locale}/buy/{carUrlTitle}-{id}/  [VERIFIED]
  Pagination  offset/limit based (max limit=100 per request)             [VERIFIED]
  Countries   DE(~7341), IT(~3445), FR(~3344), ES(~2474),
              AT(~925), PL(~650), NL(~628), SE(~481) = ~19k total        [VERIFIED]
  WAF         NONE — Auto1 Group SE (Berlin), plain Kubernetes ingress   [ASSUMED]
  Backend     Auto1 Group retail-customer-gateway (GraphQL gateway)      [VERIFIED]
  Locale map  DE->de, IT->it, FR->fr, ES->es, AT->at, PL->pl,
              NL->nl, SE->se (lowercase country code)                    [ASSUMED]
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

# ── API constants ─────────────────────────────────────────────────────────────
_GRAPHQL_URL: str = (
    "https://www.autohero.com/v1/retail-customer-gateway/graphql/"
)

# Country codes with approximate inventory sizes (verified 2026-06-04).
_COUNTRIES: tuple[str, ...] = ("DE", "IT", "FR", "ES", "AT", "PL", "NL", "SE")

# Locale prefix for detail URL construction (lowercase country code).
_LOCALE_MAP: dict[str, str] = {
    "DE": "de",
    "IT": "it",
    "FR": "fr",
    "ES": "es",
    "AT": "at",
    "PL": "pl",
    "NL": "nl",
    "SE": "se",
}

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 503})


class AutoheroCOMScraper(BasePortalScraper):
    """autohero.com vehicles via public GraphQL API (T0, no auth)."""

    DOMAIN = "autohero.com"
    COUNTRY = "DE"

    # The GraphQL endpoint accepts up to 100 items per request. The largest
    # country (DE) has ~7.3k items = 74 pages, well within MAX_PAGES.
    PAGE_SIZE = 100
    MAX_PAGES = 100

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    COUNTRIES: tuple[str, ...] = _COUNTRIES

    @property
    def _base_url(self) -> str:
        return "https://www.autohero.com"

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": self._base_url,
            "Referer": f"{self._base_url}/",
        }

    # ── primitives ────────────────────────────────────────────────────────────

    def partition_params(self) -> list[dict[str, Any]]:
        """One segment per country — each country's inventory is enumerated fully."""
        return [{"country_code": cc} for cc in self.COUNTRIES]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """No subdivision needed — largest country (DE ~7.3k) fits in 74 pages."""
        return []

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """POST one GraphQL page; retry transient errors; return detail URLs."""
        offset = (page_num - 1) * self.PAGE_SIZE
        body = self._build_query(params["country_code"], offset)

        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            response = await self._post(session, body)
            if response is None:
                await self._retry_backoff(attempt)
                continue

            status = response.status_code
            if status in _BLOCK_STATUSES:
                log.debug(
                    "HTTP %d (%d/%d) autohero graphql",
                    status,
                    attempt,
                    self.RETRY_ATTEMPTS,
                )
                await self._retry_backoff(attempt)
                continue
            if status != 200:
                log.debug("HTTP %d (no retry) autohero graphql", status)
                return []

            return self._extract(response.text, params["country_code"])

        log.warning(
            "all %d attempts failed: autohero graphql country=%s offset=%d",
            self.RETRY_ATTEMPTS,
            params["country_code"],
            offset,
        )
        return []

    # ── helpers ───────────────────────────────────────────────────────────────

    def _build_query(self, country_code: str, offset: int) -> dict[str, str]:
        """Construct the GraphQL POST payload for one page of one country."""
        query = (
            "{searchAdV9AdsV2(search:{"
            f'filter:{{field:"countryCode",op:"eq",value:"{country_code}"}},'
            f'sort:"most_popular",limit:{self.PAGE_SIZE},offset:{offset},'
            "properties:{"
            "filterByEligibleDate:true,"
            "firstPublishedDays:-30,"
            "includeProspective:true"
            "}})}"
        )
        return {"query": query}

    def _extract(self, body: str, country_code: str) -> list[str]:
        """Parse the nested GraphQL JSON response into detail URLs."""
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            log.debug("non-JSON body from autohero graphql")
            return []

        if not isinstance(payload, dict):
            return []

        # Navigate: data -> searchAdV9AdsV2 -> data (list of cars)
        gql_data = payload.get("data")
        if not isinstance(gql_data, dict):
            log.debug("missing 'data' key in autohero graphql response")
            return []

        search_result = gql_data.get("searchAdV9AdsV2")
        if not isinstance(search_result, dict):
            # RawJson return type — the value might itself be a JSON string.
            if isinstance(search_result, str):
                try:
                    search_result = json.loads(search_result)
                except (ValueError, TypeError):
                    log.debug("searchAdV9AdsV2 is unparseable string")
                    return []
            else:
                log.debug("missing 'searchAdV9AdsV2' in autohero graphql response")
                return []

        cars = search_result.get("data")
        if not isinstance(cars, list):
            return []

        locale = _LOCALE_MAP.get(country_code, country_code.lower())
        seen: set[str] = set()
        out: list[str] = []
        for car in cars:
            url = self._car_url(car, locale)
            if url and url not in seen:
                seen.add(url)
                out.append(url)
        return out

    def _car_url(self, car: Any, locale: str) -> str | None:
        """Build the detail URL from car fields: /{locale}/buy/{carUrlTitle}-{id}/."""
        if not isinstance(car, dict):
            return None
        car_id = car.get("id")
        slug = car.get("carUrlTitle")
        if not car_id or not isinstance(slug, str) or not slug:
            # Fall back to stockNumber if id is missing
            car_id = car_id or car.get("stockNumber")
            if not car_id:
                return None
            if not slug:
                # Build a minimal slug from manufacturer + model
                parts = []
                for field in ("manufacturer", "model"):
                    val = car.get(field)
                    if isinstance(val, str) and val:
                        parts.append(val.lower().replace(" ", "-"))
                slug = "-".join(parts) if parts else str(car_id)
        return f"{self._base_url}/{locale}/buy/{slug}-{car_id}/"

    async def _post(self, session: Any, body: dict[str, Any]) -> Any | None:
        """Send a POST request to the GraphQL endpoint."""
        try:
            return await session.post(
                _GRAPHQL_URL,
                json=body,
                headers=self._headers,
                timeout=self.REQUEST_TIMEOUT,
            )
        except Exception as exc:  # transport-level
            log.debug("transport error autohero graphql: %s", exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        """Jittered exponential backoff between retry attempts."""
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(
                self.RETRY_BACKOFF_BASE ** attempt * factor
                + random.uniform(0, 0.25)
            )
