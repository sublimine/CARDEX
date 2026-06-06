"""
cardoen.be — Belgium, multi-brand dealer (~1.2k VO).

Discovery via the **listing-level sitemap** rather than SSR HTML pagination.
The previous `/fr/achat/occasions/?page=N` scraper extracted ZERO detail links:
its regex anchored on `/fr/achat/{slug}/`, but the live detail URL form is
`/fr/auto/{brand}/{model}/{variant}/{id}/` (the `/fr/achat/...` links on the page
are category pages). The product sitemap lists the correct detail URLs directly.

Route [VERIFIED 2026-06-06]:
  Sitemap https://www.cardoen.be/sitemap-product.xml  (<urlset>, 1,201 vehicles)
  Detail  https://www.cardoen.be/fr/auto/<brand>/<model>/<variant>/<id>/?vehicleId=<id>
          (e.g. /fr/auto/toyota/yaris-hybrid-hev/120h-1-5-style-75-at/331355/).
  WAF     none (Cloudflare CDN, no challenge). Tier.T1.
"""
from __future__ import annotations

import re

from scrapers.portals.sitemap_listing_base import SitemapListingScraper


class CardoenBEScraper(SitemapListingScraper):
    """cardoen.be VO via the product sitemap (T1)."""

    DOMAIN = "cardoen.be"
    COUNTRY = "BE"

    SITEMAP_URL = "https://www.cardoen.be/sitemap-product.xml"
    DETAIL_RE = re.compile(r"/(?:fr|nl)/auto/")
