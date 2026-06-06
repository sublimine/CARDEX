"""
gueudet.fr — France, Gueudet 1880 multi-brand dealer group (~5.3k VO).

Discovery via the **listing-level sitemap** rather than a 34-brand SSR sweep.
The dedicated vehicle sitemap lists every detail URL directly, and it sidesteps
the robots `Disallow: /*?page=*` rule the brand-pager tripped.

Route [VERIFIED 2026-06-06]:
  Index   https://www.gueudet.fr/storage/sitemap.xml  (<sitemapindex>, 7 children)
  Cars    `storage/sitemap-vehicles.xml` (5,344 vehicles).
  Detail  https://www.gueudet.fr/voiture/<condition>/<brand>/<model>/<slug>/<id>
          (e.g. /voiture/demonstration/bmw/serie-1/116-122-ch-dkg7-m-sport-design/105520).
  WAF     none. Tier.T1.
"""
from __future__ import annotations

import re

from scrapers.portals.sitemap_listing_base import SitemapListingScraper


class GueudetFRScraper(SitemapListingScraper):
    """gueudet.fr used vehicles via the vehicle sitemap (T1)."""

    DOMAIN = "gueudet.fr"
    COUNTRY = "FR"

    SITEMAP_URL = "https://www.gueudet.fr/storage/sitemap.xml"
    CHILD_RE = re.compile(r"/sitemap-vehicles\.xml")
    DETAIL_RE = re.compile(r"/voiture/")
