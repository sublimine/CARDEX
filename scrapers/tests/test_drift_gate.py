"""Drift gate — composes volume + field + schema-fp drift into one per-source verdict."""
from __future__ import annotations

import pytest

from scrapers.db import connect, migrate
from scrapers.intelligence.drift_gate import (
    HarvestStats,
    evaluate,
    stats_from_records,
)
from scrapers.portals.config import (
    DriftBaseline,
    ExtractionConfig,
    Extraction,
)


def _cfg(**base) -> ExtractionConfig:
    bl = DriftBaseline(
        extraction_method="jsonld",
        expected_min_volume=base.get("expected_min_volume", 3),
        required_fields=tuple(base.get("required_fields", ("make", "model", "year", "price"))),
        min_nonnull_ratio=base.get("min_nonnull_ratio", 0.7),
    )
    return ExtractionConfig(
        source_key="test.nl", country="NL", strategy="jsonld_detail",
        extraction=Extraction(method="jsonld"), drift_baseline=bl,
    )


@pytest.mark.unit
def test_healthy_harvest_passes():
    cfg = _cfg()
    stats = HarvestStats(
        volume=10,
        field_nonnull={"make": 10, "model": 10, "year": 9, "price": 10},
        sample_raw_fields={},  # no conn → schema dimension skipped
    )
    r = evaluate(cfg, stats, conn=None)
    assert r.ok and not r.alert
    assert r.volume_ok and r.fields_ok and not r.schema_changed


@pytest.mark.unit
def test_volume_drift_alerts():
    cfg = _cfg(expected_min_volume=50)
    stats = HarvestStats(volume=4, field_nonnull={"make": 4, "model": 4, "year": 4, "price": 4},
                         sample_raw_fields={})
    r = evaluate(cfg, stats, conn=None)
    assert r.alert and not r.volume_ok
    assert "volume(4<50)" in r.reason()


@pytest.mark.unit
def test_field_drift_alerts_naming_weak_field():
    cfg = _cfg()
    # price present in only 2/10 → below 0.7 ratio → field drift on `price`.
    stats = HarvestStats(volume=10, field_nonnull={"make": 10, "model": 10, "year": 10, "price": 2},
                         sample_raw_fields={})
    r = evaluate(cfg, stats, conn=None)
    assert r.alert and not r.fields_ok
    assert "price" in r.details["weak_fields"]


@pytest.mark.unit
def test_zero_volume_is_field_and_volume_drift():
    cfg = _cfg()
    stats = HarvestStats(volume=0, field_nonnull={}, sample_raw_fields={})
    r = evaluate(cfg, stats, conn=None)
    assert r.alert and not r.volume_ok and not r.fields_ok


@pytest.mark.unit
def test_schema_fingerprint_drift_via_registry():
    conn = connect(":memory:")
    migrate(conn)
    cfg = _cfg()
    healthy = {"make": "BMW", "model": "X1", "year": 2020, "price": 27950, "images": ["a"]}
    base_stats = HarvestStats(volume=5, field_nonnull={f: 5 for f in cfg.drift_baseline.required_fields},
                              sample_raw_fields=healthy)

    # first observation: registers baseline, no change
    r1 = evaluate(cfg, base_stats, conn=conn)
    assert r1.ok and not r1.schema_changed

    # same shape again: still no change
    r2 = evaluate(cfg, base_stats, conn=conn)
    assert r2.ok and not r2.schema_changed

    # portal redesign drops `price` from the page shape → fingerprint shifts → drift
    redesigned = {"make": "BMW", "model": "X1", "year": 2020, "images": ["a"]}
    drift_stats = HarvestStats(
        volume=5, field_nonnull={f: 5 for f in cfg.drift_baseline.required_fields},
        sample_raw_fields=redesigned,
    )
    r3 = evaluate(cfg, drift_stats, conn=conn)
    assert r3.alert and r3.schema_changed
    assert "schema_fp_changed" in r3.reason()


@pytest.mark.unit
def test_evaluate_volume_only_for_coordinator():
    from scrapers.intelligence.drift_gate import evaluate_volume
    cfg = _cfg(expected_min_volume=1000)
    # healthy full harvest clears the floor
    ok = evaluate_volume(cfg, 5000)
    assert ok.ok and ok.volume_ok and ok.fields_ok and not ok.schema_changed
    # collapsed harvest (selector broke) trips volume only — never a false field alarm
    bad = evaluate_volume(cfg, 12)
    assert bad.alert and not bad.volume_ok and bad.fields_ok
    assert "volume(12<1000)" in bad.reason()


@pytest.mark.unit
def test_stats_from_records_helper():
    records = [
        {"make": "Audi", "model": "A3", "year": 2020, "price": 21950},
        {"make": "Fiat", "model": "Panda", "year": 2014, "price": None},  # price missing
    ]
    stats = stats_from_records(records, ("make", "model", "year", "price"))
    assert stats.volume == 2
    assert stats.field_nonnull["make"] == 2 and stats.field_nonnull["price"] == 1
    assert stats.sample_raw_fields["make"] == "Audi"
