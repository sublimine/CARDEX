"""
Generic dealer extractor tests — discovery + extraction, no network or browser.

The whole module is exercised against an in-memory `MapFetcher` (URL → response)
so every async path runs synchronously via `asyncio.run`, matching the repo's
test convention. Coverage:

  * pure helpers      _origin/_host/_same_site, looks_like_listing,
                      parse_sitemap_locs, is_sitemap_index, looks_like_sitemap,
                      decode_sitemap (plain + gzip)
  * sitemap discovery robots.txt precedence, <sitemapindex> recursion, listing
                      filter, same-site guard, max_urls bound
  * WordPress discovery CPT filtering, pagination, non-WP short-circuit
  * union strategy    sitemap preferred, WP fallback only when sitemap empty
  * extract_listing   ok + every reject reason (fetch_error / http_404 /
                      no_fields / missing_critical / quality failure)
  * extract_dealer    end-to-end real VehicleRecords, explicit-urls bypass

Detail fixtures are markup-heavy and >15 KB so the poison gate (GATE 2) sees a
realistic listing and never trips `tiny_html`/`text_code_ratio` on a clean page.
"""
from __future__ import annotations

import asyncio
import gzip
from decimal import Decimal

import pytest

from scrapers.pipeline import generic_extractor as gx
from scrapers.pipeline.generic_extractor import FetchResult


# ── in-memory transport ─────────────────────────────────────────────────────
class MapFetcher:
    """A Fetcher backed by a URL→(status, body) map; unknown URLs return 404."""

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


# Markup-heavy padding (~22 KB, ~zero visible text) keeps detail pages above the
# 15 KB poison floor with a low text/code ratio — a real listing page's shape.
_PAD = "<div class='spec'><span></span></div>" * 600


def _detail_html(
    *,
    make: str = "BMW",
    model: str = "320d",
    year: str = "2019",
    price: str = "24900",
    vin: str = "WBA8E9G50GNT12345",
    images=("https://cdn.dealer-cdn.de/1.jpg", "https://cdn.dealer-cdn.de/2.jpg"),
) -> bytes:
    img_json = ",".join(f'"{u}"' for u in images)
    return _b(
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Car",'
        f'"brand":{{"name":"{make}"}},"model":"{model}",'
        f'"vehicleModelDate":"{year}",'
        '"mileageFromOdometer":{"value":"85000"},"fuelType":"Diesel",'
        '"vehicleTransmission":"Automatic","color":"black",'
        f'"vehicleIdentificationNumber":"{vin}",'
        f'"image":[{img_json}],'
        f'"offers":{{"@type":"Offer","price":"{price}","priceCurrency":"EUR"}}}}'
        "</script></head><body>" + _PAD + "</body></html>"
    )


# Partial JSON-LD: make+model only → fails has_critical_fields (no year/price/img).
_PARTIAL_HTML = _b(
    '<script type="application/ld+json">'
    '{"@context":"https://schema.org","@type":"Car",'
    '"brand":{"name":"BMW"},"model":"320d"}</script>'
)

# No structured data and no heuristic-matchable text → parse_listing returns {}.
_EMPTY_HTML = _b("<html><body>Welcome to our family dealership.</body></html>")


def _run(coro):
    return asyncio.run(coro)


# ── pure helpers ──────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_origin_and_host_strip_www():
    assert gx._origin("https://www.dealer.example/auto/1") == "https://www.dealer.example"
    assert gx._origin("dealer.example") == "https://dealer.example"
    assert gx._host("https://www.Dealer.Example:8443/x") == "dealer.example"


@pytest.mark.unit
def test_same_site_matches_subdomains_only():
    assert gx._same_site("https://stock.dealer.example/auto/1", "dealer.example")
    assert gx._same_site("https://www.dealer.example/auto/1", "dealer.example")
    assert not gx._same_site("https://evil-dealer.example/auto/1", "dealer.example")
    assert not gx._same_site("https://other.com/auto/1", "dealer.example")


@pytest.mark.unit
@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://d.example/vehicles/bmw-320d-1", True),
        ("https://d.example/auto-occasion/x", True),
        ("https://d.example/voiture/y", True),
        ("https://d.example/coches/z", True),
        ("https://d.example/fahrzeuge/w", True),
        ("https://d.example/about-us", False),
        ("https://d.example/contact", False),
        ("https://d.example/", False),
    ],
)
def test_looks_like_listing(url, expected):
    assert gx.looks_like_listing(url) is expected


@pytest.mark.unit
def test_parse_sitemap_locs_unescapes_and_orders():
    xml = (
        "<urlset><url><loc>https://d.example/vehicles/a&amp;b-1</loc></url>"
        "<url><loc> https://d.example/vehicles/2 </loc></url></urlset>"
    )
    assert gx.parse_sitemap_locs(xml) == [
        "https://d.example/vehicles/a&b-1",
        "https://d.example/vehicles/2",
    ]


@pytest.mark.unit
def test_is_sitemap_index_vs_urlset():
    assert gx.is_sitemap_index("<sitemapindex><sitemap><loc>x</loc></sitemap></sitemapindex>")
    assert not gx.is_sitemap_index("<urlset><url><loc>x</loc></url></urlset>")


@pytest.mark.unit
def test_looks_like_sitemap():
    assert gx.looks_like_sitemap("<urlset>")
    assert gx.looks_like_sitemap("<sitemapindex>")
    assert not gx.looks_like_sitemap("<html><body>nope</body></html>")


@pytest.mark.unit
def test_decode_sitemap_plain():
    result = FetchResult(url="https://d.example/sitemap.xml", status_code=200, body=_b("<urlset/>"))
    assert gx.decode_sitemap(result) == "<urlset/>"


@pytest.mark.unit
def test_decode_sitemap_gunzips_by_extension_and_magic():
    raw = "<urlset><url><loc>https://d.example/vehicles/1</loc></url></urlset>"
    gz = gzip.compress(_b(raw))
    by_ext = FetchResult(url="https://d.example/sitemap.xml.gz", status_code=200, body=gz)
    assert gx.decode_sitemap(by_ext) == raw
    # Even without a .gz suffix, gzip magic bytes are detected and inflated.
    by_magic = FetchResult(url="https://d.example/sitemap.xml", status_code=200, body=gz)
    assert gx.decode_sitemap(by_magic) == raw


# ── sitemap discovery ───────────────────────────────────────────────────────
@pytest.mark.unit
def test_discover_sitemap_candidates_robots_first():
    robots = "User-agent: *\nSitemap: https://dealer.example/sitemaps/master.xml\n"
    fetcher = MapFetcher({"https://dealer.example/robots.txt": (200, _b(robots))})
    candidates = _run(gx.discover_sitemap_candidates("https://dealer.example", fetcher))
    assert candidates[0] == "https://dealer.example/sitemaps/master.xml"
    # Standard fallbacks are still appended after the robots-declared sitemap.
    assert "https://dealer.example/sitemap.xml" in candidates


def _sitemap_dealer_pages() -> dict[str, tuple[int, bytes]]:
    robots = "Sitemap: https://dealer.example/sitemaps/master.xml\n"
    index = (
        "<sitemapindex>"
        "<sitemap><loc>https://dealer.example/sitemaps/vehicles-1.xml</loc></sitemap>"
        "<sitemap><loc>https://dealer.example/sitemaps/pages.xml</loc></sitemap>"
        "</sitemapindex>"
    )
    vehicles = (
        "<urlset>"
        "<url><loc>https://dealer.example/vehicles/bmw-320d-1</loc></url>"
        "<url><loc>https://dealer.example/vehicles/audi-a4-2</loc></url>"
        "<url><loc>https://dealer.example/about-us</loc></url>"          # not a listing
        "<url><loc>https://othersite.com/vehicles/x-3</loc></url>"       # cross-site
        "<url><loc>https://dealer.example/</loc></url>"                  # root, not deep
        "</urlset>"
    )
    pages = "<urlset><url><loc>https://dealer.example/contact</loc></url></urlset>"
    return {
        "https://dealer.example/robots.txt": (200, _b(robots)),
        "https://dealer.example/sitemaps/master.xml": (200, _b(index)),
        "https://dealer.example/sitemaps/vehicles-1.xml": (200, _b(vehicles)),
        "https://dealer.example/sitemaps/pages.xml": (200, _b(pages)),
    }


@pytest.mark.unit
def test_discover_sitemap_listings_recurses_and_filters():
    fetcher = MapFetcher(_sitemap_dealer_pages())
    urls = _run(gx.discover_sitemap_listings("https://dealer.example", fetcher))
    assert urls == [
        "https://dealer.example/vehicles/bmw-320d-1",
        "https://dealer.example/vehicles/audi-a4-2",
    ]


@pytest.mark.unit
def test_discover_sitemap_listings_respects_max_urls():
    fetcher = MapFetcher(_sitemap_dealer_pages())
    urls = _run(gx.discover_sitemap_listings("https://dealer.example", fetcher, max_urls=1))
    assert urls == ["https://dealer.example/vehicles/bmw-320d-1"]


# ── WordPress discovery ─────────────────────────────────────────────────────
def _wp_dealer_pages() -> dict[str, tuple[int, bytes]]:
    types = (
        '{"post":{"slug":"post"},"page":{"slug":"page"},'
        '"vehicle":{"slug":"vehicle"}}'
    )
    items = (
        '[{"id":1,"link":"https://wpdealer.example/vehicle/audi-a4-9"},'
        '{"id":2,"link":"https://wpdealer.example/vehicle/bmw-x5-10"},'
        '{"id":3,"link":"https://othersite.com/vehicle/x-11"}]'   # cross-site dropped
    )
    return {
        "https://wpdealer.example/wp-json/": (200, _b('{"name":"WP Dealer"}')),
        "https://wpdealer.example/wp-json/wp/v2/types": (200, _b(types)),
        "https://wpdealer.example/wp-json/wp/v2/vehicle?per_page=100&page=1": (200, _b(items)),
    }


@pytest.mark.unit
def test_discover_wp_listings_enumerates_vehicle_cpt():
    fetcher = MapFetcher(_wp_dealer_pages())
    urls = _run(gx.discover_wp_listings("https://wpdealer.example", fetcher))
    assert urls == [
        "https://wpdealer.example/vehicle/audi-a4-9",
        "https://wpdealer.example/vehicle/bmw-x5-10",
    ]


@pytest.mark.unit
def test_discover_wp_listings_empty_when_not_wordpress():
    fetcher = MapFetcher({})  # /wp-json/ → 404
    assert _run(gx.discover_wp_listings("https://plain.example", fetcher)) == []


# ── union strategy ──────────────────────────────────────────────────────────
@pytest.mark.unit
def test_discover_listing_urls_prefers_sitemap_skips_wp():
    fetcher = MapFetcher(_sitemap_dealer_pages())
    urls = _run(gx.discover_listing_urls("https://dealer.example", fetcher))
    assert urls == [
        "https://dealer.example/vehicles/bmw-320d-1",
        "https://dealer.example/vehicles/audi-a4-2",
    ]
    # A dealer with a vehicle sitemap costs zero /wp-json probes.
    assert not any("wp-json" in u for u in fetcher.requested)


@pytest.mark.unit
def test_discover_listing_urls_falls_back_to_wp():
    fetcher = MapFetcher(_wp_dealer_pages())  # no sitemaps at all
    urls = _run(gx.discover_listing_urls("https://wpdealer.example", fetcher))
    assert urls == [
        "https://wpdealer.example/vehicle/audi-a4-9",
        "https://wpdealer.example/vehicle/bmw-x5-10",
    ]


# ── extract_listing ─────────────────────────────────────────────────────────
@pytest.mark.unit
def test_extract_listing_ok_yields_record():
    url = "https://dealer.example/vehicles/bmw-320d-1"
    fetcher = MapFetcher({url: (200, _detail_html())})
    record, reason = _run(gx.extract_listing(url, fetcher, country="de"))
    assert reason == "ok"
    assert record is not None
    assert record.make == "BMW"
    assert record.model == "320d"
    assert record.year == 2019
    assert record.price_gross == Decimal("24900")
    assert record.currency == "EUR"
    assert record.source_domain == "dealer.example"
    assert record.country == "DE"
    assert len(record.images) >= 1


@pytest.mark.unit
def test_extract_listing_fetch_error():
    url = "https://dealer.example/vehicles/x-1"
    fetcher = MapFetcher({}, fail_urls={url})
    record, reason = _run(gx.extract_listing(url, fetcher, country="de"))
    assert record is None
    assert reason == "fetch_error"


@pytest.mark.unit
def test_extract_listing_http_status_reason():
    url = "https://dealer.example/vehicles/gone-1"
    fetcher = MapFetcher({url: (404, b"")})
    record, reason = _run(gx.extract_listing(url, fetcher, country="de"))
    assert record is None
    assert reason == "http_404"


@pytest.mark.unit
def test_extract_listing_no_fields():
    url = "https://dealer.example/vehicles/blank-1"
    fetcher = MapFetcher({url: (200, _EMPTY_HTML)})
    record, reason = _run(gx.extract_listing(url, fetcher, country="de"))
    assert record is None
    assert reason == "no_fields"


@pytest.mark.unit
def test_extract_listing_missing_critical():
    url = "https://dealer.example/vehicles/partial-1"
    fetcher = MapFetcher({url: (200, _PARTIAL_HTML)})
    record, reason = _run(gx.extract_listing(url, fetcher, country="de"))
    assert record is None
    assert reason.startswith("missing_critical:")
    assert "price" in reason and "year" in reason and "images" in reason


@pytest.mark.unit
def test_extract_listing_quality_failure_on_non_deep_link():
    # Full JSON-LD passes critical fields, but a root source_url fails GATE 1.
    url = "https://dealer.example/"
    fetcher = MapFetcher({url: (200, _detail_html())})
    record, reason = _run(gx.extract_listing(url, fetcher, country="de"))
    assert record is None
    assert "url_not_deep_link" in reason


# ── extract_dealer ──────────────────────────────────────────────────────────
@pytest.mark.unit
def test_extract_dealer_end_to_end():
    pages = _sitemap_dealer_pages()
    pages["https://dealer.example/vehicles/bmw-320d-1"] = (200, _detail_html(model="320d"))
    pages["https://dealer.example/vehicles/audi-a4-2"] = (
        200,
        _detail_html(make="Audi", model="A4", price="18500"),
    )
    fetcher = MapFetcher(pages)

    result = _run(gx.extract_dealer("https://dealer.example", fetcher, country="de"))

    assert result.discovered == 2
    assert result.attempted == 2
    assert result.extracted == 2
    assert result.rejected == ()
    assert result.success_rate == 1.0
    assert result.country == "DE"
    models = sorted(r.model for r in result.records)
    assert models == ["320d", "A4"]
    assert all(r.has_critical_fields() for r in result.records)


@pytest.mark.unit
def test_extract_dealer_with_explicit_urls_isolates_failures():
    good = "https://dealer.example/vehicles/good-1"
    bad = "https://dealer.example/vehicles/gone-2"
    fetcher = MapFetcher({good: (200, _detail_html()), bad: (404, b"")})

    result = _run(
        gx.extract_dealer("https://dealer.example", fetcher, country="de", urls=[good, bad])
    )

    assert result.discovered == 2
    assert result.attempted == 2
    assert result.extracted == 1
    assert result.rejected == ((bad, "http_404"),)
    assert result.records[0].source_url == good
    # Discovery was skipped entirely when urls= is supplied.
    assert "https://dealer.example/robots.txt" not in fetcher.requested
