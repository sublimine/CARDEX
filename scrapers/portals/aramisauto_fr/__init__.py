"""
aramisauto.com — France, Aramis Group reconditioning dealer (~2.9k used cars).

Discovery via the **listing-level sitemap** rather than SSR HTML pagination.
The previous `/achat/occasion?page=N` scraper matched a stale `/achat/{brand}/
{model}/{slug}/` form; the live detail URL is `/voitures/{brand}/{model}/{trim}/
rv{id}/`. The product sitemap lists every vehicle in one fetch — and harvesting
a static XML avoids the Cloudflare JS-challenge risk the paginated SSR carried.

Route [VERIFIED 2026-06-06]:
  Sitemap https://www.aramisauto.com/sitemap-product.xml  (<urlset>, 2,909 vehicles)
  Detail  https://www.aramisauto.com/voitures/<brand>/<model>/<trim>/rv<id>/?vehicleId=<id>
          (e.g. /voitures/peugeot/308/allure-pack/rv995934/).
  WAF     Cloudflare CDN (no challenge on the sitemap). Tier.T1.
"""
from __future__ import annotations

import re

from scrapers.portals.sitemap_listing_base import SitemapListingScraper


class AramisAutoFRScraper(SitemapListingScraper):
    """aramisauto.com used cars via the product sitemap (T1)."""

    DOMAIN = "aramisauto.com"
    COUNTRY = "FR"

    SITEMAP_URL = "https://www.aramisauto.com/sitemap-product.xml"
    DETAIL_RE = re.compile(r"/voitures/")
