"""
Dealer detail-URL discovery with catalog-follow (frente C).

Real dealer sites rarely list every vehicle's detail page in a sitemap. The common
shape is: a sitemap/menu points at a CATALOG/stock index (``/fahrzeuge``,
``/auto-finder``, ``/occasions``) and the individual vehicle detail pages are linked
FROM that index. Naive discovery stops at the catalog and extracts nothing (the index
is not a single vehicle). This module follows the catalog one level down to the real
detail URLs, statically first and — when the index paints its grid client-side — via
a browser render.

Layered, cheapest-first, bounded at every step:

  sitemap → wp-rest → homepage links → catalog page → (catalog-follow) → render-follow

Returns DETAIL urls (best-effort) so detection and harvest both probe real listings.
Every off-host / IP-literal URL is SSRF-rejected (untrusted dealer markup).
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from scrapers.common.net_guard import is_safe_public_url
from scrapers.dealer_scraping.detector_helpers import extract_listing_links, find_catalog_url
from scrapers.pipeline.generic_extractor import (
    Fetcher,
    _host,
    _safe_fetch,
    discover_sitemap_listings,
    discover_wp_listings,
)

log = logging.getLogger(__name__)

DISCOVERY_CAP = 150
MAX_CATALOG_EXPAND = 4       # catalog pages followed for inner detail links
MAX_RENDER_EXPAND = 2        # catalog pages RENDERED when static follow is empty (RAM)

# A detail page usually carries an id/slug: a 2+ digit run in the last path segment,
# or a path deeper than a single index segment. ``/fahrzeuge`` (index) → False;
# ``/fahrzeug/12345`` or ``/vehicles/bmw-320d-1`` (detail) → True.
_ID_IN_SEG_RE = re.compile(r"\d{2,}")


def looks_like_detail(url: str) -> bool:
    """Heuristic: True for a single-vehicle detail URL, False for a catalog index."""
    path = urlparse(url).path.strip("/")
    if not path:
        return False
    segs = path.split("/")
    last = segs[-1]
    if _ID_IN_SEG_RE.search(last):
        return True
    # A slug with multiple hyphen-separated tokens in a deep path is detail-shaped.
    return len(segs) >= 2 and ("-" in last)


def split_details_and_catalogs(urls: list[str]) -> tuple[list[str], list[str]]:
    """Partition candidate URLs into (likely-detail, likely-catalog-index)."""
    details = [u for u in urls if looks_like_detail(u)]
    catalogs = [u for u in urls if not looks_like_detail(u)]
    return details, catalogs


async def expand_catalogs(
    catalogs: list[str],
    fetcher: Fetcher,
    *,
    domain: str,
    cap: int,
    max_expand: int,
) -> list[str]:
    """Fetch each catalog index and pull its inner same-site detail links (bounded)."""
    out: list[str] = []
    seen: set[str] = set()
    for cat in catalogs[:max_expand]:
        # Defense-in-depth: upstream paths already SSRF-guard their URLs, but never
        # fetch a catalog URL without re-checking it at this call site.
        if not is_safe_public_url(cat):
            continue
        page = await _safe_fetch(fetcher, cat)
        if page is None or page.status_code != 200:
            continue
        for v in extract_listing_links(page.text, cat, max_urls=cap):
            if v != cat and v not in seen:
                seen.add(v)
                out.append(v)
                if len(out) >= cap:
                    return out
    return out


async def discover_detail_urls(
    domain: str,
    *,
    static_fetcher: Fetcher,
    e07_fetcher: Fetcher | None = None,
    cap: int = DISCOVERY_CAP,
) -> tuple[list[str], str, str, str]:
    """
    Discover a dealer's VEHICLE DETAIL urls, following catalogs as needed.

    Returns ``(detail_urls, method, home_html, catalog_url)``. ``method`` names how the
    surface was found (sitemap | wp_rest | catalog | catalog_follow | render_follow |
    none). ``home_html`` is returned so the caller reuses one homepage fetch (SPA-marker
    detection). Bounded by ``cap`` and the expand limits so no dealer runs unbounded.
    """
    base = f"https://{domain}"
    base_host = _host(base)

    # SSRF: ``domain`` comes from discovery_candidates (external registries) — never
    # fetch a domain that resolves to an IP literal / internal name. The downstream
    # detail/catalog URLs are same-site-guarded by extract_listing_links / the sitemap
    # walker, but the base homepage + wp-json fetch here must be guarded too.
    if not is_safe_public_url(base):
        return [], "ssrf_blocked", "", ""

    # one homepage fetch, reused by the caller for SPA-marker detection
    home = await _safe_fetch(static_fetcher, base)
    home_html = home.text if (home is not None and home.status_code == 200) else ""
    catalog_url = find_catalog_url(home_html, base) if home_html else None

    # Layer 1/2: static sitemap, then WordPress REST
    candidates = await discover_sitemap_listings(base, static_fetcher, max_urls=cap)
    method = "sitemap" if candidates else ""
    if not candidates:
        candidates = await discover_wp_listings(base, static_fetcher, max_urls=cap)
        method = "wp_rest" if candidates else ""

    # Layer 3: homepage links, then the catalog page's links
    if not candidates and home_html:
        candidates = extract_listing_links(home_html, base, max_urls=cap)
        if not candidates and catalog_url:
            cat = await _safe_fetch(static_fetcher, catalog_url)
            if cat is not None and cat.status_code == 200:
                candidates = extract_listing_links(cat.text, catalog_url, max_urls=cap)
        if candidates:
            method = "catalog"

    details, catalogs = split_details_and_catalogs(candidates)
    had_direct_details = bool(details)

    # 1. Catalog-follow (static): the candidates may be index pages — expand to details.
    if len(details) < cap and catalogs:
        expanded = await expand_catalogs(
            catalogs, static_fetcher, domain=base_host, cap=cap, max_expand=MAX_CATALOG_EXPAND
        )
        if expanded:
            details = list(dict.fromkeys(details + expanded))
            if not had_direct_details:
                method = "catalog_follow"

    # 2. Render-follow: a JS catalog paints its grid client-side — render the index and
    # pull the now-present detail links (bounded; the OOM-safe browser is reused). Runs
    # only while we still have NO real detail URLs, so it never costs a render needlessly.
    if not details and e07_fetcher is not None:
        if catalog_url:
            render_targets = [catalog_url]
        elif catalogs:
            render_targets = catalogs[:MAX_RENDER_EXPAND]
        else:
            render_targets = [base]
        rendered_details: list[str] = []
        for tgt in render_targets[:MAX_RENDER_EXPAND]:
            r = await _safe_fetch(e07_fetcher, tgt)
            if r is not None and r.status_code == 200:
                rendered_details.extend(extract_listing_links(r.text, tgt, max_urls=cap))
        rendered_details = list(dict.fromkeys(rendered_details))
        if rendered_details:
            details = rendered_details
            method = "render_follow"

    # 3. Last resort: treat a catalog index itself as the surface (the probe decides if
    # the index entry carries a vehicle); only when nothing better was found.
    if not details and catalogs:
        details = catalogs

    return details[:cap], (method or "none"), home_html, (catalog_url or "")
