"""
Autocasión Spain — autocasion.com. T1 (curl_cffi chrome passes CF-free, no challenge).

[VERIFIED 2026-06-03 against live HTML via curl_cffi impersonate="chrome"]

Search surface (category page; the site's own verified pager href):
    page 1:  https://www.autocasion.com/coches-segunda-mano/{cat}-ocasion
    page N≥2: …/{cat}-ocasion?page={N}     (bare URL on page 1 — no ?page=1;
              audi observed up to ?page=331)

Detail links in the search HTML: /coches-segunda-mano/{cat}/{slug}-ref{id},
    canonical https://www.autocasion.com{path}. Two path segments + `-ref{id}`
    distinguishes a detail link from the single-segment `{cat}-ocasion` category.

Segment universe (leaf urlset, verified end of the sitemap chain
    uploads/sitemap.xml → index-coches-segunda-mano.xml → this leaf):
    https://www.autocasion.com/uploads/sitemap-ng/coches-segunda-mano/coches-segunda-mano.xml
    (30386 category locs `/coches-segunda-mano/{cat}-ocasion`, with dupes →
     deduped by the base). Categories are already fine-grained (brand+model), so
     no further subdivision is needed; cross-category overlap is deduped by the
     base `seen` set.
"""
from __future__ import annotations

import re
from typing import Any

from scrapers.portals.html_search_base import HtmlSearchScraper

# /coches-segunda-mano/{cat}-ocasion at the URL tail. cat may contain hyphens;
# the literal `-ocasion` suffix backtracks out of the greedy capture.
_CATEGORY_LOC_RE: re.Pattern[str] = re.compile(
    r"/coches-segunda-mano/([a-z0-9-]+)-ocasion/?$", re.IGNORECASE
)


class AutocasionES(HtmlSearchScraper):
    DOMAIN = "autocasion.com"
    COUNTRY = "ES"
    HOST = "www.autocasion.com"
    SITEMAP_URL = (
        "https://www.autocasion.com/uploads/sitemap-ng/"
        "coches-segunda-mano/coches-segunda-mano.xml"
    )
    DETAIL_RE = re.compile(r"/coches-segunda-mano/[a-z0-9-]+/[a-z0-9-]+-ref\d+")
    PAGE_SIZE = 25

    def _build_url(self, params: dict[str, Any], page_num: int) -> str:
        base = f"https://{self.HOST}/coches-segunda-mano/{params['category']}-ocasion"
        if page_num <= 1:
            return base
        return f"{base}?page={page_num}"

    def _loc_to_segment(self, loc: str) -> dict[str, Any] | None:
        match = _CATEGORY_LOC_RE.search(loc)
        if not match:
            return None
        return {"category": match.group(1).lower()}
