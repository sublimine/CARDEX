"""
vroom.be -- Belgian mobility platform (~40k selected cars, 8M+ visits).

Leading Belgian automotive portal with news, reviews, and classifieds sections.
Joint venture of Groupe Rossel and Roularta Media Group. Offers both new and
used car listings from dealers and private sellers.

Gold nuggets [research 2026-06-04]:

  Search URL    GET https://www.vroom.be/fr/voitures-occasion             [VERIFIED]
  NL variant    GET https://www.vroom.be/nl/tweedehands-auto              [ASSUMED]
  Detail URL    /fr/voitures-occasion/{brand}/{model}/{slug}-{id}         [ASSUMED]
  Pagination    ?page=N (1-indexed)                                       [ASSUMED]
  WAF           Unknown — Groupe Rossel media property                    [UNVERIFIED]
  Inventory     ~40,000 selected cars                                     [VERIFIED]
  Categories    Car, Classic, Commercial Vehicle, Motorcycle              [VERIFIED]
  Languages     FR, NL                                                    [VERIFIED]

Strategy: brand-level partitioning in FR locale. Listing URLs regex-extracted
from SSR HTML.
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

# Match vehicle detail URLs: /fr/voitures-occasion/{brand}/{model}/{slug}
# Model slugs can be short (a3, x1), so minimum 1 char after first char.
_LISTING_RE: re.Pattern[str] = re.compile(
    r'href="(/(?:fr|nl)/(?:voitures-occasion|tweedehands-auto)/[a-z0-9][a-z0-9_-]+/[a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9_-]{5,}[^"]*)"',
    re.IGNORECASE,
)

# Alternative: ID-based detail link
_DETAIL_RE: re.Pattern[str] = re.compile(
    r'href="(/(?:fr|nl)/(?:annonce|advertentie|voiture|auto)/[a-z0-9-]+-\d{4,}[^"]*)"',
    re.IGNORECASE,
)

_BRANDS: tuple[str, ...] = (
    "abarth", "alfa-romeo", "audi", "bmw", "citroen", "cupra", "dacia",
    "fiat", "ford", "honda", "hyundai", "jaguar", "jeep", "kia",
    "land-rover", "lexus", "mazda", "mercedes-benz", "mg", "mini",
    "mitsubishi", "nissan", "opel", "peugeot", "porsche", "renault",
    "seat", "skoda", "smart", "suzuki", "tesla", "toyota",
    "volkswagen", "volvo",
)


class VroomBEScraper(BasePortalScraper):
    """vroom.be vehicles via SSR HTML (T1)."""

    DOMAIN = "vroom.be"
    COUNTRY = "BE"

    HOST = "www.vroom.be"
    LANG = "fr"

    PAGE_SIZE = 20
    MAX_PAGES = 50

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    BRANDS: tuple[str, ...] = _BRANDS

    def partition_params(self) -> list[dict[str, Any]]:
        return [{"brand": b} for b in self.BRANDS]

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

    def _build_url(self, params: dict[str, Any], page_num: int) -> str:
        brand = params.get("brand", "")
        section = "voitures-occasion" if self.LANG == "fr" else "tweedehands-auto"
        base = f"https://{self.HOST}/{self.LANG}/{section}/{brand}"
        if page_num > 1:
            return f"{base}?page={page_num}"
        return base

    def _extract(self, html: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for pattern in (_LISTING_RE, _DETAIL_RE):
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
