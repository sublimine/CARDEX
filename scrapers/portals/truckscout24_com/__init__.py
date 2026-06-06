"""
truckscout24.com — Germany/EU, commercial-vehicle classifieds (~80-120k listings).

Discovery via the **listing-level sitemap** rather than category SSR pagination.
The previous per-category `/{category}/used?page=N` sweep capped at MAX_PAGES×20 =
1,000 listings/category; the gzipped listing sitemaps enumerate the full corpus in
two fetches. (`sitemap_new-listing_*` / `sitemap_deleted-listing_*` and the dealer/
category/search children are intentionally skipped — the two `sitemap_listing_*`
shards already cover every live listing.)

Route [VERIFIED 2026-06-06]:
  Index   https://www.truckscout24.com/sitemap.xml  (<sitemapindex>)
  Cars    `…/data/sitemaps/b_ts_en_US/sitemap_listing_1.xml.gz` (50,000) + `_2` (gzipped).
  Detail  https://www.truckscout24.com/tsp/ts-<id>  (e.g. /tsp/ts-396-57-89).
  WAF     none (Yii2/PHP). robots Crawl-delay 5 → polite SITEMAP_FETCH_DELAY. Tier.T1.
"""
from __future__ import annotations

import re

from scrapers.portals.sitemap_listing_base import SitemapListingScraper


class TruckScout24DEScraper(SitemapListingScraper):
    """truckscout24.com commercial vehicles via the listing sitemap (T1)."""

    DOMAIN = "truckscout24.com"
    COUNTRY = "DE"

    SITEMAP_URL = "https://www.truckscout24.com/sitemap.xml"
    CHILD_RE = re.compile(r"/sitemap_listing_\d+\.xml")  # full-listing shards only
    DETAIL_RE = re.compile(r"/tsp/ts-")

    SITEMAP_FETCH_DELAY = 5.0  # respect robots.txt Crawl-delay: 5
