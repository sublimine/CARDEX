"""
simplicicar.com — France/Belgium, used car franchise network (~6,000 vehicles).

T1 (No WAF): PrestaShop CMS backend with no anti-bot protection.  The site
is a franchise network with 100+ points of sale across France and Belgium,
selling certified used vehicles.

Approach: SSR HTML parsing.  PrestaShop renders server-side HTML with
product listing pages.  Extract vehicle detail URLs from search result cards.
The site may also expose a sitemap with all vehicle URLs.

Gold nuggets [research 2026-06-04]:

  Search URL    /occasions?page={N}                                [INFERRED]
                /occasions?marque={brand}
                /vehicule-occasion/{slug}                          [INFERRED]
  Framework     PrestaShop CMS (PHP)                               [CONFIRMED]
  WAF           None                                               [CONFIRMED]
  Network       100+ points of sale (FR, BE)                       [CONFIRMED]
  Inventory     ~6,000 vehicles                                    [CONFIRMED]
  Sitemap       /sitemap.xml (likely PrestaShop default)           [INFERRED]

Partition: single segment (small-medium inventory).  One paginated pass.
Subdivision not needed for <10k listings.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BASE_URL = "https://www.simplicicar.com/occasions"

# PrestaShop vehicle listing link patterns
_LISTING_LINK_RE = re.compile(
    r'href="(/(?:vehicule-occasion|occasion|voiture-occasion)/[^"]+)"',
    re.IGNORECASE,
)
_CARD_LINK_RE = re.compile(
    r'href="(https?://(?:www\.)?simplicicar\.com/(?:vehicule-occasion|occasion|voiture-occasion)/[^"]+)"',
    re.IGNORECASE,
)

# Sitemap URL extraction
_LOC_RE = re.compile(r"<loc>\s*(https?://[^<]+)\s*</loc>", re.IGNORECASE)


class SimplicicarFRScraper(BasePortalScraper):
    """SSR HTML scraper for simplicicar.com (T1, no WAF)."""

    DOMAIN = "simplicicar.com"
    COUNTRY = "FR"

    PAGE_SIZE = 24
    MAX_PAGES = 50

    SLEEP_BASE = 1.0
    SLEEP_JITTER = 0.5

    def partition_params(self) -> list[dict[str, Any]]:
        """Single segment — inventory fits in one paginated pass."""
        return [{}]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Load search result page and extract vehicle listing URLs."""
        url = f"{_BASE_URL}?page={page_num}"

        try:
            resp = await session.get(url, timeout=30)
        except Exception as exc:  # transport-level: DNS, reset, timeout, proxy drop
            log.debug("simplicicar.com transport error %s: %s", url[:90], exc)
            return []
        if resp.status_code != 200:
            log.warning(
                "simplicicar.com status=%d page=%d", resp.status_code, page_num
            )
            return []

        return _extract_listing_urls(resp.text)

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """No subdivision needed — inventory fits in single pass."""
        return []


def _extract_listing_urls(html: str) -> list[str]:
    """Extract vehicle listing URLs from PrestaShop SSR HTML."""
    urls: list[str] = []
    seen: set[str] = set()

    # Relative URLs
    for path in _LISTING_LINK_RE.findall(html):
        full = f"https://www.simplicicar.com{path}"
        if full not in seen:
            seen.add(full)
            urls.append(full)

    # Absolute URLs
    for full_url in _CARD_LINK_RE.findall(html):
        if full_url not in seen:
            seen.add(full_url)
            urls.append(full_url)

    return urls
