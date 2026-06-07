"""
Unit tests for de_11880 pure parsers (no network, no DB).

Fixtures are derived from real 11880.com HTML verified 2026-06-07.

Run from the scrapers/ directory:
    cd scrapers && PYTHONPATH=.. python -m pytest tests/test_de_11880.py -q
"""
from __future__ import annotations

import json
import textwrap

import pytest

from scrapers.discovery.sources.de_11880 import (
    _domain,
    _normalize_url,
    _registry_id_from_path,
    parse_detail_page,
    parse_listing_page,
    parse_total_pages,
    _listing_item_to_candidate,
)

# ---------------------------------------------------------------------------
# Real data verified from 11880.com on 2026-06-07
# ---------------------------------------------------------------------------

# Exact JSON-LD ItemList block from page 1 (two items shown)
_JSONLD_REAL = json.dumps({
    "@context": "http://schema.org",
    "@type": "SearchResultsPage",
    "mainEntity": {
        "@type": "ItemList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "item": {
                    "@type": "LocalBusiness",
                    "name": "Auto Dietz GmbH",
                    "url": "https://www.11880.com/branchenbuch/bardowick/120672194B27114587/auto-dietz-gmbh.html",
                    "email": "o.dietz@autodietz.de",
                    "address": {
                        "@type": "PostalAddress",
                        "postalCode": "21357",
                        "addressLocality": "Bardowick",
                        "addressRegion": "Niedersachsen",
                        "streetAddress": "Hamburger Landstr. 3",
                    },
                    "telephone": "(04131) 9242-0",
                },
            },
            {
                "@type": "ListItem",
                "position": 2,
                "item": {
                    "@type": "LocalBusiness",
                    "name": "SpaceClean GbR",
                    "url": "https://www.11880.com/branchenbuch/duesseldorf/061330955B113719547/spaceclean-gbr.html",
                    "address": {
                        "@type": "PostalAddress",
                        "postalCode": "40591",
                        "addressLocality": "Düsseldorf",
                        "addressRegion": "Nordrhein-Westfalen",
                        "streetAddress": "Witzheldener Str. 12",
                    },
                    "telephone": "(0173) 3570004",
                },
            },
        ],
    },
})

_LISTING_PAGE_HTML = (
    f'<script type="application/ld+json">{_JSONLD_REAL}</script>'
    '<span id="hit-count">52721</span>'
)

# Real detail page HTML for Auto Dietz GmbH (key fragments only)
_DETAIL_HTML_WITH_WEB = textwrap.dedent("""\
    <html><body>
    <script type="application/ld+json">
    {"localBusiness": {
        "@context": "http://schema.org",
        "@type": "LocalBusiness",
        "name": "Auto Dietz GmbH",
        "url": "https://www.11880.com/branchenbuch/bardowick/120672194B27114587/auto-dietz-gmbh.html",
        "geo": {"@type": "GeoCoordinates", "longitude": 10.390282, "latitude": 53.289083}
    }}
    </script>
    <div class="mobile-action-bar">
      <div class="mobile-action-bar__icon icon icon-website"></div>
      <meta itemprop="url" content="http://www.autodietz.de" />
    </div>
    </body></html>
""")

_DETAIL_HTML_NO_WEB = textwrap.dedent("""\
    <html><body>
    <script type="application/ld+json">
    {"localBusiness": {
        "@context": "http://schema.org",
        "@type": "LocalBusiness",
        "name": "Garage Ohne Web GmbH",
        "url": "https://www.11880.com/branchenbuch/berlin/000000000B000000000/garage-ohne-web.html"
    }}
    </script>
    <div class="mobile-action-bar__icon icon icon-phone"></div>
    </body></html>
""")

_DETAIL_HTML_SELF_REF = textwrap.dedent("""\
    <html><body>
    <meta itemprop="url" content="https://www.11880.com/branchenbuch/bardowick/120672194B27114587/auto-dietz-gmbh.html" />
    </body></html>
""")


# ---------------------------------------------------------------------------
# _registry_id_from_path
# ---------------------------------------------------------------------------

class TestRegistryIdFromPath:
    def test_standard_path(self):
        path = "/branchenbuch/bardowick/120672194B27114587/auto-dietz-gmbh.html"
        assert _registry_id_from_path(path) == "11880-120672194B27114587"

    def test_different_id(self):
        path = "/branchenbuch/duesseldorf/061330955B113719547/spaceclean-gbr.html"
        assert _registry_id_from_path(path) == "11880-061330955B113719547"

    def test_invalid_path_returns_none(self):
        assert _registry_id_from_path("/some/other/path") is None

    def test_empty_returns_none(self):
        assert _registry_id_from_path("") is None


# ---------------------------------------------------------------------------
# _domain / _normalize_url
# ---------------------------------------------------------------------------

class TestDomain:
    def test_strips_www(self):
        assert _domain("https://www.autodietz.de/") == "autodietz.de"

    def test_no_www(self):
        assert _domain("https://autohaus-xyz.de") == "autohaus-xyz.de"

    def test_none(self):
        assert _domain(None) is None

    def test_empty(self):
        assert _domain("") is None


class TestNormalizeUrl:
    def test_adds_https(self):
        assert _normalize_url("www.autodietz.de") == "https://www.autodietz.de"

    def test_strips_trailing_slash(self):
        assert _normalize_url("https://autodietz.de/") == "https://autodietz.de"

    def test_none_returns_none(self):
        assert _normalize_url(None) is None

    def test_empty_returns_none(self):
        assert _normalize_url("") is None


# ---------------------------------------------------------------------------
# parse_listing_page
# ---------------------------------------------------------------------------

class TestParseListingPage:
    def test_parses_two_items(self):
        candidates = parse_listing_page(_LISTING_PAGE_HTML)
        assert len(candidates) == 2

    def test_first_item_fields(self):
        candidates = parse_listing_page(_LISTING_PAGE_HTML)
        c = candidates[0]
        assert c["name"] == "Auto Dietz GmbH"
        assert c["source"] == "11880"
        assert c["country"] == "DE"
        assert c["source_layer"] == 2
        assert c["email"] == "o.dietz@autodietz.de"
        assert c["phone"] == "(04131) 9242-0"
        assert c["postcode"] == "21357"
        assert c["city"] == "Bardowick"
        assert "Hamburger" in (c["address"] or "")
        assert c["registry_id"] == "11880-120672194B27114587"
        # Listing rows have no domain yet
        assert c["domain"] is None
        assert c["url"] is None

    def test_second_item_no_email(self):
        candidates = parse_listing_page(_LISTING_PAGE_HTML)
        c = candidates[1]
        assert c["name"] == "SpaceClean GbR"
        assert c["email"] is None

    def test_detail_path_present(self):
        candidates = parse_listing_page(_LISTING_PAGE_HTML)
        c = candidates[0]
        assert "detail_path" in c
        assert "bardowick" in (c["detail_path"] or "")

    def test_external_refs_contain_profile(self):
        candidates = parse_listing_page(_LISTING_PAGE_HTML)
        refs = candidates[0].get("external_refs") or {}
        assert "profile" in refs
        assert "11880.com" in refs["profile"]

    def test_empty_page_returns_empty(self):
        assert parse_listing_page("<html><body>no json-ld here</body></html>") == []

    def test_html_entities_unescaped(self):
        jsonld_with_amp = json.dumps({
            "@context": "http://schema.org",
            "@type": "SearchResultsPage",
            "mainEntity": {
                "@type": "ItemList",
                "itemListElement": [{
                    "@type": "ListItem",
                    "position": 1,
                    "item": {
                        "@type": "LocalBusiness",
                        "name": "GmbH &amp; Co. KG Test",
                        "url": "https://www.11880.com/branchenbuch/city/AABBCC123/test.html",
                    },
                }],
            },
        })
        html = f'<script type="application/ld+json">{jsonld_with_amp}</script>'
        candidates = parse_listing_page(html)
        assert len(candidates) == 1
        assert "&amp;" not in (candidates[0]["name"] or "")
        assert "&" in (candidates[0]["name"] or "")


# ---------------------------------------------------------------------------
# parse_detail_page
# ---------------------------------------------------------------------------

class TestParseDetailPage:
    def test_with_web_extracts_url_and_domain(self):
        result = parse_detail_page(_DETAIL_HTML_WITH_WEB)
        assert result["url"] is not None
        assert "autodietz.de" in result["url"]
        assert result["domain"] == "autodietz.de"

    def test_with_web_extracts_geo(self):
        result = parse_detail_page(_DETAIL_HTML_WITH_WEB)
        assert result["lat"] == pytest.approx(53.289083, rel=1e-4)
        assert result["lng"] == pytest.approx(10.390282, rel=1e-4)

    def test_no_web_returns_none_url(self):
        result = parse_detail_page(_DETAIL_HTML_NO_WEB)
        assert result["url"] is None
        assert result["domain"] is None
        assert result["lat"] is None

    def test_self_ref_filtered(self):
        """11880 self-URL in itemprop must not be returned as dealer website."""
        result = parse_detail_page(_DETAIL_HTML_SELF_REF)
        assert result["url"] is None
        assert result["domain"] is None

    def test_empty_html(self):
        result = parse_detail_page("<html></html>")
        assert result == {"url": None, "domain": None, "lat": None, "lng": None}


# ---------------------------------------------------------------------------
# parse_total_pages
# ---------------------------------------------------------------------------

class TestParseTotalPages:
    def test_real_hit_count(self):
        html = '<span id="hit-count">52721</span>'
        pages = parse_total_pages(html)
        assert pages == 1055  # ceil(52721 / 50)

    def test_round_number(self):
        html = '<span id="hit-count">1000</span>'
        pages = parse_total_pages(html)
        assert pages == 20

    def test_fallback_when_no_hit_count(self):
        # Should return the hardcoded fallback (1055) or a positive number
        pages = parse_total_pages("<html></html>")
        assert pages >= 1
