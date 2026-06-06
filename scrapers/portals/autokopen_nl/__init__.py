"""
autokopen.nl — Netherlands aggregator (Dealerdirect Media B.V., ~106k listings).

Discovery via the **listing-level sitemap** rather than the Next.js data route.
The previous approach guessed a `/_next/data/{buildId}/auto.json` endpoint plus the
pageProps field names — both unverified, and fragile to every deploy (buildId churn).
The sitemap is deterministic: three robots-allowed shards enumerate every
`/auto/detail/{slug}` URL directly, no buildId, no field guessing, no year×price grid.

Route [VERIFIED 2026-06-06]:
  Shards  https://autokopen.nl/sitemap/100.xml (45,000), /101.xml (45,000),
          /102.xml (18,394) — plain <urlset>s of detail URLs. (0-4.xml are
          static/segment pages and are not fetched.)
  Detail  https://autokopen.nl/auto/detail/<slug>
          (e.g. /auto/detail/mercedes-benz-c-klasse-2026-10999). ~108k total.
  WAF     none. Tier.T1.
"""
from __future__ import annotations

import re

from scrapers.portals.sitemap_listing_base import SitemapListingScraper


class AutoKopenNLScraper(SitemapListingScraper):
    """autokopen.nl cars via the listing sitemap shards (T1)."""

    DOMAIN = "autokopen.nl"
    COUNTRY = "NL"

    SITEMAP_URLS = (
        "https://autokopen.nl/sitemap/100.xml",
        "https://autokopen.nl/sitemap/101.xml",
        "https://autokopen.nl/sitemap/102.xml",
    )
    DETAIL_RE = re.compile(r"/auto/detail/")
