"""
ocasionplus.com — Spain, multi-brand used-car dealer (~13.5k listings).

Discovery via the **listing-level sitemap** rather than the Next.js data route.
The previous approach guessed the `/_next/data/{buildId}/...` endpoint, the
pageProps field names, and a `/{slug}/{id}` detail form — all unverified and
buildId-fragile. The fichas sitemap lists every (slug-only) detail URL directly.

Route [VERIFIED 2026-06-06]:
  Index   https://www.ocasionplus.com/sitemap.xml  (<sitemapindex>, 263 children)
  Cars    `sitemap.fichas-coches.xml` (the per-brand/province children are SRP
          segments, excluded by CHILD_RE).
  Detail  https://www.ocasionplus.com/coches-segunda-mano/<slug>
          (slug ends in a unique id token, e.g. …-2024-hs0htqaz; 13,521 vehicles).
  WAF     none. Tier.T1.
"""
from __future__ import annotations

import re

from scrapers.portals.sitemap_listing_base import SitemapListingScraper


class OcasionPlusESScraper(SitemapListingScraper):
    """ocasionplus.com cars via the fichas listing sitemap (T1)."""

    DOMAIN = "ocasionplus.com"
    COUNTRY = "ES"

    SITEMAP_URL = "https://www.ocasionplus.com/sitemap.xml"
    CHILD_RE = re.compile(r"/sitemap\.fichas-coches\.xml")
    DETAIL_RE = re.compile(r"/coches-segunda-mano/")
