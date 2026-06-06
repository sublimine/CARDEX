"""
vroom.be — Belgium, Rossel/Roularta mobility platform (~22k FR listings).

Discovery via the **listing-level sitemap** rather than SSR HTML pagination.
The previous brand-pager was doubly broken: the base path
`/fr/voitures-occasion/{brand}` returns HTTP 410 Gone, and the regex expected a
three-segment `/{brand}/{model}/{slug}` form while the real detail URL is a single
flat `{slug}-{id}`. The sitemap lists every detail URL directly.

Route [VERIFIED 2026-06-06]:
  Index   https://www.vroom.be/sitemap_index.xml  (<sitemapindex>, 112 children)
  Cars    `…/sitemaps/listings-fr-0001.xml` … `-0022.xml` (FR only — the
          listings-nl-* shards are the same inventory in Dutch). CHILD_RE keeps FR.
  Detail  https://www.vroom.be/fr/voitures-occasion/<slug>-<id>
          (note: voitures with an 's'; 22 shards × 1,000 ≈ 22k vehicles).
  WAF     none. Tier.T1.
"""
from __future__ import annotations

import re

from scrapers.portals.sitemap_listing_base import SitemapListingScraper


class VroomBEScraper(SitemapListingScraper):
    """vroom.be FR vehicles via the listing sitemap (T1)."""

    DOMAIN = "vroom.be"
    COUNTRY = "BE"

    SITEMAP_URL = "https://www.vroom.be/sitemap_index.xml"
    CHILD_RE = re.compile(r"/listings-fr-")          # FR listing shards only
    DETAIL_RE = re.compile(r"/fr/voitures-occasion/")
