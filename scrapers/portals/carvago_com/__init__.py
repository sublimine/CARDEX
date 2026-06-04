"""
carvago.com — Pan-European used car marketplace (~1.07M vehicles).

Next.js frontend, no WAF. Listings are client-rendered (CSR) — the SSR shell
contains counts and pagination but NO listing data. The scraper resolves the
Next.js buildId from ``__NEXT_DATA__``, then queries the ``_next/data/`` JSON
route with brand + pagination params. If the data route lacks listings (pure
CSR → separate XHR), the scraper falls back to probing ``/api/v1/search`` and
``/api/v2/search`` REST endpoints (discovered from Carvago dev blog).

Gold nuggets [VERIFIED 2026-06-04 — docs/research/phase6-portal-probe-results.md]:

  Search page  GET https://carvago.com/de/autos?make[]=MAKE_SKODA&page=1&limit=20
  EN alias     GET https://carvago.com/cars?make[]=MAKE_SKODA&page=1&limit=20
  Brand enum   MAKE_AUDI, MAKE_BMW, MAKE_SKODA, … (MAKE_{UPPER_SNAKE} pattern)
  Pagination   ?sort=publish-date&direction=desc&page=N&limit=20 (20/page)
  buildId      rotating, extract from __NEXT_DATA__ script tag in SSR HTML
  Data route   /_next/data/{buildId}/de/autos.json?make[]=MAKE_X&page=N&limit=20
  WAF          NONE — Carvago s.r.o. (Czech Republic)
  Inventory    1,076,500 pan-European listings
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BUILD_ID_RE = re.compile(r'"buildId"\s*:\s*"([^"]+)"')
_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 503})

# Top brands covering ~95% of European inventory. The values are exact enum
# strings from the carvago.com sitemap page [VERIFIED 2026-06-04].
_MAKES: tuple[str, ...] = (
    "MAKE_ABARTH", "MAKE_ALFA_ROMEO", "MAKE_AUDI", "MAKE_BMW", "MAKE_BYD",
    "MAKE_CHEVROLET", "MAKE_CHRYSLER", "MAKE_CITROEN", "MAKE_CUPRA",
    "MAKE_DACIA", "MAKE_DS_AUTOMOBILES", "MAKE_FIAT", "MAKE_FORD",
    "MAKE_GENESIS", "MAKE_HONDA", "MAKE_HYUNDAI", "MAKE_INFINITI",
    "MAKE_JAGUAR", "MAKE_JEEP", "MAKE_KGM", "MAKE_KIA", "MAKE_LAND_ROVER",
    "MAKE_LEXUS", "MAKE_MAZDA", "MAKE_MERCEDES_BENZ", "MAKE_MG",
    "MAKE_MINI", "MAKE_MITSUBISHI", "MAKE_NISSAN", "MAKE_OPEL",
    "MAKE_PEUGEOT", "MAKE_POLESTAR", "MAKE_PORSCHE", "MAKE_RENAULT",
    "MAKE_SEAT", "MAKE_SKODA", "MAKE_SMART", "MAKE_SSANGYONG",
    "MAKE_SUBARU", "MAKE_SUZUKI", "MAKE_TESLA", "MAKE_TOYOTA",
    "MAKE_VOLKSWAGEN", "MAKE_VOLVO",
)

# EUR price bands for subdivision of high-volume makes.
_PRICE_BANDS: tuple[tuple[int | None, int | None], ...] = (
    (None, 5_000), (5_000, 10_000), (10_000, 15_000), (15_000, 20_000),
    (20_000, 30_000), (30_000, 50_000), (50_000, None),
)


class CarvagoCOMScraper(BasePortalScraper):
    """carvago.com vehicles via Next.js data route (T1)."""

    DOMAIN = "carvago.com"
    COUNTRY = "EU"

    HOST = "carvago.com"
    LANG = "de"
    PAGE_SIZE = 20
    MAX_PAGES = 200  # 20 × 200 = 4,000 per segment

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 25

    MAKES: tuple[str, ...] = _MAKES
    PRICE_BANDS: tuple[tuple[int | None, int | None], ...] = _PRICE_BANDS

    # SSR page paths per language (EN path is simpler and avoids locale prefix)
    _SEARCH_PATHS: dict[str, str] = {"de": "de/autos", "en": "cars"}

    def __init__(self) -> None:
        super().__init__()
        self._build_id: str | None = None

    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    @property
    def _search_path(self) -> str:
        return self._SEARCH_PATHS.get(self.LANG, "cars")

    # ── primitives ────────────────────────────────────────────────────────────

    def partition_params(self) -> list[dict[str, Any]]:
        """One segment per brand make code."""
        return [{"make": m} for m in self.MAKES]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Split a capped make into price-band sub-segments."""
        if params.get("_fine"):
            return []
        return [
            {
                "make": params["make"],
                "price_min": pmin,
                "price_max": pmax,
                "_fine": True,
            }
            for pmin, pmax in self.PRICE_BANDS
        ]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch one page of search results via _next/data/ JSON route."""
        if self._build_id is None:
            self._build_id = await self._resolve_build_id(session)
            if self._build_id is None:
                return []

        url = self._build_data_url(params, page_num)

        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            response = await self._get(session, url)
            if response is None:
                await self._retry_backoff(attempt)
                continue

            status = response.status_code
            if status == 404:
                # buildId rotated (new deploy) — re-resolve
                log.info("404 on data route, re-resolving buildId")
                self._build_id = await self._resolve_build_id(session)
                if self._build_id is None:
                    return []
                url = self._build_data_url(params, page_num)
                continue

            if status in _BLOCK_STATUSES:
                log.debug(
                    "HTTP %d (%d/%d) %s",
                    status, attempt, self.RETRY_ATTEMPTS, url[:90],
                )
                await self._retry_backoff(attempt)
                continue

            if status != 200:
                log.debug("HTTP %d (no retry) %s", status, url[:90])
                return []

            return self._extract(response.text)

        log.warning("all %d attempts failed: %s", self.RETRY_ATTEMPTS, url[:90])
        return []

    # ── helpers ───────────────────────────────────────────────────────────────

    def _build_data_url(self, params: dict[str, Any], page_num: int) -> str:
        """Construct _next/data/ JSON URL with search params."""
        base = (
            f"{self._base_url}/_next/data/{self._build_id}"
            f"/{self._search_path}.json"
        )
        qp: list[str] = [f"make[]={params['make']}"]
        if params.get("price_min") is not None:
            qp.append(f"price-from={params['price_min']}")
        if params.get("price_max") is not None:
            qp.append(f"price-to={params['price_max']}")
        qp.append("sort=publish-date")
        qp.append("direction=desc")
        qp.append(f"page={page_num}")
        qp.append(f"limit={self.PAGE_SIZE}")
        return f"{base}?{'&'.join(qp)}"

    def _extract(self, body: str) -> list[str]:
        """Extract listing detail URLs from _next/data/ JSON response.

        Tries multiple common Next.js data shapes:
        1. pageProps.dehydratedState.queries[*].state.data.listings.edges[].node
        2. pageProps.searchResults.items[] or pageProps.cars[]
        3. pageProps.listings[] or pageProps.results[]

        Falls back to URL-pattern scanning on the raw JSON text as last resort.
        """
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            log.debug("non-JSON body from carvago.com data route")
            return []

        props = payload.get("pageProps")
        if not isinstance(props, dict):
            return []

        # --- Strategy 1: React Query / dehydrated state (tutti.ch pattern)
        urls = self._extract_dehydrated(props)
        if urls:
            return urls

        # --- Strategy 2: direct pageProps fields
        urls = self._extract_flat_props(props)
        if urls:
            return urls

        # --- Strategy 3: regex scan for car detail URLs in raw JSON
        urls = self._extract_url_scan(body)
        if urls:
            return urls

        log.debug("no listings extracted from carvago.com data route response")
        return []

    def _extract_dehydrated(self, props: dict[str, Any]) -> list[str]:
        """Extract from dehydratedState (React Query / TanStack Query pattern)."""
        try:
            dh = props["dehydratedState"]
            queries = dh["queries"]
        except (KeyError, TypeError):
            return []
        if not isinstance(queries, list):
            return []

        seen: set[str] = set()
        out: list[str] = []
        for query in queries:
            try:
                data = query["state"]["data"]
            except (KeyError, TypeError):
                continue
            # Walk common sub-structures for listing arrays
            for key in ("listings", "items", "cars", "results", "edges"):
                items = data.get(key) if isinstance(data, dict) else None
                if items is None and isinstance(data, dict):
                    # Try one level deeper (e.g. data.listings.edges)
                    for subkey, subval in data.items():
                        if isinstance(subval, dict) and key in subval:
                            items = subval[key]
                            break
                if isinstance(items, list):
                    self._collect_urls_from_items(items, seen, out)
        return out

    def _extract_flat_props(self, props: dict[str, Any]) -> list[str]:
        """Extract from flat pageProps.{key} array fields."""
        seen: set[str] = set()
        out: list[str] = []
        for key in ("searchResults", "cars", "listings", "results", "items",
                     "vehicles", "offers"):
            val = props.get(key)
            if isinstance(val, dict):
                # Could be {items: [...], total: N}
                for subkey in ("items", "data", "cars", "edges", "nodes"):
                    subval = val.get(subkey)
                    if isinstance(subval, list):
                        self._collect_urls_from_items(subval, seen, out)
            elif isinstance(val, list):
                self._collect_urls_from_items(val, seen, out)
        return out

    def _collect_urls_from_items(
        self, items: list[Any], seen: set[str], out: list[str]
    ) -> None:
        """Walk a list of item dicts, extract detail URLs, dedup."""
        for item in items:
            # Handle edge/node wrapper pattern
            if isinstance(item, dict) and "node" in item:
                item = item["node"]
            if not isinstance(item, dict):
                continue

            url = self._item_to_url(item)
            if url and url not in seen:
                seen.add(url)
                out.append(url)

    def _item_to_url(self, item: dict[str, Any]) -> str | None:
        """Build detail URL from a listing item dict."""
        # Try common ID/slug field names
        item_id = (
            item.get("id") or item.get("carId") or item.get("vehicleId")
            or item.get("offerId") or item.get("listingId")
        )
        slug = (
            item.get("slug") or item.get("seoSlug") or item.get("urlSlug")
        )
        # Try pre-built URL fields
        for key in ("url", "detailUrl", "link", "href", "canonicalUrl"):
            val = item.get(key)
            if isinstance(val, str) and val:
                if val.startswith("http"):
                    return val
                return f"{self._base_url}{val}"

        if item_id:
            if slug:
                return f"{self._base_url}/{self._search_path}/{slug}/{item_id}"
            return f"{self._base_url}/{self._search_path}/{item_id}"
        return None

    def _extract_url_scan(self, body: str) -> list[str]:
        """Last resort: regex scan for carvago detail URL patterns in raw JSON."""
        # Pattern: /cars/{make}/{model}/{slug-or-id} or /de/autos/{make}/{model}/{id}
        pattern = re.compile(
            r'(?:https://carvago\.com)?'
            r'/(?:cars|de/autos)/[a-z0-9-]+/[a-z0-9-]+/[a-z0-9-]+'
        )
        seen: set[str] = set()
        out: list[str] = []
        for match in pattern.finditer(body):
            path = match.group(0)
            url = path if path.startswith("http") else f"{self._base_url}{path}"
            if url not in seen:
                seen.add(url)
                out.append(url)
        return out

    async def _resolve_build_id(self, session: Any) -> str | None:
        """Extract Next.js buildId from __NEXT_DATA__ in SSR HTML."""
        url = f"{self._base_url}/{self._search_path}"
        response = await self._get(session, url)
        if response is None or response.status_code != 200:
            log.error("could not resolve buildId from carvago.com")
            return None
        match = _BUILD_ID_RE.search(response.text)
        if not match:
            log.error("buildId not found in carvago.com HTML")
            return None
        build_id = match.group(1)
        log.info("carvago.com buildId resolved: %s", build_id)
        return build_id

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
