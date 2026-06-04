"""
belgiemobiel.be -- Belgian free classifieds portal (~20k+ auto listings).

PHP server-rendered site, sister platform of nederlandmobiel.nl (same software).
Uses numeric brand/model IDs in URL paths. Free for both private and business sellers.

Gold nuggets [research 2026-06-04]:

  Search URL    GET https://www.belgiemobiel.be/index.php
                    ?module=zoeken&voertuig=auto                         [VERIFIED]
  Brand filter  /auto-occasions/{brand_id}/{brand_slug}
                    ?module=zoeken&voertuig=auto&merk[]={brand_id}       [VERIFIED]
  Model filter  /auto-occasions/{brand_id}/{model_id}/{brand}/{model}   [VERIFIED]
  Detail URL    /tweedehands-auto/{brand}/{slug}/{numeric_id}            [ASSUMED from NL sister]
  Pagination    &pagina={N}  (1-based)                                   [ASSUMED from NL sister]
  Brand IDs     17=Audi, 29=BMW, 226=Volkswagen, 145=Mercedes-Benz,
                195=Seat, 199=Skoda, 217=Toyota                          [VERIFIED]
  Inventory     ~20,394 auto listings                                    [VERIFIED]
  Encoding      UTF-8 or ISO-8859-15 (like NL sister)                   [ASSUMED]
  WAF           None detected                                            [ASSUMED]
  Extern host   extern.belgiemobiel.be used for some brand pages         [VERIFIED]

Strategy: brand-ID partitioning (mirrors nederlandmobiel.nl pattern). With ~20k
listings, moderate partitioning by brand suffices. PHP SSR HTML regex extraction.
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

# Match vehicle detail URLs: /tweedehands-auto/{brand}/{slug}/{id}
# or /auto-occasions/{brand_id}/{model_id}/{brand}/{model}/detail/{id}
_LISTING_RE: re.Pattern[str] = re.compile(
    r'href="(/tweedehands-auto/[a-z0-9][a-z0-9_.-]+/[a-z0-9][a-z0-9_.-]+/\d{5,}[^"]*)"',
    re.IGNORECASE,
)

# Alternative: direct detail link with numeric ID
_DETAIL_RE: re.Pattern[str] = re.compile(
    r'href="(/(?:auto|voertuig|advertentie)/[a-z0-9][a-z0-9_-]*/\d{5,}[^"]*)"',
    re.IGNORECASE,
)

# Brand IDs verified from site research
_BRAND_IDS: tuple[tuple[int, str], ...] = (
    (3, "alfa-romeo"), (17, "audi"), (29, "bmw"), (43, "citroen"),
    (52, "dacia"), (56, "fiat"), (61, "ford"), (101, "honda"),
    (104, "hyundai"), (113, "jeep"), (118, "kia"),
    (131, "land-rover"), (145, "mercedes-benz"), (147, "mg"),
    (149, "mini"), (151, "mitsubishi"), (157, "nissan"),
    (163, "opel"), (171, "peugeot"), (175, "porsche"),
    (183, "renault"), (195, "seat"), (199, "skoda"),
    (200, "smart"), (210, "suzuki"), (213, "tesla"),
    (217, "toyota"), (226, "volkswagen"), (229, "volvo"),
)


class BelgieMobielBEScraper(BasePortalScraper):
    """belgiemobiel.be vehicles via PHP SSR HTML (T1)."""

    DOMAIN = "belgiemobiel.be"
    COUNTRY = "BE"

    HOST = "www.belgiemobiel.be"

    PAGE_SIZE = 30
    MAX_PAGES = 50

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 20

    BRAND_IDS: tuple[tuple[int, str], ...] = _BRAND_IDS

    def partition_params(self) -> list[dict[str, Any]]:
        return [{"brand_id": bid, "brand_slug": bslug} for bid, bslug in self.BRAND_IDS]

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
        bid = params["brand_id"]
        bslug = params["brand_slug"]
        base = f"https://{self.HOST}/auto-occasions/{bid}/{bslug}"
        qp = f"?module=zoeken&voertuig=auto&merk[]={bid}"
        if page_num > 1:
            qp += f"&pagina={page_num}"
        return f"{base}{qp}"

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
