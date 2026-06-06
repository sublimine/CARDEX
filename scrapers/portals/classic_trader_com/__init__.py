"""
classic-trader.com — Germany/EU, classic & luxury car marketplace (~8.5k cars).

Discovery via the **listing-level sitemap** rather than SSR HTML pagination.
The previous `/de/automobile/suche?page=N` scraper extracted ZERO links: its regex
targeted `/de/automobile/angebote/`, but the real detail path is
`/de/automobile/inserat/`. The CDN sitemap index carries per-language × type
children; CHILD_RE keeps the German car listing parts.

Route [VERIFIED 2026-06-06]:
  Index   https://cdn.classic-trader.com/I/sitemap/sitemap.xml  (<sitemapindex>, 54 children)
  Cars    `sitemap.de.car.listing.xml` + `…listing_0/_1/_2.xml` (DE cars; other
          languages and motorbikes are skipped to avoid duplicate inventory).
  Detail  https://www.classic-trader.com/de/automobile/inserat/<make>/<model>/<variant>/<year>/<id>
          (e.g. .../inserat/bentley/6-1-2-liter/6-1-2-liter/1931/2543; ~8.5k cars).
  WAF     none (Astro SSG/SSR + CDN). Tier.T1.
"""
from __future__ import annotations

import re

from scrapers.portals.sitemap_listing_base import SitemapListingScraper


class ClassicTraderDEScraper(SitemapListingScraper):
    """classic-trader.com cars via the CDN listing sitemap (T1)."""

    DOMAIN = "classic-trader.com"
    COUNTRY = "DE"

    SITEMAP_URL = "https://cdn.classic-trader.com/I/sitemap/sitemap.xml"
    CHILD_RE = re.compile(r"/sitemap\.de\.car\.listing")  # DE cars only
    DETAIL_RE = re.compile(r"/de/automobile/inserat/")
