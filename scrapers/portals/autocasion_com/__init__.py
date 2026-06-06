"""
autocasion.com — Spain classified (cars, ~122,068 listings).

autocasion.com is a Vocento Group SSR property fronted by Cloudflare with TLS-only
gating. naked `curl_cffi` `impersonate="chrome"` passes every research surface; the
plain `requests` 403 pattern was observed for the sibling autotrack.nl property
under the same Cloudflare configuration. Tier.T1.

Gold nuggets [VERIFIED 2026-06-03 against the live site — docs/research/autocasion-com.md]:

  Search URL  GET https://www.autocasion.com/coches-segunda-mano/<province>/<fuel>?page={N}
  Surface     The /coches-ocasion global SRP only reaches ~9.6k of the 122k inventory
              (cap = page 400, 24 cards/page). The per-province × per-fuel SRP grid
              is the partition-capable surface.
  Filters     All query-string filter names (precio_desde/hasta, anno_desde/hasta,
              kms_hasta, precio_min/max, year_min/max, marca, province, …) were
              probed live and ALL returned the unfiltered baseline — REJECTED.
              autocasion encodes filters as URL SEGMENTS exclusively.
  Listings    Server-rendered HTML; 24–25 unique ad anchors per page.
  Detail URL  /coches-segunda-mano/<brand>-<model>-ocasion/<slug>-ref<NUMERIC_ID>
              (numeric REF id is canonical). Host: https://www.autocasion.com.
  Pagination  page=N (?page=N is the verified pager; ?numPag was rejected — overlap
              24/24 with page 1). Hard cap = page 400; page>=401 silently degrades
              to the sticky featured-card carousel (~5 cards) — short-page detector
              terminates the loop. 400 × 24 ≈ 9,600 ads/segment.
  Block sig   Cloudflare TLS gating only; no challenge body observed. The pager cap
              is a soft "len < PAGE_SIZE" not a 404.

Partition: 52 Spanish provinces × 6 fuel slugs = 312 cells. The Madrid grid (the
largest single province) totals 56,246 across the six fuels — matches the
province baseline 56,280 within page-update jitter, confirming the fuel grid is
exhaustive and mutually exclusive. The province list is hard-coded (harvested from
the official sitemap; stable Spanish administrative geography) so the scraper does
not depend on a refdata table or re-downloading the 5.6 MB sitemap each run.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from functools import cached_property
from itertools import product
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

# 52 Spanish provinces — verified live from autocasion's coches-segunda-mano sitemap
# (https://www.autocasion.com/uploads/sitemap-ng/coches-segunda-mano/coches-segunda-mano.xml).
_PROVINCES: tuple[str, ...] = (
    "alava", "albacete", "alicante", "almeria", "asturias", "avila", "badajoz",
    "barcelona", "burgos", "caceres", "cadiz", "cantabria", "castellon", "ceuta",
    "ciudad-real", "cordoba", "cuenca", "girona", "granada", "guadalajara",
    "guipuzcoa", "huelva", "huesca", "islas-baleares", "jaen", "la-coruna",
    "la-rioja", "las-palmas", "leon", "lleida", "lugo", "madrid", "malaga",
    "melilla", "murcia", "navarra", "orense", "palencia", "pontevedra",
    "salamanca", "segovia", "sevilla", "soria", "sta-c-de-tenerife", "tarragona",
    "teruel", "toledo", "valencia", "valladolid", "vizcaya", "zamora", "zaragoza",
)

# Verified mutually-exclusive fuel-slug grammar (Madrid sum matches Madrid baseline).
_FUELS: tuple[str, ...] = (
    "diesel", "gasolina", "electrico", "hibrido", "hibrido-enchufable", "gas",
)

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 500, 502, 503})


class AutocasionESScraper(BasePortalScraper):
    """autocasion.com cars via province × fuel SRP grid (T1)."""

    DOMAIN = "autocasion.com"
    COUNTRY = "ES"

    HOST = "www.autocasion.com"

    # 24 cards/page (occasional 25 from carousel overlap); pager caps at 400.
    PAGE_SIZE = 24
    MAX_PAGES = 400

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    PROVINCES: tuple[str, ...] = _PROVINCES
    FUELS: tuple[str, ...] = _FUELS

    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    @property
    def _search_base(self) -> str:
        return f"https://{self.HOST}/coches-segunda-mano"

    @cached_property
    def _listing_re(self) -> re.Pattern[str]:
        """Match `/coches-segunda-mano/<brand-model>-ocasion/<slug>-ref<DIGITS>` hrefs."""
        return re.compile(
            r"/coches-segunda-mano/([a-z0-9\-]+-ocasion/[a-z0-9\-]+-ref\d+)"
        )

    # ── primitives ─────────────────────────────────────────────────────────────
    def partition_params(self) -> list[dict[str, Any]]:
        """52 provinces × 6 fuels = 312 cells covering the full inventory."""
        return [
            {"province": p, "fuel": f}
            for p, f in product(self.PROVINCES, self.FUELS)
        ]

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

            return self._extract(self._read_body(response))

        log.warning("all %d attempts failed: %s", self.RETRY_ATTEMPTS, url[:90])
        return []

    # ── helpers ────────────────────────────────────────────────────────────────
    def _build_url(self, params: dict[str, Any], page_num: int) -> str:
        return f"{self._search_base}/{params['province']}/{params['fuel']}?page={page_num}"

    def _extract(self, html: str) -> list[str]:
        """Canonical detail URLs from `-ref<ID>` hrefs, within-page deduped."""
        seen: set[str] = set()
        out: list[str] = []
        for match in self._listing_re.finditer(html):
            slug = match.group(1)
            canonical = f"{self._base_url}/coches-segunda-mano/{slug}"
            if canonical not in seen:
                seen.add(canonical)
                out.append(canonical)
        return out

    async def _get(self, session: Any, url: str) -> Any | None:
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:  # transport-level
            log.debug("transport error %s: %s", url[:90], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(self.RETRY_BACKOFF_BASE**attempt * factor + random.uniform(0, 0.25))
