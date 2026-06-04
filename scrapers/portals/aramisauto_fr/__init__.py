"""
aramisauto.com — France, reconditioning dealer (Aramis Group) (~3,000 used cars).

Aramis Group is the European leader in online used car sales. aramisauto.com is
the French flagship, running a Next.js app behind Cloudflare CDN. The search
surface is at /achat/occasion with SSR HTML listing cards. A Sentry trace header
confirms server-side rendering (not a pure SPA).

Gold nuggets [VERIFIED 2026-06-04 — web_fetch of homepage + search URLs]:

  Search URL  GET https://www.aramisauto.com/achat/occasion
                  ?page={N}&priceMin={Pf}&priceMax={Pt}
  Alt search  GET https://www.aramisauto.com/achat/?page={N}   (all vehicles)
  Detail URL  /achat/{brand}/{model}/{slug}/   (e.g. /achat/peugeot/208/offres/)
              Individual vehicles at /achat/{brand}/{model}/details/{ID}
  Listings    SSR HTML with structured links. ~24 cards per page.
  Pagination  ?page=N, 1-based. No pagination cap observed in the ~3k inventory.
  Filters     priceMin/priceMax (EUR), fuelTypes[], gearboxes[], etc.
  Block sig   Cloudflare CDN (cdn-cgi/image), Sentry baggage. No DataDome.
              Cloudflare JS challenge possible under heavy load → T1 with
              potential T2 escalation.
  Inventory   ~3,000 reconditional vehicles across France.

Partition: single segment with pagination (3k inventory, ~125 pages of 24).
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from functools import cached_property
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 500, 502, 503})


class AramisAutoFRScraper(BasePortalScraper):
    """aramisauto.com used cars via Next.js SSR HTML endpoint (T1)."""

    DOMAIN = "aramisauto.com"
    COUNTRY = "FR"

    HOST = "www.aramisauto.com"

    PAGE_SIZE = 24
    MAX_PAGES = 150  # generous ceiling for ~3k inventory

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    @property
    def _search_base(self) -> str:
        return f"https://{self.HOST}/achat/occasion"

    @cached_property
    def _listing_re(self) -> re.Pattern[str]:
        """Match /achat/{brand}/{model}/{slug}/ detail hrefs."""
        return re.compile(
            r"/achat/([a-z0-9\-]+)/([a-z0-9\-]+)/([a-z0-9\-]+)/"
        )

    # ── primitives ─────────────────────────────────────────────────────────────
    def partition_params(self) -> list[dict[str, Any]]:
        # ~3k inventory; single segment with pagination is sufficient.
        return [{}]

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch one listing page; retry transient blocks; return canonical ad URLs."""
        url = self._build_url(page_num)
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
    def _build_url(self, page_num: int) -> str:
        if page_num == 1:
            return self._search_base
        return f"{self._search_base}?page={page_num}"

    def _extract(self, html: str) -> list[str]:
        """Canonical detail URLs from /achat/{brand}/{model}/{slug}/ hrefs, deduped."""
        seen: set[str] = set()
        out: list[str] = []
        # Exclude category-level /offres/ pages — we want individual vehicle pages only.
        for match in self._listing_re.finditer(html):
            brand, model, slug = match.group(1), match.group(2), match.group(3)
            # Skip navigation links (offres, category pages).
            if slug == "offres":
                continue
            canonical = f"{self._base_url}/achat/{brand}/{model}/{slug}/"
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
