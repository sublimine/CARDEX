"""
2ememain.be — Belgium (French), Adevinta classifieds cars vertical (~102k listings).

Francophone mirror of 2dehands.be (same Adevinta backend, same DB, same CloudFront;
only the hostname and UI language differ — and the car path is `/v/autos/`, not
`/v/auto-s/`). Discovery via the **listing-level sitemap** rather than the LRP
search API: `/lrp/api/search` is robots-disallowed and window-capped (~5k/query),
while the sitemap is robots-allowed, uncapped, and lists every detail URL directly.

In production the coordinator runs EITHER tweedehands_be OR deuxememain_be (same
inventory); both stay registered so the router can dispatch whichever domain a
work_queue row names.

Route [VERIFIED 2026-06-06]:
  Index   https://www.2ememain.be/sitemap/sitemap.xml  (<sitemapindex>, 2,733 children)
  Cars    organic shards `…/l2.autos.<brand>.<N>.sitemap.xml.gz` (gzipped); the
          paid `admarkt_l2.*` shards are excluded by CHILD_RE.
  Detail  https://www.2ememain.be/v/autos/<brand>/m<itemId>-<slug>
          (e.g. l2.autos.volkswagen.1 → 4,200 detail URLs, same itemIds as 2dehands).
  WAF     none (CloudFront). Tier.T0.
"""
from __future__ import annotations

import re

from scrapers.portals.sitemap_listing_base import SitemapListingScraper


class DeuxememainBEScraper(SitemapListingScraper):
    """2ememain.be cars via the organic listing sitemap (T0, French mirror)."""

    DOMAIN = "2ememain.be"
    COUNTRY = "BE"

    SITEMAP_URL = "https://www.2ememain.be/sitemap/sitemap.xml"
    CHILD_RE = re.compile(r"/l2\.autos\.")   # organic car shards only (skip admarkt_l2)
    DETAIL_RE = re.compile(r"/v/autos/")
