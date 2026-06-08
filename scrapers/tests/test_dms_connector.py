"""
DMS / inventory-widget connector — pure inventory-list extraction + record building.
No browser: the captured JSON is supplied directly.
"""
from __future__ import annotations

import pytest

from scrapers.dealer_scraping.dms_connector import (
    extract_vehicles_from_captured,
    records_from_raws,
)


@pytest.mark.unit
def test_extract_inventory_array_from_nested_payload():
    captured = [{"meta": {"total": 3}, "data": {"vehicles": [
        {"make": "BMW", "model": "320d", "grossPrice": 24900, "firstRegistration": "2019"},
        {"make": "Audi", "model": "A4", "price": 18500, "baujahr": 2020},
        {"title": "not a car", "id": 7},
    ]}}]
    raws = extract_vehicles_from_captured(captured)
    assert len(raws) == 2
    assert {r["make"] for r in raws} == {"BMW", "Audi"}


@pytest.mark.unit
def test_extract_picks_largest_vehicle_array():
    captured = [
        {"featured": [{"make": "BMW", "model": "X", "price": 1000}]},
        {"results": [{"make": "Audi", "model": "A1", "price": 9000},
                     {"make": "Seat", "model": "Ibiza", "price": 8000}]},
    ]
    raws = extract_vehicles_from_captured(captured)
    assert len(raws) == 2 and {r["make"] for r in raws} == {"Audi", "Seat"}


@pytest.mark.unit
def test_extract_empty_when_no_vehicle_array():
    assert extract_vehicles_from_captured([{"status": "ok", "items": [1, 2]}]) == []


@pytest.mark.unit
def test_records_from_raws_builds_quality_gated_records():
    raws = [
        {"make": "BMW", "model": "320d", "price": "24900", "currency": "EUR",
         "year": "2019", "mileage": "85000", "images": ["https://cdn/1.jpg"]},
        {"make": "Audi", "model": "A4", "price": "18500", "currency": "EUR",
         "year": "2020", "images": ["https://cdn/2.jpg"]},
    ]
    records = records_from_raws(raws, source_domain="d.de", country="DE",
                               base_url="https://d.de/gebrauchtwagen")
    assert len(records) == 2
    makes = sorted(r.make for r in records)
    assert makes == ["Audi", "BMW"]
    # Synthetic deep-link source_url derived per vehicle (passes the deep-link gate).
    assert all(r.source_url.startswith("https://d.de/") and r.source_url != "https://d.de/"
               for r in records)


@pytest.mark.unit
def test_records_kept_without_image_when_core_fields_present():
    # DMS feeds serve photos separately; a missing image must NOT drop a complete car
    # (make/model/year/price). A7 persists without an image.
    raws = [{"make": "CUPRA", "model": "Born", "price": "36033", "year": "2023",
             "mileage": "28900", "fuel_type": "Elektro"}]  # no images
    records = records_from_raws(raws, source_domain="kuehl.seat.de", country="DE",
                               base_url="https://kuehl.seat.de/gebrauchtwagen")
    assert len(records) == 1
    assert records[0].make == "CUPRA" and str(records[0].price) == "36033"
    assert records[0].images == ()


@pytest.mark.unit
def test_records_drop_entries_missing_critical_fields():
    raws = [
        {"make": "BMW", "model": "320d", "price": "24900", "year": "2019",
         "images": ["https://cdn/1.jpg"]},
        {"make": "Audi", "model": "A4"},  # no price/year/images → dropped
    ]
    records = records_from_raws(raws, source_domain="d.de", country="DE")
    assert len(records) == 1 and records[0].make == "BMW"
