"""
milanuncios.com — Spain, major general classifieds (~150k car listings).

T3 (DataDome): both web and mobile API are protected by DataDome with full
TLS fingerprinting and behavioral analysis.  The Android SDK integrates at
the OkHttp interceptor level, so mobile traffic is also fingerprinted.

Approach: Camoufox headless browser + __NEXT_DATA__ extraction.  The site
is Next.js SSR — every search page embeds a <script id="__NEXT_DATA__">
JSON blob containing all listing data for the current page.  A Camoufox
session that passes DataDome can load the SSR page and parse the embedded
JSON, extracting ~35 fields per listing.

Gold nuggets [research 2026-06-04]:

  Search URL    /coches-de-segunda-mano/?pagina={N}                [CONFIRMED]
                /coches-de-segunda-mano/?desde={price}&hasta={price}
  Framework     Next.js + React (SSR)                              [CONFIRMED]
  Data source   <script id="__NEXT_DATA__"> JSON blob              [CONFIRMED]
  Item shape    props.pageProps.listingCards[].id                   [ASSUMED]
                props.pageProps.listingCards[].title
                props.pageProps.listingCards[].price
                props.pageProps.listingCards[].url
  Pagination    Query param ?pagina={N}, 30 items/page             [CONFIRMED]
  Max pages     ~50 (portal caps at 1500 results per search)       [ASSUMED]
  Price filter  desde={min}&hasta={max} (EUR)                      [CONFIRMED]
  Province      ?dempieza={province_code}                          [INFERRED]
  WAF           DataDome (JS challenge + behavioral + cookie)      [CONFIRMED]
  Mobile API    DataDome SDK in OkHttp interceptor — NOT bypass    [CONFIRMED]
  Block signal  DataDome CAPTCHA challenge page (HTML, no JSON)    [CONFIRMED]
  Inventory     ~150k used car listings                            [ESTIMATED]
  KrakenD GW    ~300 microservices on K8s, KrakenD API gateway     [CONFIRMED]

Partition: price bands (EUR).  Each band is paginated up to MAX_PAGES.
If a band hits the cap, subdivide into finer price sub-bands.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

_BASE_URL = "https://www.milanuncios.com/coches-de-segunda-mano/"

# ── price bands (EUR) ────────────────────────────────────────────────────────
_PRICE_BANDS: tuple[tuple[int, int | None], ...] = (
    (0,     2_000),
    (2_000, 4_000),
    (4_000, 6_000),
    (6_000, 8_000),
    (8_000, 10_000),
    (10_000, 13_000),
    (13_000, 16_000),
    (16_000, 20_000),
    (20_000, 25_000),
    (25_000, 30_000),
    (30_000, 40_000),
    (40_000, 60_000),
    (60_000, 100_000),
    (100_000, None),
)

# __NEXT_DATA__ extraction regex
_NEXT_DATA_RE = re.compile(
    r'<script\s+id="__NEXT_DATA__"\s+type="application/json">\s*({.*?})\s*</script>',
    re.DOTALL,
)


class MilanunciosESScraper(BasePortalScraper):
    """Next.js __NEXT_DATA__ scraper for milanuncios.com (T3, DataDome)."""

    DOMAIN = "milanuncios.com"
    COUNTRY = "ES"

    PAGE_SIZE = 30
    MAX_PAGES = 50

    # DataDome sessions need slower crawling to avoid behavioral detection.
    SLEEP_BASE = 3.0
    SLEEP_JITTER = 1.5

    def partition_params(self) -> list[dict[str, Any]]:
        """Price band segments."""
        return [
            {"price_from": pf, "price_to": pt}
            for pf, pt in _PRICE_BANDS
        ]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Load search page via Camoufox, extract __NEXT_DATA__ listing URLs."""
        price_from = params["price_from"]
        price_to = params.get("price_to")

        # Build search URL with price filter and pagination
        url = f"{_BASE_URL}?pagina={page_num}&desde={price_from}"
        if price_to is not None:
            url += f"&hasta={price_to}"

        resp = await session.get(url, timeout=30)
        if resp.status_code != 200:
            log.warning(
                "milanuncios.com status=%d price=%d-%s page=%d",
                resp.status_code, price_from, price_to, page_num,
            )
            return []

        # Check for DataDome challenge page
        if "geo.captcha-delivery.com" in resp.text or "datadome" in resp.text.lower():
            log.warning("milanuncios.com DataDome challenge on page %d", page_num)
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
    """Parse __NEXT_DATA__ JSON from SSR HTML and return listing deep-link URLs."""
    m = _NEXT_DATA_RE.search(html)
    if not m:
        log.debug("milanuncios.com: no __NEXT_DATA__ found")
        return []

    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        log.warning("milanuncios.com: malformed __NEXT_DATA__ JSON")
        return []

    urls: list[str] = []
    # Navigate the Next.js page props structure
    page_props = data.get("props", {}).get("pageProps", {})
    # Milanuncios uses a listingCards or adsList structure
    listings = (
        page_props.get("listingCards")
        or page_props.get("adsList")
        or page_props.get("initialData", {}).get("ads")
        or []
    )

    for item in listings:
        # Try multiple URL field patterns
        url = (
            item.get("url")
            or item.get("detailUrl")
            or item.get("seoUrl")
        )
        if url:
            if not url.startswith("http"):
                url = f"https://www.milanuncios.com{url}"
            urls.append(url)
            continue
        # Fallback: construct from ad ID
        ad_id = item.get("id") or item.get("adId")
        if ad_id:
            urls.append(f"https://www.milanuncios.com/{ad_id}")

    return urls
