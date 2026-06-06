"""
A9 entity_resolver tests — the pure cross-source VIN pairing (V12 layer).

The asyncpg reader/writer is the thin live shell (exercised by the seam demo in
P0_EXECUTION_REPORT §P0-4); the matching logic that decides *which* listings are
the same physical car is pure and fully covered here.
"""
from __future__ import annotations

import pytest

from scrapers.entity_resolver import Match, VehicleRef, vin_group_matches


@pytest.mark.unit
def test_two_sources_same_vin_yield_one_match():
    refs = [
        VehicleRef("01AAA", "autotrack.nl"),
        VehicleRef("01BBB", "marktplaats.nl"),
    ]
    matches = vin_group_matches("WVWZZZ1", refs)
    assert len(matches) == 1
    m = matches[0]
    assert m.entity_a_id == "01AAA" and m.entity_a_source == "autotrack.nl"
    assert m.entity_b_id == "01BBB" and m.entity_b_source == "marktplaats.nl"
    assert m.vin == "WVWZZZ1"


@pytest.mark.unit
def test_single_source_repeats_yield_no_match():
    # Same VIN, same platform twice — that is L2 fingerprint dedup, NOT a
    # cross-source entity match. The resolver must stay silent.
    refs = [VehicleRef("01AAA", "autotrack.nl"), VehicleRef("01BBB", "autotrack.nl")]
    assert vin_group_matches("VIN1", refs) == []


@pytest.mark.unit
def test_single_ref_yields_no_match():
    assert vin_group_matches("VIN1", [VehicleRef("01AAA", "autotrack.nl")]) == []


@pytest.mark.unit
def test_three_sources_anchor_smallest_ulid():
    refs = [
        VehicleRef("01CCC", "viabovag.nl"),
        VehicleRef("01AAA", "autotrack.nl"),
        VehicleRef("01BBB", "marktplaats.nl"),
    ]
    matches = vin_group_matches("VIN1", refs)
    assert len(matches) == 2
    # All pairs anchor on the smallest ULID (01AAA) → stable, idempotent.
    assert all(m.entity_a_id == "01AAA" for m in matches)
    assert {m.entity_b_id for m in matches} == {"01BBB", "01CCC"}


@pytest.mark.unit
def test_pairing_is_order_independent():
    a = [VehicleRef("01BBB", "x.nl"), VehicleRef("01AAA", "y.nl")]
    b = [VehicleRef("01AAA", "y.nl"), VehicleRef("01BBB", "x.nl")]
    assert vin_group_matches("VIN1", a) == vin_group_matches("VIN1", b)
