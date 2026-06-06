"""
annonces-automobile.com — France, premium classifieds portal (~44k annonces).

Discovery via the **listing-level sitemap** rather than SSR HTML pagination.
The previous `/l-s/occasion?pg=N` scraper extracted `/acheter/{slug}` links; the
canonical detail page is `/d/{id}`. The detail sitemap lists every `/d/{id}`
directly, in one pass, with no pagination.

Route [VERIFIED 2026-06-06]:
  Index   https://www.annonces-automobile.com/sitemap.xml  (<sitemapindex>)
  Cars    `sitemap_detail.xml` (the `sitemap_list.xml` child is segment/SRP pages).
  Detail  https://www.annonces-automobile.com/d/<id>
          (e.g. /d/4563550; 44,138 detail URLs).
  WAF     none (SSR HTML + jQuery). Tier.T1.
"""
from __future__ import annotations

import re

from scrapers.portals.sitemap_listing_base import SitemapListingScraper


class AnnoncesAutomobileFRScraper(SitemapListingScraper):
    """annonces-automobile.com via the detail sitemap (T1)."""

    DOMAIN = "annonces-automobile.com"
    COUNTRY = "FR"

    SITEMAP_URL = "https://www.annonces-automobile.com/sitemap.xml"
    CHILD_RE = re.compile(r"/sitemap_detail\.xml")
    DETAIL_RE = re.compile(r"/d/\d+")
