"""
gaspedaal.nl — Netherlands meta-aggregator (cars, ~338,817 listings).

gaspedaal.nl is a Dutch meta-search portal that re-indexes inventory from several
NL classified sources. The marketplace surface is a Next.js SSR app at `/zoeken`
that embeds a schema.org `ItemList` JSON-LD block of 100 cars per page; the global
pager covers the full inventory (3,389 pages, last partial). No CDN-WAF challenge
seen on this property — naked `curl_cffi` `impersonate="chrome"` passes. Tier.T1.

Gold nuggets [VERIFIED 2026-06-03 against the live site — docs/research/gaspedaal-nl.md]:

  Search URL  GET https://www.gaspedaal.nl/zoeken?page={N}
  Listings    JSON-LD <script type="application/ld+json"> containing an
              ItemList of 100 Car/Product entries. Each carries @id, brand
              and model fields the canonical URL is reconstructed from.
  Detail URL  /auto/<brand-slug>/<model-slug>/<ID> [VERIFIED 200 for renault/
              captur, mercedes-benz/c-klasse, ds/ds-4, bmw/3-serie].
              Slug = NFKD-normalised, accent-stripped, lower-cased, spaces→hyphens.
              (e.g. "Citroën" → "citroen"; raw "citroën" gives 404.)
  ID source   The ItemList items expose @id = ".../zoeken[?page=N]#<ID>"; ID
              is the digits after the `#`.
  Pagination  page=1..3388 fully populated, page=3389 partial (17 items),
              page>=3390 returns 0 items. The global pager covers the
              entire 338k inventory — NO query filter / make-list partition.

Filter vocabulary — query-string filter names (priceTo, priceFrom, min/maxPrice,
priceMin/Max) were each probed against the live counter and ALL returned the
unfiltered baseline. gaspedaal encodes filters as URL segments (e.g. `/auto/audi`,
`/auto/audi/a3`), not query params; deferring to the segment grammar would require
a make/model refdata table. Since the pager covers the inventory, this scraper
deliberately uses a single empty segment, exactly like autotrack.nl.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import unicodedata
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BLOCK_STATUSES: frozenset[int] = frozenset({403, 429, 500, 502, 503})

# Match every Car/Product item in the ItemList — the @id always carries `#<digits>`
# (optionally after a `?page=N` query echo on page 2+). brand / model fields are
# stable strings on the same item.
_LDJSON_RE: re.Pattern[str] = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(?P<body>[\s\S]+?)</script>',
)
_ITEM_ID_RE: re.Pattern[str] = re.compile(
    r'"@id":"https://www\.gaspedaal\.nl/zoeken[^"]*#(\d+)"',
)


def _slugify(value: str) -> str:
    """NFKD-fold, strip combining marks, lower-case, spaces→hyphens.

    Verified: Citroën → 'citroen' (raw `citroën` returns 404). Mercedes-Benz,
    'DS 4' and '3 Serie' all round-trip to canonical detail URLs that 200.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(c for c in decomposed if not unicodedata.category(c).startswith("M"))
    return ascii_only.lower().strip().replace(" ", "-")


class GaspedaalNLScraper(BasePortalScraper):
    """gaspedaal.nl cars via the global SSR pager + JSON-LD ItemList (T1)."""

    DOMAIN = "gaspedaal.nl"
    COUNTRY = "NL"

    HOST = "www.gaspedaal.nl"

    # 100 ItemList entries per page; pager runs 1..3388 + a 17-item tail at 3389.
    # MAX_PAGES intentionally exceeds the observed last page so the short-page
    # detector terminates naturally and inventory growth doesn't truncate.
    PAGE_SIZE = 100
    MAX_PAGES = 3500

    RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE: float = 1.5
    REQUEST_TIMEOUT: int = 25

    @property
    def _base_url(self) -> str:
        return f"https://{self.HOST}"

    @property
    def _search_base(self) -> str:
        return f"https://{self.HOST}/zoeken"

    # ── primitives ─────────────────────────────────────────────────────────────
    def partition_params(self) -> list[dict[str, Any]]:
        """Single empty segment — the global pager covers the entire inventory."""
        return [{}]

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
        return f"{self._search_base}?page={page_num}"

    def _extract(self, html: str) -> list[str]:
        """Pull canonical detail URLs from JSON-LD ItemList items.

        Each `Car`/`Product` item contributes one URL of the form
        /auto/<brand-slug>/<model-slug>/<ID>. Items lacking brand or model are
        skipped (the canonical path can't be reconstructed without them).
        """
        seen: set[str] = set()
        out: list[str] = []
        for script in _LDJSON_RE.finditer(html):
            payload = script.group("body").strip()
            try:
                data = json.loads(payload)
            except (ValueError, TypeError):
                continue
            if not isinstance(data, dict) or data.get("@type") != "ItemList":
                continue
            for entry in data.get("itemListElement") or []:
                item = entry.get("item") if isinstance(entry, dict) else None
                if not isinstance(item, dict):
                    continue
                canonical = self._canonical_for(item)
                if canonical is None or canonical in seen:
                    continue
                seen.add(canonical)
                out.append(canonical)
        return out

    def _canonical_for(self, item: dict[str, Any]) -> str | None:
        at_id = item.get("@id")
        brand = item.get("brand")
        model = item.get("model")
        if not isinstance(at_id, str) or not isinstance(brand, str) or not isinstance(model, str):
            return None
        match = _ITEM_ID_RE.search(f'"@id":"{at_id}"')
        if match is None:
            return None
        return f"{self._base_url}/auto/{_slugify(brand)}/{_slugify(model)}/{match.group(1)}"

    async def _get(self, session: Any, url: str) -> Any | None:
        try:
            return await session.get(url, timeout=self.REQUEST_TIMEOUT)
        except Exception as exc:  # transport-level
            log.debug("transport error %s: %s", url[:90], exc)
            return None

    async def _retry_backoff(self, attempt: int, factor: float = 1.0) -> None:
        if attempt < self.RETRY_ATTEMPTS:
            await asyncio.sleep(self.RETRY_BACKOFF_BASE**attempt * factor + random.uniform(0, 0.25))
