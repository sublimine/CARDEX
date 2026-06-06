"""
capcar.fr — France, P2P platform with 350+ agents (~1k curated cars).

Discovery via the **listing-level sitemap** rather than SSR HTML pagination.
The products sitemap lists every `/voiture-occasion/{slug}-r{id}` detail URL in a
single fetch — the same form the old `_LISTING_RE` targeted, but complete and
pager-independent.

Route [VERIFIED 2026-06-06]:
  Sitemap https://www.capcar.fr/sitemap/products.xml  (<urlset>, 1,000 vehicles)
  Detail  https://www.capcar.fr/voiture-occasion/<brand>-<model>-r<id>
          (e.g. /voiture-occasion/peugeot-308-r0107248).
  WAF     none. Tier.T1.
"""
from __future__ import annotations

import re

from scrapers.portals.sitemap_listing_base import SitemapListingScraper


class CapCarFRScraper(SitemapListingScraper):
    """capcar.fr P2P used cars via the products sitemap (T1)."""

    DOMAIN = "capcar.fr"
    COUNTRY = "FR"

    SITEMAP_URL = "https://www.capcar.fr/sitemap/products.xml"
    DETAIL_RE = re.compile(r"/voiture-occasion/[^/]+-r\d+")
