"""
gowago.ch — Switzerland, online car leasing marketplace (~5k used cars).

Discovery via the **listing-level sitemap** rather than 423 paginated SSR pages.
The products sitemaps enumerate every `/en/listing/...` detail URL in two XML
fetches, with no pager fragility.

Route [VERIFIED 2026-06-06]:
  Index   https://gowago.ch/sitemap/sitemap-index.xml  (<sitemapindex>)
  Cars    `products-sitemap-0.xml` + `products-sitemap-1.xml` (each carries the
          three locales DE/FR/EN/IT for every vehicle; CHILD_RE keeps the products
          children, DETAIL_RE keeps the EN locale to dedup to one URL/vehicle).
  Detail  https://gowago.ch/en/listing/<brand>-<model>/<id>
          (e.g. /en/listing/ford-puma/8EAA4E82; ~5,009 unique vehicles).
  WAF     none. Tier.T1.
"""
from __future__ import annotations

import re

from scrapers.portals.sitemap_listing_base import SitemapListingScraper


class GowagoCHScraper(SitemapListingScraper):
    """gowago.ch used cars via the products sitemap (T1)."""

    DOMAIN = "gowago.ch"
    COUNTRY = "CH"

    SITEMAP_URL = "https://gowago.ch/sitemap/sitemap-index.xml"
    CHILD_RE = re.compile(r"/products-sitemap-")  # vehicle shards, skip static sitemap-N
    DETAIL_RE = re.compile(r"/en/listing/")        # one locale per vehicle
