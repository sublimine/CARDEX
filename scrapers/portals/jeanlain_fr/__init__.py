"""
occasions.jeanlain.com — France, Jean Lain Mobilités dealer group (~2.5k vehicles).

Discovery via the **listing-level sitemap** rather than SSR price-band pagination.
The dedicated vehicle sitemap lists every detail URL directly, so the price-band
partition + subdivision is no longer needed.

Route [VERIFIED 2026-06-06]:
  Index   https://occasions.jeanlain.com/sitemap.xml  (<sitemapindex>, 6 children)
  Cars    `vehicle-sitemap.xml` (2,713 locs; 171 non-vehicle pages filtered out).
  Detail  https://occasions.jeanlain.com/voiture/<brand>/modele-<model>/<slug>-<id>
          (e.g. /voiture/volkswagen/modele-t-roc/t-roc-398113; 2,542 vehicles).
  WAF     none. Tier.T1.
"""
from __future__ import annotations

import re

from scrapers.portals.sitemap_listing_base import SitemapListingScraper


class JeanLainFRScraper(SitemapListingScraper):
    """occasions.jeanlain.com vehicles via the vehicle sitemap (T1)."""

    DOMAIN = "occasions.jeanlain.com"
    COUNTRY = "FR"

    SITEMAP_URL = "https://occasions.jeanlain.com/sitemap.xml"
    CHILD_RE = re.compile(r"/vehicle-sitemap\.xml")
    DETAIL_RE = re.compile(r"/voiture/")
