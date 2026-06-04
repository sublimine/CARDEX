"""
caravenue.com — FR/BE/LU/CH, multi-brand dealer group (~2,400 vehicles, 62 dealerships).

T0 (No WAF): Next.js + Turbopack frontend, no Cloudflare or anti-bot protection.
The site is a dealership group aggregating inventory from 62 points of sale across
France, Belgium, Luxembourg, and Switzerland.

Approach: Next.js __NEXT_DATA__ extraction.  The search results page at
/vehicules-occasions renders server-side HTML with a __NEXT_DATA__ JSON blob
containing all listing data.  Fallback to SSR HTML link extraction if the
JSON structure changes.

Gold nuggets [research 2026-06-04]:

  Search URL    /vehicules-occasions?page={N}                      [INFERRED]
                /vehicules-occasions?marque={brand}
  Framework     Next.js 14+ with Turbopack                         [CONFIRMED]
  WAF           None                                               [CONFIRMED]
  Dealers       62 points of sale (FR/BE/LU/CH)                    [CONFIRMED]
  Inventory     ~2,400 vehicles                                    [CONFIRMED]
  Data source   __NEXT_DATA__ JSON or SSR HTML links               [INFERRED]

Partition: single segment (small inventory).  One pass with pagination is
sufficient — no price bands needed for <3k listings.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BASE_URL = "https://www.caravenue.com/vehicules-occasions"

# __NEXT_DATA__ extraction
_NEXT_DATA_RE = re.compile(
    r'<script\s+id="__NEXT_DATA__"\s+type="application/json">\s*({.*?})\s*</script>',
    re.DOTALL,
)

# Fallback: SSR HTML link extraction for vehicle detail pages
_LISTING_LINK_RE = re.compile(
    r'href="(/vehicule(?:s|-occasion)?/[^"]+)"', re.IGNORECASE
)
_CARD_LINK_RE = re.compile(
    r'href="(https?://(?:www\.)?caravenue\.com/vehicule(?:s|-occasion)?/[^"]+)"',
    re.IGNORECASE,
)


class CaravenueFRScraper(BasePortalScraper):
    """Next.js scraper for caravenue.com (T0, no WAF)."""

    DOMAIN = "caravenue.com"
    COUNTRY = "FR"

    PAGE_SIZE = 24
    MAX_PAGES = 50

    SLEEP_BASE = 1.0
    SLEEP_JITTER = 0.5

    def partition_params(self) -> list[dict[str, Any]]:
        """Single segment — inventory is small enough for one pass."""
        return [{}]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Load search page, extract listing URLs from __NEXT_DATA__ or HTML."""
        url = f"{_BASE_URL}?page={page_num}"

        resp = await session.get(url, timeout=30)
        if resp.status_code != 200:
            log.warning("caravenue.com status=%d page=%d", resp.status_code, page_num)
            return []

        # Try __NEXT_DATA__ first
        urls = _extract_from_next_data(resp.text)
        if urls:
            return urls

        # Fallback to SSR HTML link extraction
        return _extract_from_html(resp.text)

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """No subdivision needed — inventory fits in single pass."""
        return []


def _extract_from_next_data(html: str) -> list[str]:
    """Parse __NEXT_DATA__ JSON and return listing URLs."""
    m = _NEXT_DATA_RE.search(html)
    if not m:
        return []

    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        log.warning("caravenue.com: malformed __NEXT_DATA__ JSON")
        return []

    urls: list[str] = []
    page_props = data.get("props", {}).get("pageProps", {})

    # Try common Next.js vehicle listing structures
    vehicles = (
        page_props.get("vehicles")
        or page_props.get("listings")
        or page_props.get("cars")
        or page_props.get("results", {}).get("items")
        or page_props.get("data", {}).get("vehicles")
        or []
    )

    for item in vehicles:
        url = item.get("url") or item.get("slug") or item.get("href")
        if url:
            if not url.startswith("http"):
                url = f"https://www.caravenue.com{url}"
            urls.append(url)
            continue
        # Fallback: construct from ID
        vid = item.get("id") or item.get("vehicleId")
        if vid:
            urls.append(f"https://www.caravenue.com/vehicule/{vid}")

    return urls


def _extract_from_html(html: str) -> list[str]:
    """Fallback: extract listing URLs from SSR HTML."""
    urls: list[str] = []
    seen: set[str] = set()

    for path in _LISTING_LINK_RE.findall(html):
        full = f"https://www.caravenue.com{path}"
        if full not in seen:
            seen.add(full)
            urls.append(full)

    for full_url in _CARD_LINK_RE.findall(html):
        if full_url not in seen:
            seen.add(full_url)
            urls.append(full_url)

    return urls
