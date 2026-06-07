"""NL BOVAG member directory — pure parser tests (no network, no DB)."""
from __future__ import annotations

import json

import pytest

from scrapers.discovery.sources import nl_bovag


# ---------------------------------------------------------------------------
# Helpers to build minimal __NEXT_DATA__ HTML fixtures
# ---------------------------------------------------------------------------

def _make_page_html(page: dict) -> str:
    """Wrap a page dict in a minimal __NEXT_DATA__ HTML string."""
    payload = {"props": {"pageProps": {"page": page}}}
    blob = json.dumps(payload)
    return (
        f'<html><head><title>BOVAG - {page.get("name", "Test")}</title></head>'
        f'<body><script id="__NEXT_DATA__" type="application/json">{blob}</script></body></html>'
    )


def _auto_vehicle(key: str = "auto") -> dict:
    return {
        "_type": "memberProperty",
        "property": {"_type": "keyValuePair", "key": key, "value": key.capitalize()},
        "propertyType": "vehicle",
    }


# ---------------------------------------------------------------------------
# extract_leden_urls
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_extract_leden_urls_basic():
    xml = (
        "<urlset>"
        "<url><loc>https://www.bovag.nl/leden/autobedrijf-wolfs-bv</loc></url>"
        "<url><loc>https://www.bovag.nl/leden/hedin-automotive</loc></url>"
        "<url><loc>https://www.bovag.nl/over-bovag</loc></url>"  # not /leden/ → excluded
        "</urlset>"
    )
    urls = nl_bovag.extract_leden_urls(xml)
    assert urls == [
        "https://www.bovag.nl/leden/autobedrijf-wolfs-bv",
        "https://www.bovag.nl/leden/hedin-automotive",
    ]


@pytest.mark.unit
def test_extract_leden_urls_empty():
    assert nl_bovag.extract_leden_urls("<urlset></urlset>") == []


# ---------------------------------------------------------------------------
# parse_member_page — with website (styles_website href in JSON)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_parse_member_with_website_from_json():
    page = {
        "name": "Autobedrijf Wolfs B.V.",
        "website": "http://www.wolfs-autobedrijf.nl",
        "address": {
            "street": "Tt. Vasumweg", "housenumber": 16,
            "postalCode": "1033 SC", "city": "Amsterdam",
            "latitude": 52.402627, "longitude": 4.897297,
        },
        "phoneNumber": "020-6335163",
        "vehicles": [_auto_vehicle("auto")],
    }
    html = _make_page_html(page)
    c = nl_bovag.parse_member_page(html, "autobedrijf-wolfs-bv")
    assert c is not None
    assert c["name"] == "Autobedrijf Wolfs B.V."
    assert c["domain"] == "wolfs-autobedrijf.nl"
    assert c["url"] == "http://www.wolfs-autobedrijf.nl"
    assert c["postcode"] == "1033 SC"
    assert c["city"] == "Amsterdam"
    assert c["address"] == "Tt. Vasumweg 16"
    assert c["lat"] == 52.402627
    assert c["lng"] == 4.897297
    assert c["phone"] == "020-6335163"
    assert c["registry_id"] == "autobedrijf-wolfs-bv"
    assert c["source"] == "bovag"
    assert c["source_layer"] == 2
    assert c["country"] == "NL"
    assert c["_automotive"] is True


@pytest.mark.unit
def test_parse_member_website_fallback_to_html_anchor():
    """When JSON has no website field, parser falls back to styles_website href in HTML."""
    page = {
        "name": "Garage Test BV",
        "address": {"postalCode": "2000 AB", "city": "Rotterdam"},
        "vehicles": [_auto_vehicle("bedrijfswagen")],
    }
    payload = json.dumps({"props": {"pageProps": {"page": page}}})
    html = (
        '<html><head><title>BOVAG - Garage Test BV</title></head><body>'
        f'<script id="__NEXT_DATA__" type="application/json">{payload}</script>'
        '<a class="styles_website__XyZ99" href="https://www.garagetest.nl">garagetest.nl</a>'
        '</body></html>'
    )
    c = nl_bovag.parse_member_page(html, "garage-test-bv")
    assert c is not None
    assert c["domain"] == "garagetest.nl"
    assert c["url"] == "https://www.garagetest.nl"


@pytest.mark.unit
def test_parse_member_no_website_yields_identity_only():
    """Member without website still returns candidate (identity via slug)."""
    page = {
        "name": "Autoservice Den Haag",
        "address": {"postalCode": "2500 AA", "city": "Den Haag"},
        "vehicles": [_auto_vehicle("auto")],
    }
    c = nl_bovag.parse_member_page(_make_page_html(page), "autoservice-den-haag")
    assert c is not None
    assert c["domain"] is None
    assert c["registry_id"] == "autoservice-den-haag"
    assert c["postcode"] == "2500 AA"


@pytest.mark.unit
def test_parse_member_returns_none_without_next_data():
    assert nl_bovag.parse_member_page("<html>No data</html>", "slug") is None


@pytest.mark.unit
def test_parse_member_returns_none_for_nameless_page():
    """Page with no name in JSON and title that doesn't match 'BOVAG - <name>' pattern → None."""
    page = {"address": {"city": "Utrecht"}}
    payload = json.dumps({"props": {"pageProps": {"page": page}}})
    # Title deliberately omits the "BOVAG - <name>" pattern so the fallback also yields nothing
    html = (
        '<html><head><title>BOVAG</title></head>'
        f'<body><script id="__NEXT_DATA__" type="application/json">{payload}</script></body></html>'
    )
    c = nl_bovag.parse_member_page(html, "slug")
    assert c is None


# ---------------------------------------------------------------------------
# is_automotive / _vehicle_keys
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_automotive_with_auto_key():
    page = {"name": "Auto X", "vehicles": [_auto_vehicle("auto")]}
    assert nl_bovag.is_automotive(page) is True


@pytest.mark.unit
def test_automotive_with_bedrijfswagen():
    page = {"name": "Van Co", "vehicles": [_auto_vehicle("bedrijfswagen")]}
    assert nl_bovag.is_automotive(page) is True


@pytest.mark.unit
def test_non_automotive_fiets_only():
    page = {"name": "Rijwielhandel Schilder", "vehicles": [_auto_vehicle("fiets")]}
    assert nl_bovag.is_automotive(page) is False


@pytest.mark.unit
def test_non_automotive_mixed_but_no_auto_key():
    """bromfiets + motor → not automotive (none in AUTO_KEYS)."""
    page = {"name": "Moped Shop", "vehicles": [_auto_vehicle("bromfiets"), _auto_vehicle("motor")]}
    assert nl_bovag.is_automotive(page) is False


@pytest.mark.unit
def test_automotive_mixed_auto_and_fiets():
    """auto + fiets together → still automotive (any match in AUTO_KEYS suffices)."""
    page = {"name": "Multi BV", "vehicles": [_auto_vehicle("auto"), _auto_vehicle("fiets")]}
    assert nl_bovag.is_automotive(page) is True


@pytest.mark.unit
def test_automotive_no_vehicles_list_is_inclusive():
    """Members with no vehicle metadata are included conservatively."""
    page = {"name": "Unknown Garage"}
    assert nl_bovag.is_automotive(page) is True


# ---------------------------------------------------------------------------
# _domain / _normalize_url helpers
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_domain_strips_www():
    assert nl_bovag._domain("http://www.example.nl") == "example.nl"


@pytest.mark.unit
def test_normalize_url_adds_https():
    assert nl_bovag._normalize_url("example.nl") == "https://example.nl"


@pytest.mark.unit
def test_domain_none_for_empty():
    assert nl_bovag._domain(None) is None
    assert nl_bovag._domain("") is None
