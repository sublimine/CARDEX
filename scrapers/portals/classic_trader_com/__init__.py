"""
classic-trader.com — Germany/EU, luxury & classic car marketplace (~8,500 listings).

T1 (No WAF): Astro framework (SSG/SSR) with CDN at cdn.classic-trader.com.
No anti-bot protection — robots.txt is entirely commented out.  Niche premium
segment covering classic cars, youngtimers, and luxury vehicles.

Approach: SSR HTML parsing.  Search results pages at
/{lang}/automobile/suche render listing cards.  JSON-LD structured data on
SRP pages provides item counts and metadata.  Sitemaps organized by
language × type at CDN.

Gold nuggets [research 2026-06-04]:

  Search URL    /de/automobile/suche?page={N}                      [CONFIRMED]
                /de/automobile/suche/{make}?page={N}               [INFERRED]
  Framework     Astro (SSG/SSR) + CDN                              [CONFIRMED]
  WAF           None (robots.txt entirely commented out)           [CONFIRMED]
  Sitemaps      CDN sitemaps by language × type                    [CONFIRMED]
  JSON-LD       schema.org structured data on SRP                  [CONFIRMED]
  Inventory     ~8,500 car listings                                [CONFIRMED]
  Languages     de, en, fr, it                                     [INFERRED]
  Consent       Cookiebot                                          [CONFIRMED]

Partition: single segment with pagination.  Small enough inventory for one pass.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BASE_URL = "https://www.classic-trader.com/de/automobile/suche"

# Listing link patterns
_LISTING_LINK_RE = re.compile(
    r'href="(/de/automobile/angebote/[^"]+)"', re.IGNORECASE
)
_CARD_LINK_RE = re.compile(
    r'href="(https?://(?:www\.)?classic-trader\.com/de/automobile/angebote/[^"]+)"',
    re.IGNORECASE,
)


class ClassicTraderDEScraper(BasePortalScraper):
    """SSR HTML scraper for classic-trader.com (T1, no WAF)."""

    DOMAIN = "classic-trader.com"
    COUNTRY = "DE"

    PAGE_SIZE = 24
    MAX_PAGES = 50

    SLEEP_BASE = 1.5
    SLEEP_JITTER = 0.5

    def partition_params(self) -> list[dict[str, Any]]:
        """Single segment — inventory is small enough for one paginated pass."""
        return [{}]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Load search page and extract listing URLs."""
        url = f"{_BASE_URL}?page={page_num}"

        try:
            resp = await session.get(url, timeout=30)
        except Exception as exc:  # transport-level: DNS, reset, timeout, proxy drop
            log.debug("classic-trader.com transport error %s: %s", url[:90], exc)
            return []
        if resp.status_code != 200:
            log.warning(
                "classic-trader.com status=%d page=%d",
                resp.status_code, page_num,
            )
            return []

        return _extract_listing_urls(resp.text)

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """No subdivision needed — single segment pass."""
        return []


def _extract_listing_urls(html: str) -> list[str]:
    """Extract listing URLs from Astro SSR HTML."""
    urls: list[str] = []
    seen: set[str] = set()

    for path in _LISTING_LINK_RE.findall(html):
        full = f"https://www.classic-trader.com{path}"
        if full not in seen:
            seen.add(full)
            urls.append(full)

    for full_url in _CARD_LINK_RE.findall(html):
        if full_url not in seen:
            seen.add(full_url)
            urls.append(full_url)

    return urls
