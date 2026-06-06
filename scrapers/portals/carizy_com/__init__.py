"""
carizy.com — France, P2P car-sales platform (~1k annonces).

Discovery via the **listing-level sitemap** rather than Nuxt SSR pagination.
The previous `/voiture-occasion?page=N` regex expected `/voiture-occasion/{slug}`;
the real detail URL is `/voiture-occasion/annonce/{MAKE}/{MODEL}/{YEAR}/{id}`. The
sitemap lists every annonce directly.

Route [VERIFIED 2026-06-06]:
  Index   https://www.carizy.com/sitemap.xml  (<sitemapindex>, 3 children)
  Cars    `voiture-occasion/sitemap.xml` (1,301 locs; the other 301 are make/model
          + bodytype segments, filtered out by DETAIL_RE).
  Detail  https://www.carizy.com/voiture-occasion/annonce/<MAKE>/<MODEL>/<YEAR>/<id>
          (e.g. .../annonce/MERCEDES/GLB/2022/83041; ~1,000 vehicles).
  WAF     none (Nuxt SSR). Tier.T1.
"""
from __future__ import annotations

import re

from scrapers.portals.sitemap_listing_base import SitemapListingScraper


class CarizyFRScraper(SitemapListingScraper):
    """carizy.com P2P used cars via the listing sitemap (T1)."""

    DOMAIN = "carizy.com"
    COUNTRY = "FR"

    SITEMAP_URL = "https://www.carizy.com/sitemap.xml"
    CHILD_RE = re.compile(r"/voiture-occasion/sitemap\.xml")
    DETAIL_RE = re.compile(r"/voiture-occasion/annonce/")
