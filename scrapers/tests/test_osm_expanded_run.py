"""Unit tests for osm_expanded_run._countries_to_run()."""
from __future__ import annotations

import os

import pytest

from scrapers.discovery.sources.osm_expanded_run import _countries_to_run


def test_default_returns_all_six(monkeypatch):
    monkeypatch.delenv("OSM_COUNTRIES", raising=False)
    result = _countries_to_run()
    assert set(result) == {"DE", "FR", "ES", "NL", "BE", "CH"}
    assert len(result) == 6


def test_env_filters_countries(monkeypatch):
    monkeypatch.setenv("OSM_COUNTRIES", "BE,NL,CH")
    result = _countries_to_run()
    assert result == ("BE", "NL", "CH")


def test_env_preserves_order(monkeypatch):
    monkeypatch.setenv("OSM_COUNTRIES", "ES,FR,BE")
    result = _countries_to_run()
    assert result == ("ES", "FR", "BE")


def test_env_normalizes_case(monkeypatch):
    monkeypatch.setenv("OSM_COUNTRIES", "be,nl")
    result = _countries_to_run()
    assert result == ("BE", "NL")


def test_env_strips_whitespace(monkeypatch):
    monkeypatch.setenv("OSM_COUNTRIES", " BE , NL , CH ")
    result = _countries_to_run()
    assert result == ("BE", "NL", "CH")


def test_empty_env_returns_all(monkeypatch):
    monkeypatch.setenv("OSM_COUNTRIES", "")
    result = _countries_to_run()
    assert set(result) == {"DE", "FR", "ES", "NL", "BE", "CH"}
