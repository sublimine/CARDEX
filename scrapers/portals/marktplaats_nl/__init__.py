"""
marktplaats.nl — Netherlands' largest classifieds, cars vertical (~268k listings).

Discovery via the **listing-level sitemap** rather than the LRP search API.

The LRP JSON route (`/lrp/api/search`) is open and unauthenticated, but it is
robots-disallowed (`Disallow: /lrp/api/search*`) AND hard-capped at
`maxAllowedPageNumber=167` ⇒ ~5,010 listings per query, forcing a synthetic
year×price grid to even approach the 268k inventory. The sitemap has neither
problem: it is crawler-sanctioned (robots-allowed), uncapped, and enumerates
every bare `/v/auto-s/...` detail URL directly.

Route [VERIFIED 2026-06-06]:
  Index   https://www.marktplaats.nl/sitemap/sitemap.xml  (<sitemapindex>)
  Cars    ~106 organic shards `…/l2.auto-s.<brand>.<N>.sitemap.xml.gz` (gzipped).
          The parallel `admarkt_l2.*` shards are the paid-promo subset and are
          excluded (CHILD_RE requires a '/' before `l2`, which `admarkt_l2` lacks).
  Detail  `<loc>` https://www.marktplaats.nl/v/auto-s/<brand>/m<itemId>-<slug>
          (e.g. l2.auto-s.bmw.1 → 2,204 detail URLs).
  WAF     none (AWS CloudFront). Tier.T0.
"""
from __future__ import annotations

import re

from scrapers.portals.sitemap_listing_base import SitemapListingScraper


class MarktplaatsNLScraper(SitemapListingScraper):
    """marktplaats.nl cars via the organic listing sitemap (T0)."""

    DOMAIN = "marktplaats.nl"
    COUNTRY = "NL"

    SITEMAP_URL = "https://www.marktplaats.nl/sitemap/sitemap.xml"
    CHILD_RE = re.compile(r"/l2\.auto-s\.")   # organic car shards only (skip admarkt_l2)
    DETAIL_RE = re.compile(r"/v/auto-s/")
