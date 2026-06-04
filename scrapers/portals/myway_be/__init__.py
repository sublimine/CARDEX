"""
myway.be — Belgium, D'Ieteren Automotive certified used car platform.

Multi-language SSR site (NL/FR) with 30+ brands. All vehicles pass 100+
inspection points and carry minimum 1-year legal guarantee. D'Ieteren is
Belgium's largest automotive distributor (Volkswagen Group, Porsche, etc.).

Gold nuggets [research 2026-06-04]:

  Search base   GET https://www.myway.be/fr/offre-voitures-occasion/    [VERIFIED via Google]
                    https://www.myway.be/nl/aanbod-tweedehands-wagens/  [ASSUMED NL mirror]
  Fuel filter   /fr/offre-voitures-occasion/-{fuel}/                   [VERIFIED]
                e.g. -cng/, -electrique/
  Brand filter  ?model[{brand}]={model} (query param)                   [VERIFIED via Google index]
  Sort          ?trier-par=-publicationDate (newest first)              [VERIFIED via Google index]
  Detail URL    /fr/offre-voitures-occasion/{brand}-{model}-{slug}/     [ASSUMED]
  Pagination    ?page=N  (1-indexed, assumed)                           [ASSUMED]
  WAF           Unknown — assumed T1 (D'Ieteren corporate site)         [NEEDS live probe]
  Inventory     Unknown (30+ brands, certified pre-owned only)          [VERIFIED]
  Tech stack    SSR HTML, likely Symfony/Laravel (PHP)                   [ASSUMED]

Strategy: single-segment global paginator over the occasion listing page.
Sort by -publicationDate for freshest results. Extract vehicle detail hrefs.
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

# Match detail hrefs under the occasion listing paths.
_LISTING_RE: re.Pattern[str] = re.compile(
    r'href="(/(?:fr|nl)/(?:offre-voitures-occasion|aanbod-tweedehands-wagens)/[a-z0-9][a-z0-9_/-]{8,}[^"]*)"',
    re.IGNORECASE,
)

# Alternative: /fr/vehicule/{slug} or /nl/voertuig/{slug}
_LISTING_RE_ALT: re.Pattern[str] = re.compile(
    r'href="(/(?:fr|nl)/(?:vehicule|voertuig|vehicle|detail)/[a-z0-9][a-z0-9_/-]{5,}[^"]*)"',
    re.IGNORECASE,
)


class MyWayBEScraper(BasePortalScraper):
    """myway.be D'Ieteren certified used cars via SSR HTML (T1)."""

    DOMAIN = "myway.be"
    COUNTRY = "BE"

    HOST = "www.myway.be"

    PAGE_SIZE = 24
    MAX_PAGES = 200

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    # ── primitives ────────────────────────────────────────────────────────────

    def partition_params(self) -> list[dict[str, Any]]:
        """Single segment — global paginator over all certified inventory."""
        return [{}]

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
        base = f"https://{self.HOST}/fr/offre-voitures-occasion/"
        qp: list[str] = ["trier-par=-publicationDate"]
        if page_num > 1:
            qp.append(f"page={page_num}")
        return f"{base}?{'&'.join(qp)}"

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
