"""
autoboerse.de — Germany, Santander dealer marketplace (~250k vehicles).

Discovery via the **listing-level sitemap** rather than a 115-brand × price-band
SSR sweep. The sitemap tree enumerates every `/fahrzeugsuche/{slug}/{id}` detail
URL directly: a two-level index (sitemap.xml → autoboerse.xml → 11
Sitemap-Autoboerse-N.xml urlsets) that the base walks transparently.

Route [VERIFIED 2026-06-06]:
  Index   https://www.autoboerse.de/sitemap.xml → https://autoboerse.de/sitemap/autoboerse.xml
          → `…/autoboerse/Sitemap-Autoboerse-{0..10}.xml` (25,000 locs each).
  Detail  https://autoboerse.de/fahrzeugsuche/<slug>/<12-char-id>
          (e.g. /fahrzeugsuche/citroen-c3-benzin-sachsen-anhalt/rYP87WWOxJEo).
  WAF     none — Openbank Deutschland AG (Santander group). Tier.T1.
"""
from __future__ import annotations

import re

from scrapers.portals.sitemap_listing_base import SitemapListingScraper


class AutoboerseDEScraper(SitemapListingScraper):
    """autoboerse.de vehicles via the listing sitemap tree (T1)."""

    DOMAIN = "autoboerse.de"
    COUNTRY = "DE"

    SITEMAP_URL = "https://www.autoboerse.de/sitemap.xml"
    # The whole tree is vehicle sitemaps, so no CHILD_RE filter is needed.
    DETAIL_RE = re.compile(r"/fahrzeugsuche/[^/?]+/[^/?]+")  # /{slug}/{id}, not the 1-segment search page
