"""
gocar.be — Belgium, premium automotive classifieds portal (~30k listings).

T2 (Cloudflare Business): datacenter IPs get connection reset. Requires
Camoufox browser session to pass Cloudflare JS challenge.  The portal is a
Vue.js SPA — search results load via XHR to an internal API, but the same
API is behind CF so direct curl is impossible.

Approach: sitemap-based extraction.  gocar.be publishes per-brand vehicle
sitemaps at /sitemaps/vehicles-{lang}-{brand}.xml.  These contain every
active listing URL.  A Camoufox session can fetch these XML files after
passing the CF challenge once (cookies persist in the session).

Gold nuggets [research 2026-06-04]:

  Sitemap URL   /sitemaps/vehicles-nl-{brand}.xml                  [CONFIRMED via Apify]
  Sitemap URL   /sitemaps/vehicles-fr-{brand}.xml                  [INFERRED]
  Languages     nl (Dutch), fr (French)                            [CONFIRMED]
  Brand slugs   audi, bmw, citroen, dacia, fiat, ford, hyundai,
                kia, mazda, mercedes-benz, nissan, opel, peugeot,
                renault, seat, skoda, toyota, volkswagen, volvo    [PARTIAL]
  Listing URL   https://www.gocar.be/nl/tweedehands/{brand}/{slug} [CONFIRMED]
  WAF           Cloudflare Business                                [CONFIRMED]
  Framework     Vue.js SPA                                         [CONFIRMED]
  Block signal  HTTP 000 / connection reset from datacenter IPs    [CONFIRMED]
  Inventory     ~30k listings                                      [ESTIMATED]

Partition: brands (one segment per brand × language).  Each segment fetches
its sitemap XML and extracts all <loc> URLs.  No pagination needed — sitemaps
are complete.  Subdivision not needed (single sitemap per brand is small enough).
"""
from __future__ import annotations

import logging
import re
from itertools import product
from typing import Any

from scrapers.portals.base import BasePortalScraper

log = logging.getLogger(__name__)

# ── brand slugs (gocar.be URL convention) ────────────────────────────────────
_BRANDS: tuple[str, ...] = (
    "abarth", "alfa-romeo", "audi", "bmw", "citroen", "cupra", "dacia",
    "ds", "fiat", "ford", "honda", "hyundai", "jaguar", "jeep", "kia",
    "land-rover", "lexus", "mazda", "mercedes-benz", "mg", "mini",
    "mitsubishi", "nissan", "opel", "peugeot", "porsche", "renault",
    "seat", "skoda", "smart", "suzuki", "tesla", "toyota", "volkswagen",
    "volvo",
)

# gocar.be is bilingual (NL + FR).  NL has larger inventory.
_LANGUAGES: tuple[str, ...] = ("nl", "fr")

# Regex to extract <loc> URLs from sitemap XML.
_LOC_RE = re.compile(r"<loc>\s*(https?://[^<]+)\s*</loc>", re.IGNORECASE)


class GocarBEScraper(BasePortalScraper):
    """Sitemap-based scraper for gocar.be (T2, Cloudflare Business)."""

    DOMAIN = "gocar.be"
    COUNTRY = "BE"

    # Sitemaps are not paginated — one XML per brand.
    PAGE_SIZE = 10_000
    MAX_PAGES = 1

    def partition_params(self) -> list[dict[str, Any]]:
        """One segment per (language, brand) pair."""
        return [
            {"lang": lang, "brand": brand}
            for lang, brand in product(_LANGUAGES, _BRANDS)
        ]

    async def fetch_segment(
        self, session: Any, params: dict[str, Any], page_num: int
    ) -> list[str]:
        """Fetch sitemap XML for one brand and extract listing URLs."""
        lang = params["lang"]
        brand = params["brand"]
        url = f"https://www.gocar.be/sitemaps/vehicles-{lang}-{brand}.xml"

        resp = await session.get(url, timeout=30)
        if resp.status_code == 404:
            # Brand has no listings or sitemap doesn't exist for this brand
            log.debug("gocar.be sitemap 404 for %s/%s", lang, brand)
            return []
        if resp.status_code != 200:
            log.warning(
                "gocar.be sitemap %s/%s status=%d", lang, brand, resp.status_code
            )
            return []

        urls = _LOC_RE.findall(resp.text)
        # Filter to actual vehicle listing URLs (not category/brand index pages)
        listing_urls = [
            u for u in urls
            if "/tweedehands/" in u or "/voitures-occasion/" in u
        ]
        log.info(
            "gocar.be sitemap %s/%s: %d URLs (%d listing)",
            lang, brand, len(urls), len(listing_urls),
        )
        return listing_urls

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """No subdivision needed — sitemaps are complete per brand."""
        return []
