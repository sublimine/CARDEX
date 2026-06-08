"""
Minimal pure-function tests for osm_full parsers.
No network, no DB required.

Run:
    python -m pytest scrapers/discovery/sources/test_osm_full.py -v
    # or directly:
    python scrapers/discovery/sources/test_osm_full.py
"""
from __future__ import annotations

import sys
import os

# Allow running from the repo root without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from scrapers.discovery.sources.osm_full import (
    normalize_url,
    extract_domain,
    build_address,
    element_to_candidate,
    parse_elements,
)


# ---------------------------------------------------------------------------
# normalize_url
# ---------------------------------------------------------------------------

def test_normalize_url_adds_scheme():
    assert normalize_url("example.com") == "https://example.com"

def test_normalize_url_keeps_https():
    assert normalize_url("https://example.com/path/") == "https://example.com/path"

def test_normalize_url_none():
    assert normalize_url(None) is None

def test_normalize_url_empty():
    assert normalize_url("") is None


# ---------------------------------------------------------------------------
# extract_domain
# ---------------------------------------------------------------------------

def test_extract_domain_strips_www():
    assert extract_domain("https://www.dealer.de/") == "dealer.de"

def test_extract_domain_no_www():
    assert extract_domain("https://garage.fr") == "garage.fr"

def test_extract_domain_none():
    assert extract_domain(None) is None

def test_extract_domain_malformed():
    # urlparse shouldn't raise; domain is just empty
    result = extract_domain("not-a-url-at-all")
    assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# build_address
# ---------------------------------------------------------------------------

def test_build_address_full():
    tags = {
        "addr:street": "Rue de la Paix",
        "addr:housenumber": "12",
        "addr:postcode": "75001",
        "addr:city": "Paris",
    }
    addr = build_address(tags)
    assert addr == "Rue de la Paix, 12, 75001, Paris"

def test_build_address_partial():
    tags = {"addr:city": "Berlin"}
    assert build_address(tags) == "Berlin"

def test_build_address_empty():
    assert build_address({}) is None


# ---------------------------------------------------------------------------
# element_to_candidate — node
# ---------------------------------------------------------------------------

_NODE = {
    "type": "node",
    "id": 123456789,
    "lat": 48.8566,
    "lon": 2.3522,
    "tags": {
        "name": "Garage Dupont",
        "shop": "car",
        "website": "https://www.dupont-autos.fr",
        "phone": "+33 1 23 45 67 89",
        "addr:city": "Paris",
        "addr:postcode": "75001",
    },
}

def test_node_candidate_basic():
    cand = element_to_candidate(_NODE, "FR")
    assert cand is not None
    assert cand["name"] == "Garage Dupont"
    assert cand["country"] == "FR"
    assert cand["source"] == "osm"
    assert cand["source_layer"] == 4
    assert cand["registry_id"] == "node/123456789"
    assert cand["lat"] == 48.8566
    assert cand["lng"] == 2.3522

def test_node_candidate_domain():
    cand = element_to_candidate(_NODE, "FR")
    assert cand is not None
    assert cand["domain"] == "dupont-autos.fr"
    assert cand["url"] == "https://www.dupont-autos.fr"

def test_node_candidate_external_refs_contains_shop_tag():
    cand = element_to_candidate(_NODE, "FR")
    assert cand is not None
    assert cand["external_refs"]["osm_tags"]["shop"] == "car"


# ---------------------------------------------------------------------------
# element_to_candidate — way (uses center)
# ---------------------------------------------------------------------------

_WAY = {
    "type": "way",
    "id": 987654321,
    "center": {"lat": 52.52, "lon": 13.405},
    "tags": {
        "name": "Autohaus Berlin",
        "shop": "vehicle",
    },
}

def test_way_candidate_uses_center():
    cand = element_to_candidate(_WAY, "DE")
    assert cand is not None
    assert cand["lat"] == 52.52
    assert cand["lng"] == 13.405
    assert cand["domain"] is None  # no website tag
    assert cand["registry_id"] == "way/987654321"


# ---------------------------------------------------------------------------
# element_to_candidate — filter cases
# ---------------------------------------------------------------------------

def test_no_name_returns_none():
    el = {"type": "node", "id": 1, "lat": 1.0, "lon": 1.0, "tags": {"shop": "car"}}
    assert element_to_candidate(el, "ES") is None

def test_no_coords_returns_none():
    el = {"type": "node", "id": 1, "tags": {"name": "Dealer", "shop": "car"}}
    assert element_to_candidate(el, "BE") is None

def test_way_without_center_returns_none():
    el = {"type": "way", "id": 2, "tags": {"name": "Dealer", "shop": "car"}}
    assert element_to_candidate(el, "NL") is None


# ---------------------------------------------------------------------------
# parse_elements
# ---------------------------------------------------------------------------

def test_parse_elements_yields_valid_only():
    data = {
        "elements": [
            _NODE,
            _WAY,
            # nameless — should be filtered
            {"type": "node", "id": 99, "lat": 0.0, "lon": 0.0, "tags": {"shop": "car"}},
        ]
    }
    results = list(parse_elements(data, "FR"))
    assert len(results) == 2

def test_parse_elements_empty_data():
    results = list(parse_elements({}, "CH"))
    assert results == []


# ---------------------------------------------------------------------------
# NEW tag coverage — verify new shop=vehicle and craft=coachbuilder parse correctly
# ---------------------------------------------------------------------------

def test_shop_vehicle_tag_captured():
    el = {
        "type": "node", "id": 555, "lat": 50.0, "lon": 4.0,
        "tags": {"name": "VehicleCo", "shop": "vehicle"},
    }
    cand = element_to_candidate(el, "BE")
    assert cand is not None
    assert cand["external_refs"]["osm_tags"]["shop"] == "vehicle"

def test_craft_coachbuilder_captured():
    el = {
        "type": "node", "id": 666, "lat": 47.0, "lon": 8.0,
        "tags": {"name": "Karosserie AG", "craft": "coachbuilder"},
    }
    cand = element_to_candidate(el, "CH")
    assert cand is not None
    assert cand["external_refs"]["osm_tags"]["craft"] == "coachbuilder"

def test_shop_trailer_captured():
    el = {
        "type": "node", "id": 777, "lat": 51.0, "lon": 4.5,
        "tags": {"name": "Trailer NL", "shop": "trailer"},
    }
    cand = element_to_candidate(el, "NL")
    assert cand is not None
    assert cand["external_refs"]["osm_tags"]["shop"] == "trailer"


# ---------------------------------------------------------------------------
# Runner (no pytest dependency)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback

    tests = [
        (name, fn) for name, fn in sorted(globals().items())
        if name.startswith("test_") and callable(fn)
    ]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except Exception:
            print(f"  FAIL  {name}")
            traceback.print_exc()
            failed += 1

    print(f"\n{passed} passed, {failed} failed out of {len(tests)} tests.")
    sys.exit(0 if failed == 0 else 1)
