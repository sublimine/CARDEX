"""
simplicicar.com — France/Belgium, used-car franchise network (~6k vehicles).

Discovery via the **listing-level sitemap** rather than SSR HTML pagination.
The previous `/occasions?page=N` scraper was dead: that path returns HTTP 404 and
its regexes never matched (real product URLs are `/{cat_id}/{id}-{slug}.html`).
The PrestaShop sitemap is a flat urlset; DETAIL_RE keeps the product pages and
drops the CMS/category entries.

Route [VERIFIED 2026-06-06]:
  Sitemap https://www.simplicicar.com/sitemap.xml  (<urlset>, 6,839 locs)
  Detail  https://www.simplicicar.com/<cat_id>/<id>-<slug>.html
          (e.g. /417/981-audi-q3-35-tdi-20-150-limited-s-tronic.html; ~5,997 products).
  WAF     none (PrestaShop). Tier.T1.
"""
from __future__ import annotations

import re

from scrapers.portals.sitemap_listing_base import SitemapListingScraper


class SimplicicarFRScraper(SitemapListingScraper):
    """simplicicar.com vehicles via the PrestaShop sitemap (T1)."""

    DOMAIN = "simplicicar.com"
    COUNTRY = "FR"

    SITEMAP_URL = "https://www.simplicicar.com/sitemap.xml"
    DETAIL_RE = re.compile(r"/\d+/\d+-[^/]+\.html")  # /{cat_id}/{id}-{slug}.html products
