"""
Pure detection helpers (no I/O) — shared by the detector and the discovery layer.

Kept in a leaf module so ``discovery`` (which catalog-follows) and ``detector`` (which
decides the strategy) both import them without a cycle. Every function is pure HTML→data
and unit-testable without a network or a browser.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from scrapers.common.net_guard import is_safe_public_url
from scrapers.pipeline.delta import is_deep_link
from scrapers.pipeline.generic_extractor import _host, _origin, _same_site, looks_like_listing

_HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.I)

# SPA framework fingerprints in raw (pre-render) HTML — their presence means the
# static cascade will likely see an empty shell and a browser render is warranted.
_SPA_MARKERS: tuple[tuple[str, str], ...] = (
    ("__NEXT_DATA__", "next"),
    ('id="__next"', "next"),
    ("window.__NUXT__", "nuxt"),
    ("__NUXT__", "nuxt"),
    ("data-server-rendered", "vue"),
    ("data-reactroot", "react"),
    ('id="root"', "react-root"),
    ("ng-version", "angular"),
    ("window.__INITIAL_STATE__", "spa-state"),
)

# Catalog/stock path tokens across DE/FR/ES/NL/IT/EN — used to find the page that
# lists a dealer's inventory when there is no vehicle sitemap.
_CATALOG_PATH_TOKENS: tuple[str, ...] = (
    "occasion", "occasions", "aanbod", "ons-aanbod", "voorraad", "stock",
    "gebrauchtwagen", "fahrzeuge", "fahrzeugbestand", "fahrzeugsuche", "fahrzeug",
    "vehicules", "vehicule", "vehicles", "vehicle", "coches", "ocasion",
    "segunda-mano", "used-cars", "usados", "inventory", "bestand", "showroom",
    "auto-occasion", "occasioni", "veicoli", "parc-auto", "auto-finder", "angebote",
    "neufahrzeuge", "voitures-occasion", "nos-vehicules", "auto-s",
)


def detect_spa_markers(html: str) -> tuple[str, ...]:
    """Framework hints present in raw HTML (deduped, order-stable)."""
    found: list[str] = []
    for token, name in _SPA_MARKERS:
        if token in html and name not in found:
            found.append(name)
    return tuple(found)


def extract_listing_links(html: str, base_url: str, *, max_urls: int = 150) -> list[str]:
    """
    Same-site, deep-link, vehicle-token URLs from any page (homepage or catalog).

    The static fallback for dealers with no vehicle sitemap: small dealers render their
    whole stock as links on one page. SSRF-guarded (hostile markup can point off-host).
    """
    origin = _origin(base_url)
    base_host = _host(base_url)
    out: list[str] = []
    seen: set[str] = set()
    for m in _HREF_RE.finditer(html):
        absolute = urljoin(origin + "/", m.group(1).strip())
        if absolute in seen:
            continue
        seen.add(absolute)
        if (
            is_safe_public_url(absolute)
            and _same_site(absolute, base_host)
            and looks_like_listing(absolute)
            and is_deep_link(absolute)
        ):
            out.append(absolute)
            if len(out) >= max_urls:
                break
    return out


def find_catalog_url(html: str, base_url: str) -> str | None:
    """First same-site link whose path names a catalog/stock surface, else None."""
    origin = _origin(base_url)
    base_host = _host(base_url)
    for m in _HREF_RE.finditer(html):
        absolute = urljoin(origin + "/", m.group(1).strip())
        if not (is_safe_public_url(absolute) and _same_site(absolute, base_host)):
            continue
        path = urlparse(absolute).path.lower()
        if any(tok in path for tok in _CATALOG_PATH_TOKENS):
            return absolute
    return None


# Third-party DMS / inventory-widget provider host fragments. When a dealer EMBEDS
# its stock from one of these (iframe / script / data-src), the vehicles live on the
# provider's domain, not the dealer's — so on-domain scraping yields nothing and the
# dealer is classified ``embedded_dms`` (a backlog item: harvest the provider feed).
_DMS_PROVIDERS: tuple[str, ...] = (
    "modix", "mobile.de", "autoscout24", "dealerk", "planetvo", "autinity",
    "gw-trends", "api4automotive", "autralis", "wirsol", "automanager",
    "dealer.com", "incadea", "fahrzeugmarkt", "am.cms", "carworld", "leadmanager",
    "pixelconcept", "autostadt", "intercar", "pixel-base", "sprinto",
)
_SRC_RE = re.compile(r'(?:src|data-src)\s*=\s*["\']([^"\']+)["\']', re.I)


def detect_embedded_dms(html: str) -> str | None:
    """The DMS provider a page embeds its inventory from (iframe/script host), or None."""
    for m in _SRC_RE.finditer(html):
        src = m.group(1)
        host = urlparse(src if "://" in src else f"https://{src}").netloc.lower()
        for provider in _DMS_PROVIDERS:
            if provider in host:
                return provider
    return None


def classify_non_yield(home_html: str, detail_urls, spa_markers) -> str:
    """A by-cause label for a dealer that did not yield, for honest measurement."""
    dms = detect_embedded_dms(home_html) if home_html else None
    if dms:
        return f"embedded_dms:{dms}"
    if not home_html:
        return "unreachable"          # 4xx/5xx/transport — datacenter-IP block or down
    if not detail_urls:
        return "no_inventory_links"   # real page, but no on-domain vehicle URLs found
    if spa_markers:
        return "spa_shell"            # SPA whose details did not expose extractable data
    return "details_no_fields"        # found URLs but they carry no parseable vehicle
