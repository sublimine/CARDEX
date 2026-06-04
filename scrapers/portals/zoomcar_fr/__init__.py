"""
zoomcar.fr — France, automotive classifieds (~190k listings, 3900 dealers).

T2 (Cloudflare Pro): formerly ouestfrance-auto.com, migrated April 2026.
Backend is PHP (Symfony/Zend) with PostgreSQL and ElasticSearch/Algolia.
Datacenter IPs get connection reset (HTTP 000).  Requires Camoufox.

Approach: SSR HTML parsing.  The search results page at
/recherche/voiture-occasion renders server-side HTML with listing cards.
A Camoufox session that passes CF JS challenge can load these pages and
extract listing URLs from the DOM.

Gold nuggets [research 2026-06-04]:

  Search URL    /recherche/voiture-occasion?page={N}               [INFERRED]
                /recherche/voiture-occasion?marque={brand}
                /recherche/voiture-occasion?prix_min={P}&prix_max={P}
  Framework     PHP Symfony + ElasticSearch/Algolia                 [CONFIRMED]
  Mobile site   m.zoomcar.fr (active, lighter HTML)                [CONFIRMED]
  Mobile app    fr.zoomcar.zoomcarfr (Android)                     [CONFIRMED]
  WAF           Cloudflare Pro                                     [CONFIRMED]
  Block signal  HTTP 000 / connection reset from datacenter        [CONFIRMED]
  Dealers       ~3,900 professional dealers                        [CONFIRMED]
  Inventory     ~190-250k listings                                 [ESTIMATED]
  robots.txt    404 (none)                                         [CONFIRMED]
  sitemap.xml   404 (none)                                         [CONFIRMED]

Partition: price bands (EUR).  French market price distribution used.
Subdivision splits bands in half when cap is hit.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BASE_URL = "https://www.zoomcar.fr/recherche/voiture-occasion"

# ── price bands (EUR) ────────────────────────────────────────────────────────
_PRICE_BANDS: tuple[tuple[int, int | None], ...] = (
    (0,     3_000),
    (3_000, 5_000),
    (5_000, 8_000),
    (8_000, 10_000),
    (10_000, 13_000),
    (13_000, 16_000),
    (16_000, 20_000),
    (20_000, 25_000),
    (25_000, 30_000),
    (30_000, 40_000),
    (40_000, 60_000),
    (60_000, None),
)

# HTML link extraction — search result listing links
_LISTING_LINK_RE = re.compile(
    r'href="(/[^"]*?/annonce/[^"]+)"', re.IGNORECASE
)
# Alternative pattern for card-based layouts
_CARD_LINK_RE = re.compile(
    r'href="(https?://(?:www\.)?zoomcar\.fr/[^"]*?/annonce/[^"]+)"',
    re.IGNORECASE,
)


class ZoomcarFRScraper(BasePortalScraper):
    """SSR HTML scraper for zoomcar.fr (T2, Cloudflare Pro)."""

    DOMAIN = "zoomcar.fr"
    COUNTRY = "FR"

    PAGE_SIZE = 20
    MAX_PAGES = 50

    SLEEP_BASE = 2.0
    SLEEP_JITTER = 0.8

    def partition_params(self) -> list[dict[str, Any]]:
        """Price band segments."""
        return [
            {"price_min": pf, "price_max": pt}
            for pf, pt in _PRICE_BANDS
        ]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Load search page via Camoufox, extract listing URLs from HTML."""
        price_min = params["price_min"]
        price_max = params.get("price_max")

        url = f"{_BASE_URL}?page={page_num}&prix_min={price_min}"
        if price_max is not None:
            url += f"&prix_max={price_max}"

        resp = await session.get(url, timeout=30)
        if resp.status_code != 200:
            log.warning(
                "zoomcar.fr status=%d price=%d-%s page=%d",
                resp.status_code, price_min, price_max, page_num,
            )
            return []

        # Check for CF challenge
        if "challenge-platform" in resp.text or "Just a moment" in resp.text:
            log.warning("zoomcar.fr CF challenge on page %d", page_num)
            return []

        return _extract_listing_urls(resp.text)

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Split price band in half."""
        pf = params["price_min"]
        pt = params.get("price_max")
        if pt is None or (pt - pf) <= 1_000:
            return []
        mid = pf + (pt - pf) // 2
        return [
            {"price_min": pf, "price_max": mid},
            {"price_min": mid, "price_max": pt},
        ]


def _extract_listing_urls(html: str) -> list[str]:
    """Extract listing deep-link URLs from SSR HTML."""
    urls: list[str] = []
    seen: set[str] = set()

    # Try relative /annonce/ links first
    for path in _LISTING_LINK_RE.findall(html):
        full = f"https://www.zoomcar.fr{path}"
        if full not in seen:
            seen.add(full)
            urls.append(full)

    # Try absolute links
    for full_url in _CARD_LINK_RE.findall(html):
        if full_url not in seen:
            seen.add(full_url)
            urls.append(full_url)

    return urls
