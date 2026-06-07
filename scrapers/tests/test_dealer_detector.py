"""
Dealer web-type detector — probe a domain → ExtractionConfig, no network/browser.

Every async path runs against an in-memory ``MapFetcher`` (URL → response), the
repo convention, so the four real strategies (sitemap / wp / catalog / E07-render)
and the negative cases (dead dealer, SSRF) are covered deterministically. Detail
fixtures reuse the JSON-LD + SEO-meta shapes proven in test_generic_extractor and
test_playwright_extractor — nothing invented.
"""
from __future__ import annotations

import asyncio

import pytest

from scrapers.dealer_scraping import detector as det
from scrapers.dealer_scraping.detector import (
    DetectionResult,
    build_config,
    detect_spa_markers,
    detect_web_type,
    extract_listing_links,
    find_catalog_url,
)
from scrapers.pipeline.generic_extractor import FetchResult


# ── in-memory transport (mirrors test_generic_extractor.MapFetcher) ─────────────
class MapFetcher:
    def __init__(self, pages: dict[str, tuple[int, bytes]], *, fail_urls=()):
        self._pages = pages
        self._fail = set(fail_urls)
        self.requested: list[str] = []

    async def __call__(self, url: str) -> FetchResult:
        self.requested.append(url)
        if url in self._fail:
            raise ConnectionError("simulated transport fault")
        if url in self._pages:
            status, body = self._pages[url]
            return FetchResult(url=url, status_code=status, body=body)
        return FetchResult(url=url, status_code=404, body=b"")


def _b(text: str) -> bytes:
    return text.encode("utf-8")


def _run(coro):
    return asyncio.run(coro)


_PAD = "<div class='spec'><span></span></div>" * 600


def _jsonld_detail(make="BMW", model="320d", year="2019", price="24900") -> bytes:
    return _b(
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Car",'
        f'"brand":{{"name":"{make}"}},"model":"{model}","vehicleModelDate":"{year}",'
        '"mileageFromOdometer":{"value":"85000"},"fuelType":"Diesel",'
        '"image":["https://cdn.d.example/1.jpg"],'
        f'"offers":{{"@type":"Offer","price":"{price}","priceCurrency":"EUR"}}}}'
        "</script></head><body>" + _PAD + "</body></html>"
    )


# A rendered SPA page that carries the vehicle ONLY in SEO meta (autolina shape).
_META_DETAIL = _b(
    "<html><head>"
    '<meta property="og:title" content="SKODA Kamiq 1.5 TSI gebraucht für CHF 29\'500 auf X">'
    '<meta name="description" content="SKODA Kamiq 1.5 TSI - Benzin, Automatik, '
    "Kilometer: 10'600 km, Preis: CHF 29'500, Erstzulassung: 01.09.2025, Farbe: Silber\">"
    '<meta property="og:image" content="https://cdn.x.ch/4997584.jpg">'
    "</head><body>" + _PAD + "</body></html>"
)

# SPA shell: a framework marker, no server-rendered vehicle data.
_SPA_SHELL = _b('<html><head><title>Garage</title></head><body><div id="__next"></div>'
                "<script>window.__NUXT__={}</script></body></html>")
_EMPTY = _b("<html><body>Welcome to our family dealership.</body></html>")


# ── pure helpers ────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_detect_spa_markers():
    assert "next" in detect_spa_markers('<div id="__next"></div>')
    assert "nuxt" in detect_spa_markers("window.__NUXT__={}")
    assert detect_spa_markers("<html><body>static dealer</body></html>") == ()


@pytest.mark.unit
def test_extract_listing_links_same_site_vehicle_only():
    html = (
        '<a href="/vehicles/bmw-320d-1">car</a>'
        '<a href="/about-us">about</a>'
        '<a href="https://othersite.com/vehicles/x-2">offsite</a>'
        '<a href="https://stock.dealer.example/voiture/audi-a4-3">sub</a>'
        '<a href="/">home</a>'
    )
    links = extract_listing_links(html, "https://dealer.example")
    assert links == [
        "https://dealer.example/vehicles/bmw-320d-1",
        "https://stock.dealer.example/voiture/audi-a4-3",
    ]


@pytest.mark.unit
def test_find_catalog_url():
    html = '<a href="/over-ons">x</a><a href="/occasions/voorraad">stock</a>'
    assert find_catalog_url(html, "https://dealer.example") == "https://dealer.example/occasions/voorraad"
    assert find_catalog_url('<a href="/contact">c</a>', "https://dealer.example") is None


@pytest.mark.unit
def test_build_config_none_when_not_yielding():
    r = DetectionResult("x.de", "DE", "none", False, "none", 0)
    assert build_config(r) is None


@pytest.mark.unit
def test_build_config_from_positive_detection():
    r = DetectionResult(
        domain="autohaus-bahm.de", country="de", strategy="sitemap_listing",
        yields_inventory=True, discovery="sitemap", discovered=12,
        sitemap_url="https://autohaus-bahm.de/sitemap.xml",
    )
    cfg = build_config(r)
    assert cfg is not None
    assert cfg.source_key == "autohaus-bahm.de" and cfg.country == "DE"
    assert cfg.strategy == "sitemap_listing"
    assert cfg.drift_baseline.expected_min_volume == 12
    assert cfg.endpoints.sitemap_url == "https://autohaus-bahm.de/sitemap.xml"


@pytest.mark.unit
def test_build_config_e07_uses_meta_method():
    r = DetectionResult("spa.ch", "CH", "playwright_meta", True, "sitemap", 4)
    cfg = build_config(r)
    assert cfg.strategy == "playwright_meta"
    assert cfg.extraction.method == "og"
    assert cfg.drift_baseline.extraction_method == "og"


# ── full probe: the four strategies + negatives ─────────────────────────────────
def _sitemap_pages(detail_body: bytes) -> dict[str, tuple[int, bytes]]:
    sm = (
        "<urlset>"
        "<url><loc>https://dealer.example/vehicles/bmw-320d-1</loc></url>"
        "<url><loc>https://dealer.example/vehicles/audi-a4-2</loc></url>"
        "</urlset>"
    )
    return {
        "https://dealer.example/robots.txt": (200, _b("Sitemap: https://dealer.example/sitemap.xml")),
        "https://dealer.example/sitemap.xml": (200, _b(sm)),
        "https://dealer.example/vehicles/bmw-320d-1": (200, detail_body),
        "https://dealer.example/vehicles/audi-a4-2": (200, detail_body),
    }


@pytest.mark.unit
def test_detect_sitemap_static_dealer():
    fetcher = MapFetcher(_sitemap_pages(_jsonld_detail()))
    r = _run(detect_web_type("dealer.example", country="de", static_fetcher=fetcher))
    assert r.ok and r.strategy == "sitemap_listing"
    assert r.discovery == "sitemap" and r.discovered == 2
    assert r.proof and r.proof["make"] == "BMW"
    assert build_config(r).strategy == "sitemap_listing"


@pytest.mark.unit
def test_detect_wp_dealer():
    types = '{"page":{"slug":"page"},"vehicle":{"slug":"vehicle"}}'
    items = '[{"id":1,"link":"https://wp.example/vehicle/audi-a4-9"}]'
    pages = {
        "https://wp.example/wp-json/": (200, _b('{"name":"WP"}')),
        "https://wp.example/wp-json/wp/v2/types": (200, _b(types)),
        "https://wp.example/wp-json/wp/v2/vehicle?per_page=100&page=1": (200, _b(items)),
        "https://wp.example/vehicle/audi-a4-9": (200, _jsonld_detail(make="Audi", model="A4")),
    }
    r = _run(detect_web_type("wp.example", country="de", static_fetcher=MapFetcher(pages)))
    assert r.ok and r.strategy == "wp_rest" and r.discovery == "wp_rest"
    assert r.proof["make"] == "Audi"


@pytest.mark.unit
def test_detect_catalog_links_dealer():
    home = (
        '<html><head><title>Garage Busato</title></head><body>'
        '<a href="/vehicules/clio-1">v1</a><a href="/contact">c</a>'
        "</body></html>"
    )
    pages = {
        "https://busato.fr": (200, _b(home)),
        "https://busato.fr/vehicules/clio-1": (200, _jsonld_detail(make="Renault", model="Clio")),
    }
    r = _run(detect_web_type("busato.fr", country="fr", static_fetcher=MapFetcher(pages)))
    assert r.ok and r.strategy == "jsonld_detail" and r.discovery == "catalog"
    assert r.proof["make"] == "Renault"


@pytest.mark.unit
def test_detect_spa_dealer_needs_e07():
    # Static discovery finds URLs (sitemap) but detail pages are SPA shells: static
    # extraction is empty, so the verdict must be playwright_meta via the e07 fetcher.
    static = MapFetcher({
        **_sitemap_pages(_SPA_SHELL),
        "https://dealer.example": (200, _SPA_SHELL),
    })
    e07 = MapFetcher({
        "https://dealer.example/vehicles/bmw-320d-1": (200, _META_DETAIL),
        "https://dealer.example/vehicles/audi-a4-2": (200, _META_DETAIL),
    })
    r = _run(detect_web_type("dealer.example", country="ch", static_fetcher=static, e07_fetcher=e07))
    assert r.ok and r.strategy == "playwright_meta"
    assert "next" in r.spa_markers or "nuxt" in r.spa_markers
    assert r.proof["make"] == "SKODA"


@pytest.mark.unit
def test_detect_spa_dealer_without_e07_is_none():
    # Same SPA, but no browser available → honest "none", not a false static config.
    static = MapFetcher({**_sitemap_pages(_SPA_SHELL), "https://dealer.example": (200, _SPA_SHELL)})
    r = _run(detect_web_type("dealer.example", country="ch", static_fetcher=static))
    assert not r.ok and r.strategy == "none"
    assert build_config(r) is None


@pytest.mark.unit
def test_detect_dead_dealer_yields_none():
    fetcher = MapFetcher({"https://dead.de": (200, _EMPTY)})  # no sitemap, no wp, no links
    r = _run(detect_web_type("dead.de", country="de", static_fetcher=fetcher))
    assert not r.ok and r.strategy == "none" and r.discovered == 0


@pytest.mark.unit
def test_detect_ssrf_blocked_domain():
    # A domain that is an internal IP literal must never be probed.
    fetcher = MapFetcher({})
    r = _run(detect_web_type("169.254.169.254", country="de", static_fetcher=fetcher))
    assert not r.ok and r.notes == ("ssrf_blocked",)
    assert fetcher.requested == []  # nothing was fetched
