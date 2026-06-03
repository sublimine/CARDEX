"""
AutoTrack Netherlands — autotrack.nl. T1 (curl_cffi chrome, WAF.NONE).

[VERIFIED 2026-06-03 against live HTML via curl_cffi impersonate="chrome"]

Search surface (the site's own canonical pager — NOT an assumed ?page=N):
    https://www.autotrack.nl/aanbod
        ?data.merkModel.filter.0.slug={brand}
        &pageNumber={N}            (1-based; p1/p2/p3 = 30 fresh ids each)
        &pageSize=30
        &sortField=relevance&sortOrder=asc
    brand+model adds: &data.merkModel.filter.0.models.0.slug={model}
    (VW alone = 23172 results / 773 pages — the query API is the real surface;
     the /auto/{brand} pages are JS-driven and yield no paginated HTML.)

Detail links in the search HTML: /a/{slug}-{id}  (id ≥ 5 digits), canonical
    https://www.autotrack.nl/a/{slug}-{id}  (query string stripped by the regex).

Segment universe: https://www.autotrack.nl/sitemap_brand_model_auto.xml
    (urlset, 994 locs: /auto/{brand} brand pages + /auto/{brand}/{model}). Brand
    locs become brand segments; model locs only enrich the subdivision map so a
    brand segment that hits the 20-page cap subdivides into brand+model.
"""
from __future__ import annotations

import re
from typing import Any

from scrapers.portals.html_search_base import HtmlSearchScraper

# /auto/{brand} or /auto/{brand}/{model}, anchored at the URL tail.
_AUTO_LOC_RE: re.Pattern[str] = re.compile(
    r"/auto/([a-z0-9-]+)(?:/([a-z0-9-]+))?/?$", re.IGNORECASE
)


class AutotrackNL(HtmlSearchScraper):
    DOMAIN = "autotrack.nl"
    COUNTRY = "NL"
    HOST = "www.autotrack.nl"
    SITEMAP_URL = "https://www.autotrack.nl/sitemap_brand_model_auto.xml"
    DETAIL_RE = re.compile(r"/a/[a-z0-9-]+-\d{5,}")
    PAGE_SIZE = 30

    def __init__(self, segments: list[dict[str, Any]] | None = None) -> None:
        super().__init__(segments)
        # brand → [model, ...], built as a side-effect of parsing the sitemap.
        self._brand_models: dict[str, list[str]] = {}

    def _build_url(self, params: dict[str, Any], page_num: int) -> str:
        url = (
            f"https://{self.HOST}/aanbod"
            f"?data.merkModel.filter.0.slug={params['brand']}"
            f"&pageNumber={page_num}&pageSize={self.PAGE_SIZE}"
            f"&sortField=relevance&sortOrder=asc"
        )
        model = params.get("model")
        if model:
            url += f"&data.merkModel.filter.0.models.0.slug={model}"
        return url

    def _loc_to_segment(self, loc: str) -> dict[str, Any] | None:
        match = _AUTO_LOC_RE.search(loc)
        if not match:
            return None
        brand = match.group(1).lower()
        model = match.group(2)
        if model:
            # Model locs only feed the subdivision map; they are not segments.
            models = self._brand_models.setdefault(brand, [])
            model = model.lower()
            if model not in models:
                models.append(model)
            return None
        return {"brand": brand}

    def subdivide_segment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """A capped brand segment splits by model; a model segment cannot split further."""
        if params.get("model"):
            return []
        brand = params.get("brand", "")
        return [{"brand": brand, "model": m} for m in self._brand_models.get(brand, [])]
