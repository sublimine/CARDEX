"""
Dealer detail-URL discovery with catalog-follow — the fix for "the sitemap points at
the catalog, not the cars". In-memory fetchers, no network/browser.
"""
from __future__ import annotations

import asyncio

import pytest

from scrapers.dealer_scraping.discovery import (
    discover_detail_urls,
    expand_catalogs,
    looks_like_detail,
    split_details_and_catalogs,
)
from scrapers.pipeline.generic_extractor import FetchResult


class MapFetcher:
    def __init__(self, pages: dict[str, tuple[int, bytes]]):
        self._pages = pages
        self.requested: list[str] = []

    async def __call__(self, url: str) -> FetchResult:
        self.requested.append(url)
        if url in self._pages:
            status, body = self._pages[url]
            return FetchResult(url=url, status_code=status, body=body)
        return FetchResult(url=url, status_code=404, body=b"")


def _b(t: str) -> bytes:
    return t.encode("utf-8")


def _run(coro):
    return asyncio.run(coro)


@pytest.mark.unit
@pytest.mark.parametrize("url,expected", [
    ("https://d.de/fahrzeuge", False),                       # index — no id
    ("https://d.de/occasion", False),
    ("https://d.de/fahrzeug/12345", True),                   # numeric id
    ("https://d.de/vehicles/bmw-320d-1", True),              # slug + id
    ("https://d.de/voiture/renault-clio-occasion", True),    # deep multi-token slug
    ("https://d.de/", False),
])
def test_looks_like_detail(url, expected):
    assert looks_like_detail(url) is expected


@pytest.mark.unit
def test_split_details_and_catalogs():
    urls = ["https://d.de/fahrzeuge", "https://d.de/fahrzeug/99", "https://d.de/stock"]
    details, catalogs = split_details_and_catalogs(urls)
    assert details == ["https://d.de/fahrzeug/99"]
    assert catalogs == ["https://d.de/fahrzeuge", "https://d.de/stock"]


@pytest.mark.unit
def test_expand_catalogs_pulls_inner_detail_links():
    catalog = "https://d.de/fahrzeuge"
    page = (
        '<a href="/fahrzeug/bmw-320d-12345">a</a>'
        '<a href="/fahrzeug/audi-a4-67890">b</a>'
        '<a href="/impressum">x</a>'
        '<a href="/fahrzeuge">self</a>'
    )
    fetcher = MapFetcher({catalog: (200, _b(page))})
    out = _run(expand_catalogs([catalog], fetcher, domain="d.de", cap=50, max_expand=4))
    assert out == [
        "https://d.de/fahrzeug/bmw-320d-12345",
        "https://d.de/fahrzeug/audi-a4-67890",
    ]


@pytest.mark.unit
def test_discover_detail_urls_sitemap_direct():
    sm = ("<urlset>"
          "<url><loc>https://d.de/fahrzeug/bmw-320d-12345</loc></url>"
          "<url><loc>https://d.de/fahrzeug/audi-a4-67890</loc></url></urlset>")
    pages = {
        "https://d.de/robots.txt": (200, _b("Sitemap: https://d.de/sitemap.xml")),
        "https://d.de/sitemap.xml": (200, _b(sm)),
    }
    details, method, _home, _cat = _run(
        discover_detail_urls("d.de", static_fetcher=MapFetcher(pages))
    )
    assert method == "sitemap"
    assert details == ["https://d.de/fahrzeug/bmw-320d-12345", "https://d.de/fahrzeug/audi-a4-67890"]


@pytest.mark.unit
def test_discover_detail_urls_catalog_follow():
    # Sitemap points ONLY at the catalog index; the details are linked from it.
    sm = "<urlset><url><loc>https://d.de/fahrzeuge</loc></url></urlset>"
    catalog_html = (
        '<a href="/fahrzeug/bmw-320d-12345">a</a><a href="/fahrzeug/audi-a4-67890">b</a>'
    )
    pages = {
        "https://d.de/robots.txt": (200, _b("Sitemap: https://d.de/sitemap.xml")),
        "https://d.de/sitemap.xml": (200, _b(sm)),
        "https://d.de/fahrzeuge": (200, _b(catalog_html)),
    }
    details, method, _home, _cat = _run(
        discover_detail_urls("d.de", static_fetcher=MapFetcher(pages))
    )
    assert method == "catalog_follow"
    assert details == [
        "https://d.de/fahrzeug/bmw-320d-12345",
        "https://d.de/fahrzeug/audi-a4-67890",
    ]


@pytest.mark.unit
def test_discover_detail_urls_merges_homepage_detail_links():
    # The sitemap lists only a catalog/nav page, but the homepage links a real detail
    # (deep slug + id). The merge must surface that detail (the probe filters non-cars).
    sm = "<urlset><url><loc>https://d.nl/occasion</loc></url></urlset>"
    home = ('<html><body><a href="/occasion/ford-transit-custom-54008980">stock</a>'
            '<a href="/over-ons">about</a></body></html>')
    pages = {
        "https://d.nl": (200, _b(home)),
        "https://d.nl/robots.txt": (200, _b("Sitemap: https://d.nl/sitemap.xml")),
        "https://d.nl/sitemap.xml": (200, _b(sm)),
        "https://d.nl/occasion": (200, _b("<html><body>no inner links</body></html>")),
    }
    details, _method, _home, _cat = _run(discover_detail_urls("d.nl", static_fetcher=MapFetcher(pages)))
    assert "https://d.nl/occasion/ford-transit-custom-54008980" in details


@pytest.mark.unit
def test_discover_detail_urls_ssrf_blocked():
    # A domain that is an internal IP literal must never be fetched.
    fetcher = MapFetcher({})
    details, method, home, cat = _run(discover_detail_urls("169.254.169.254", static_fetcher=fetcher))
    assert details == [] and method == "ssrf_blocked"
    assert fetcher.requested == []


@pytest.mark.unit
def test_discover_detail_urls_render_follow():
    # No static sitemap/wp/links; the catalog grid is painted client-side. The static
    # catalog page has no links, but the RENDERED page does → render_follow.
    home = '<html><body><a href="/fahrzeuge">stock</a></body></html>'
    static = MapFetcher({
        "https://d.de": (200, _b(home)),
        "https://d.de/fahrzeuge": (200, _b("<html><body><div id=app></div></body></html>")),
    })
    rendered = '<a href="/fahrzeug/bmw-320d-12345">a</a>'
    e07 = MapFetcher({"https://d.de/fahrzeuge": (200, _b(rendered))})
    details, method, _home, cat = _run(
        discover_detail_urls("d.de", static_fetcher=static, e07_fetcher=e07)
    )
    assert method == "render_follow"
    assert details == ["https://d.de/fahrzeug/bmw-320d-12345"]
    assert cat == "https://d.de/fahrzeuge"
