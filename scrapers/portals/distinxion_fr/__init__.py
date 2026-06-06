"""
distinxion.fr — France, multi-brand network, 120+ POS (~4.7k VO).

Discovery via the **listing-level sitemap** rather than a 32-brand SSR sweep.
The catalog sitemap mixes vehicle detail pages with `/distributeur/...` mirrors
and category pages; DETAIL_RE keeps only the `/voitures/{brand}/{model}/{id}`
detail form.

Route [VERIFIED 2026-06-06]:
  Index   https://www.distinxion.fr/sitemap.xml  (<sitemapindex>, 5 children)
  Cars    `sitemap.catalog.xml` (10,267 locs; 4,717 are vehicle details).
  Detail  https://www.distinxion.fr/voitures/<brand>/<model>/<numeric_id>
          (e.g. /voitures/nissan/juke/765244).
  Note    catalog lastmod can lag ~months; the sink dedups/validates against the
          live inventory, so stale entries are harmless.
  WAF     none (Symfony SSR). Tier.T1.
"""
from __future__ import annotations

import re

from scrapers.portals.sitemap_listing_base import SitemapListingScraper


class DistinxionFRScraper(SitemapListingScraper):
    """distinxion.fr used vehicles via the catalog sitemap (T1)."""

    DOMAIN = "distinxion.fr"
    COUNTRY = "FR"

    SITEMAP_URL = "https://www.distinxion.fr/sitemap.xml"
    CHILD_RE = re.compile(r"/sitemap\.catalog\.xml")
    DETAIL_RE = re.compile(r"/voitures/[^/]+/[^/]+/\d+")  # brand/model/numeric_id only
