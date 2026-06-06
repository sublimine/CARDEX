"""Versioned extraction-config store — load / round-trip / validation."""
from __future__ import annotations

import pytest

from scrapers.portals import config as cfgmod
from scrapers.portals.config import ExtractionConfig, from_dict, to_dict


@pytest.mark.unit
def test_load_reference_config_autotrack():
    cfg = cfgmod.load("autotrack.nl")
    assert cfg is not None
    assert cfg.source_key == "autotrack.nl" and cfg.country == "NL"
    assert cfg.strategy == "portal_paginated"
    assert cfg.pagination.page_size == 30 and cfg.pagination.max_pages == 7500
    assert cfg.extraction.method == "jsonld"
    assert cfg.extraction.field_map["make"] == "brand.name"
    assert cfg.drift_baseline.expected_min_volume == 1000   # production full-harvest floor
    assert "price" in cfg.drift_baseline.required_fields


@pytest.mark.unit
def test_reference_configs_present():
    keys = cfgmod.list_configs()
    assert "autotrack.nl" in keys and "viabovag.nl" in keys


@pytest.mark.unit
def test_round_trip_dict_preserves_fields():
    cfg = cfgmod.load("autotrack.nl")
    again = from_dict(to_dict(cfg))
    assert again == cfg                       # frozen dataclasses compare by value
    assert isinstance(again.drift_baseline.required_fields, tuple)


@pytest.mark.unit
def test_unknown_strategy_rejected():
    with pytest.raises(ValueError):
        ExtractionConfig(source_key="x.nl", country="NL", strategy="telepathy")


@pytest.mark.unit
def test_missing_source_returns_none():
    assert cfgmod.load("does-not-exist.invalid") is None
