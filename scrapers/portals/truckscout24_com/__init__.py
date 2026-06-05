"""
truckscout24.com — Germany/EU, commercial vehicle classifieds (~80-120k listings).

T1 (No significant WAF): Yii2/PHP backend with jQuery + Bootstrap frontend.
Server-side rendered HTML with PJAX.  NOT the same platform as autoscout24.de
(which is Next.js + Akamai).  ClaudeBot allowed with 5s crawl-delay.  Part of
the AutoScout24 Group but runs on a completely separate tech stack.

Approach: SSR HTML parsing.  Search results at /{category}/used?page={N}
render listing cards server-side.  Extract listing URLs from the HTML.
Sitemaps also available at /data/sitemaps/ (gzipped).

Gold nuggets [research 2026-06-04]:

  Search URL    /trucks/used?page={N}                              [CONFIRMED]
                /vans-up-to-7-5-t/used?page={N}                   [INFERRED]
                /trailers/used?page={N}                            [INFERRED]
  Listing URL   /tsp/ts-{id}                                       [CONFIRMED]
  Framework     Yii2 (PHP) + jQuery + Bootstrap + PJAX             [CONFIRMED]
  WAF           None significant (5s crawl-delay in robots.txt)    [CONFIRMED]
  Sitemaps      /data/sitemaps/ (gzipped XML)                      [CONFIRMED]
  Inventory     ~80-120k total listings                            [ESTIMATED]
  Group         AutoScout24 Group (separate platform stack)        [CONFIRMED]

Partition: vehicle categories.  Each category is paginated separately.
Subdivision splits by sub-category if cap is hit.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BASE_URL = "https://www.truckscout24.com"

# ── vehicle categories (URL slugs) ──────────────────────────────────────────
_CATEGORIES: tuple[str, ...] = (
    "trucks",
    "vans-up-to-7-5-t",
    "trailers",
    "semi-trailers",
    "construction-machines",
    "agricultural-vehicles",
    "buses",
    "forklifts",
)

# Listing link patterns in SSR HTML
_LISTING_LINK_RE = re.compile(
    r'href="(/tsp/ts-[^"]+)"', re.IGNORECASE
)
_CARD_LINK_RE = re.compile(
    r'href="(https?://(?:www\.)?truckscout24\.com/tsp/ts-[^"]+)"',
    re.IGNORECASE,
)


class TruckScout24DEScraper(BasePortalScraper):
    """SSR HTML scraper for truckscout24.com (T1, no WAF)."""

    DOMAIN = "truckscout24.com"
    COUNTRY = "DE"

    PAGE_SIZE = 20
    MAX_PAGES = 50

    SLEEP_BASE = 5.0   # Respect robots.txt 5s crawl-delay
    SLEEP_JITTER = 1.0

    def partition_params(self) -> list[dict[str, Any]]:
        """One segment per vehicle category."""
        return [{"category": cat} for cat in _CATEGORIES]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Load search page and extract listing URLs."""
        category = params["category"]
        url = f"{_BASE_URL}/{category}/used?page={page_num}"

        try:
            resp = await session.get(url, timeout=30)
        except Exception as exc:  # transport-level: DNS, reset, timeout, proxy drop
            log.debug("truckscout24.com transport error %s: %s", url[:90], exc)
            return []
        if resp.status_code != 200:
            log.warning(
                "truckscout24.com status=%d cat=%s page=%d",
                resp.status_code, category, page_num,
            )
            return []

        return _extract_listing_urls(resp.text)

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """No subdivision — categories are already fine-grained."""
        return []


def _extract_listing_urls(html: str) -> list[str]:
    """Extract listing URLs from SSR HTML."""
    urls: list[str] = []
    seen: set[str] = set()

    for path in _LISTING_LINK_RE.findall(html):
        full = f"{_BASE_URL}{path}"
        if full not in seen:
            seen.add(full)
            urls.append(full)

    for full_url in _CARD_LINK_RE.findall(html):
        if full_url not in seen:
            seen.add(full_url)
            urls.append(full_url)

    return urls
