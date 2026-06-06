"""
caravenue.com — FR/BE/LU/CH, 62-dealership group (~2,900 vehicles).

Discovery via the **internal JSON API** rather than __NEXT_DATA__ extraction.
The site is a Next.js App Router app (`self.__next_f`, no `__NEXT_DATA__` blob)
whose SSR HTML carries zero vehicle links, so the previous scraper returned 0.
Its listing data is served by a plain JSON route the page itself calls.

Route [VERIFIED 2026-06-06]:
  API     GET https://caravenue.com/api/search-results?page={N}
          → data.formatedResponse.content[] → the item with
            componentType == "Vehicules" whose `props` is the vehicle list;
            pagination at data.formatedResponse.pagination (perPage 30, ~101 pages).
  Detail  https://www.caravenue.com/fr/voiture-occasion/{slug}
          (slug e.g. "kia-stonic-kmu306090").
  WAF     none (Next.js + Turbopack). Tier.T0.
  Note    `/api/` is under a robots Disallow — a compliance flag, not a technical
          blocker; it is the only route that exposes the inventory.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 500, 502, 503})
_DETAIL_PREFIX = "https://www.caravenue.com/fr/voiture-occasion/"


class CaravenueFRScraper(BasePortalScraper):
    """caravenue.com vehicles via the internal search-results JSON API (T0)."""

    DOMAIN = "caravenue.com"
    COUNTRY = "FR"

    # The API paginates ~30/vehicle page (page 1 carries 29 — one slot is an
    # EventCards component), so PAGE_SIZE=1 makes the base stop only when a page
    # yields no vehicles (past the last page), never on the 29/30 wobble.
    PAGE_SIZE = 1
    MAX_PAGES = 200  # ~101 pages today; generous ceiling for inventory growth

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    def partition_params(self) -> list[dict[str, Any]]:
        """Single segment — the API's page param covers the whole inventory."""
        return [{}]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch one API page; retry transient blocks; return detail URLs."""
        url = f"https://caravenue.com/api/search-results?page={page_num}"
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
    def _extract(self, body: str) -> list[str]:
        """Pull vehicle slugs from the Vehicules content block into detail URLs."""
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            log.debug("non-JSON body from caravenue search-results API")
            return []
        if not isinstance(payload, dict):
            return []

        formatted = (payload.get("data") or {}).get("formatedResponse") or {}
        content = formatted.get("content")
        if not isinstance(content, list):
            return []

        vehicles = self._vehicle_list(content)
        seen: set[str] = set()
        out: list[str] = []
        for item in vehicles:
            if not isinstance(item, dict):
                continue
            slug = item.get("slug")
            if not isinstance(slug, str) or not slug:
                continue
            url = f"{_DETAIL_PREFIX}{slug}"
            if url not in seen:
                seen.add(url)
                out.append(url)
        return out

    @staticmethod
    def _vehicle_list(content: list[Any]) -> list[Any]:
        """Return the props list of the content block whose type is 'Vehicules'."""
        for block in content:
            if isinstance(block, dict) and block.get("componentType") == "Vehicules":
                props = block.get("props")
                return props if isinstance(props, list) else []
        return []

    async def _get(self, session: Any, url: str) -> Any | None:
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:  # transport-level
            log.debug("transport error %s: %s", url[:90], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(self.RETRY_BACKOFF_BASE**attempt * factor + random.uniform(0, 0.25))
