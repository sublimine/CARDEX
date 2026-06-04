"""
autoweek.nl — Netherlands, DPG Media automotive classifieds (~187k listings).

T2 (Akamai V3): editorial automotive media site with classifieds section.
Syndication mirror of AutoTrack.nl via Automotive MediaVentions (DPG Media +
Mediahuis JV).  Listings are expected to overlap ~100% with autotrack.nl, but
implemented as safety net per zero-loss policy.

Approach: SSR HTML parsing via Camoufox.  The occasions section renders
server-side HTML listing cards.  Akamai V3 requires Camoufox browser session.

Gold nuggets [research 2026-06-04]:

  Search URL    /occasions/?pagina={N}                             [INFERRED]
                /occasions/?prijsvan={P}&prijstot={P}              [INFERRED]
  Framework     Unknown (DPG Media stack)                          [INFERRED]
  WAF           Akamai V3                                          [CONFIRMED]
  Syndication   AutoTrack.nl via Automotive MediaVentions JV       [CONFIRMED]
  Inventory     ~187k listings (mirrored from AutoTrack)           [ESTIMATED]
  Dedup note    Expected ~100% overlap with autotrack.nl           [CONFIRMED]

Partition: price bands (EUR).  Dutch market price distribution.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BASE_URL = "https://www.autoweek.nl/occasions/"

# ── price bands (EUR) ────────────────────────────────────────────────────────
_PRICE_BANDS: tuple[tuple[int, int | None], ...] = (
    (0,     3_000),
    (3_000, 5_000),
    (5_000, 8_000),
    (8_000, 10_000),
    (10_000, 15_000),
    (15_000, 20_000),
    (20_000, 30_000),
    (30_000, 50_000),
    (50_000, None),
)

# Listing URL patterns in SSR HTML
_LISTING_LINK_RE = re.compile(
    r'href="(/occasions/[^"]*?/[^"]+\d[^"]*)"', re.IGNORECASE
)
_CARD_LINK_RE = re.compile(
    r'href="(https?://(?:www\.)?autoweek\.nl/occasions/[^"]*?/[^"]+\d[^"]*)"',
    re.IGNORECASE,
)


class AutoweekNLScraper(BasePortalScraper):
    """SSR HTML scraper for autoweek.nl (T2, Akamai V3)."""

    DOMAIN = "autoweek.nl"
    COUNTRY = "NL"

    PAGE_SIZE = 20
    MAX_PAGES = 50

    SLEEP_BASE = 2.0
    SLEEP_JITTER = 0.8

    def partition_params(self) -> list[dict[str, Any]]:
        """Price band segments."""
        return [
            {"price_from": pf, "price_to": pt}
            for pf, pt in _PRICE_BANDS
        ]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Load search page via Camoufox, extract listing URLs."""
        price_from = params["price_from"]
        price_to = params.get("price_to")

        url = f"{_BASE_URL}?pagina={page_num}&prijsvan={price_from}"
        if price_to is not None:
            url += f"&prijstot={price_to}"

        resp = await session.get(url, timeout=30)
        if resp.status_code != 200:
            log.warning(
                "autoweek.nl status=%d price=%d-%s page=%d",
                resp.status_code, price_from, price_to, page_num,
            )
            return []

        # Check for Akamai challenge
        if "akamai" in resp.text.lower() or "_abck" in resp.text:
            log.warning("autoweek.nl Akamai challenge on page %d", page_num)
            return []

        return _extract_listing_urls(resp.text)

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Split price band in half."""
        pf = params["price_from"]
        pt = params.get("price_to")
        if pt is None or (pt - pf) <= 1_000:
            return []
        mid = pf + (pt - pf) // 2
        return [
            {"price_from": pf, "price_to": mid},
            {"price_from": mid, "price_to": pt},
        ]


def _extract_listing_urls(html: str) -> list[str]:
    """Extract listing URLs from SSR HTML."""
    urls: list[str] = []
    seen: set[str] = set()

    for path in _LISTING_LINK_RE.findall(html):
        full = f"https://www.autoweek.nl{path}"
        if full not in seen:
            seen.add(full)
            urls.append(full)

    for full_url in _CARD_LINK_RE.findall(html):
        if full_url not in seen:
            seen.add(full_url)
            urls.append(full_url)

    return urls
