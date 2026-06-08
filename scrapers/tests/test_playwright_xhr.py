"""
E07 playwright_xhr — pure normalization of captured vehicle JSON → schema.org JSON-LD →
record. No browser. Validates the multilingual alias mapping and the round-trip through
the EXISTING parse_listing / record_from_rendered so the seam needs no change.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from scrapers.pipeline.parse import parse_listing
from scrapers.pipeline.playwright_extractor import record_from_rendered
from scrapers.pipeline.playwright_xhr import (
    best_vehicle_jsonld,
    inject_jsonld,
    vehicle_json_to_jsonld,
    vehicle_json_to_raw,
    was_xhr_injected,
)

_PAD = "<div class='spec'><span></span></div>" * 600


@pytest.mark.unit
def test_normalize_german_modix_like():
    obj = {"vehicle": {"make": "BMW", "model": "320d", "grossPrice": 24900,
                       "firstRegistration": "2019-03-01", "mileage": 85000,
                       "fuelType": "Diesel", "vehicleIdentificationNumber": "WBA8E9G50GNT12345",
                       "images": ["https://cdn.d.de/1.jpg", "https://cdn.d.de/2.jpg"]}}
    raw = vehicle_json_to_raw(obj)
    assert raw["make"] == "BMW" and raw["model"] == "320d"
    assert raw["price"] == "24900" and raw["year"] == "2019" and raw["mileage"] == "85000"
    assert raw["vin"] == "WBA8E9G50GNT12345" and len(raw["images"]) == 2


@pytest.mark.unit
def test_normalize_french_nested_list_with_value_wrappers():
    obj = {"data": {"results": [{"marque": "Renault", "modele": "Clio",
                                 "prix": {"amount": 14990, "currency": "EUR"},
                                 "kilometrage": {"value": 45000},
                                 "anneeMiseEnCirculation": "2021"}]}}
    raw = vehicle_json_to_raw(obj)
    assert raw["make"] == "Renault" and raw["model"] == "Clio"
    assert raw["price"] == "14990" and raw["mileage"] == "45000" and raw["year"] == "2021"


@pytest.mark.unit
def test_normalize_images_as_objects():
    obj = {"make": "Audi", "model": "A4", "preis": 18500, "baujahr": 2020,
           "media": [{"url": "https://cdn/x1.jpg"}, {"src": "https://cdn/x2.jpg"}]}
    raw = vehicle_json_to_raw(obj)
    assert raw["images"] == ["https://cdn/x1.jpg", "https://cdn/x2.jpg"]
    assert raw["price"] == "18500" and raw["year"] == "2020"


@pytest.mark.unit
def test_normalize_rejects_non_vehicle_json():
    assert vehicle_json_to_raw({"status": "ok", "items": [1, 2, 3]}) == {}
    assert vehicle_json_to_raw({"user": {"name": "x", "id": 5}}) == {}


@pytest.mark.unit
def test_jsonld_is_parseable_by_existing_extractor():
    raw = {"make": "BMW", "model": "320d", "price": "24900", "currency": "EUR",
           "year": "2019", "mileage": "85000", "images": ["https://cdn/1.jpg"]}
    jsonld = vehicle_json_to_jsonld(raw)
    assert jsonld and was_xhr_injected(jsonld)
    html = inject_jsonld("<html><head></head><body>" + _PAD + "</body></html>", jsonld)
    # The EXISTING static parser must read the injected JSON-LD — no seam change needed.
    parsed = parse_listing(html)
    assert parsed.get("make") == "BMW" and parsed.get("model") == "320d"
    assert "24900" in str(parsed.get("price"))


@pytest.mark.unit
def test_full_record_from_injected_xhr():
    # End-to-end: captured XHR → JSON-LD → inject → record_from_rendered → VehicleRecord.
    captured = [{"results": [{"make": "BMW", "model": "320d", "grossPrice": 24900,
                              "vehicleModelDate": "2019",
                              "image": ["https://cdn/1.jpg"], "currency": "EUR"}]}]
    jsonld = best_vehicle_jsonld(captured)
    assert jsonld is not None
    html = inject_jsonld("<html><head></head><body>" + _PAD + "</body></html>", jsonld)
    rec, reason = record_from_rendered(
        html, source_url="https://d.de/fahrzeug/bmw-320d-12345", source_domain="d.de", country="DE")
    assert reason == "ok" and rec is not None
    assert rec.make == "BMW" and rec.model == "320d" and rec.year == 2019
    assert rec.price == Decimal("24900") and rec.has_critical_fields()


@pytest.mark.unit
def test_jsonld_none_without_make_model():
    assert vehicle_json_to_jsonld({"price": "100"}) is None
    assert best_vehicle_jsonld([{"status": "ok"}]) is None
