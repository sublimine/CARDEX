"""fx_eur tests — honest FX → EUR (never invents a rate)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from scrapers.pipeline import fx_eur


@pytest.mark.unit
def test_eur_is_identity():
    assert fx_eur.to_eur(Decimal("18500"), "EUR", {"EUR": Decimal(1)}) == Decimal("18500")


@pytest.mark.unit
def test_configured_rate_applies():
    rates = {"EUR": Decimal(1), "CHF": Decimal("1.05")}
    assert fx_eur.to_eur(Decimal("10000"), "CHF", rates) == Decimal("10500.00")


@pytest.mark.unit
def test_unknown_currency_returns_none():
    assert fx_eur.to_eur(Decimal("1000"), "CHF", {"EUR": Decimal(1)}) is None


@pytest.mark.unit
def test_blank_or_missing_returns_none():
    assert fx_eur.to_eur(None, "EUR", {"EUR": Decimal(1)}) is None
    assert fx_eur.to_eur(Decimal("100"), "", {"EUR": Decimal(1)}) is None


@pytest.mark.unit
def test_case_insensitive_currency():
    assert fx_eur.to_eur(Decimal("100"), "eur", {"EUR": Decimal(1)}) == Decimal("100")


@pytest.mark.unit
def test_load_rates_from_env(monkeypatch):
    monkeypatch.setenv("FX_RATE_CHF", "1.07")
    monkeypatch.setenv("FX_RATE_GARBAGE", "not-a-number")
    rates = fx_eur.load_rates_from_env()
    assert rates["EUR"] == Decimal(1)
    assert rates["CHF"] == Decimal("1.07")
    assert "GARBAGE" not in rates  # invalid value skipped, not crashed
