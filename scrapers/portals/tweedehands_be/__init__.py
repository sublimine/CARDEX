"""
2dehands.be — Belgium (Dutch), Adevinta classifieds cars vertical (~102k listings).

Dutch-language sibling of marktplaats.nl on the same Adevinta LRP backend.
Discovery via the **listing-level sitemap** rather than the LRP search API: the
`/lrp/api/search` route is robots-disallowed (`Disallow: /lrp/api/search*`) and
window-capped (~5,010/query), while the sitemap is robots-allowed, uncapped, and
lists every `/v/auto-s/...` detail URL directly.

Route [VERIFIED 2026-06-06]:
  Index   https://www.2dehands.be/sitemap/sitemap.xml  (<sitemapindex>, 2,736 children)
  Cars    organic shards `…/l2.auto-s.<brand>.<N>.sitemap.xml.gz` (gzipped); the
          paid `admarkt_l2.*` shards are excluded by CHILD_RE.
  Detail  https://www.2dehands.be/v/auto-s/<brand>/m<itemId>-<slug>
          (e.g. l2.auto-s.volkswagen.1 → 4,343 detail URLs).
  WAF     none (CloudFront). Tier.T0.
"""
from __future__ import annotations

import re

from scrapers.portals.sitemap_listing_base import SitemapListingScraper


class TweedehandsBEScraper(SitemapListingScraper):
    """2dehands.be cars via the organic listing sitemap (T0)."""

    DOMAIN = "2dehands.be"
    COUNTRY = "BE"

    SITEMAP_URL = "https://www.2dehands.be/sitemap/sitemap.xml"
    CHILD_RE = re.compile(r"/l2\.auto-s\.")   # organic car shards only (skip admarkt_l2)
    DETAIL_RE = re.compile(r"/v/auto-s/")
