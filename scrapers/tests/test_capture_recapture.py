"""Capture-recapture (Chapman) — pure estimator tests (no network/DB)."""
from __future__ import annotations

import math

import pytest

from scrapers.intelligence.capture_recapture import chapman_estimate


@pytest.mark.unit
def test_chapman_known_value():
    # Arrange: two sources of 100, overlap 50.
    # Act
    e = chapman_estimate(100, 100, 50)
    # Assert: N̂ = 101*101/51 - 1 ≈ 199.02 ; union 150 ; coverage 150/199 ≈ 0.754
    assert math.isclose(e.estimate, (101 * 101) / 51 - 1, rel_tol=1e-9)
    assert e.observed_union == 150
    assert 0.74 < e.coverage < 0.76
    assert not e.trustworthy_complete


@pytest.mark.unit
def test_chapman_high_overlap_is_complete():
    # Heavy overlap → we've captured nearly the whole universe.
    e = chapman_estimate(100, 100, 95)
    assert e.coverage >= 0.95
    assert e.trustworthy_complete is True
    assert e.ci95_low >= e.observed_union  # CI floor never below what we already saw


@pytest.mark.unit
def test_more_overlap_means_smaller_universe_estimate():
    # Monotonicidad: a mayor solapamiento, menor universo estimado (más cobertura).
    low = chapman_estimate(1000, 1000, 100)
    high = chapman_estimate(1000, 1000, 800)
    assert low.estimate > high.estimate
    assert high.coverage > low.coverage


@pytest.mark.unit
def test_zero_overlap_not_estimable():
    # Fuentes disjuntas → no estimable; señal honesta, no un número inventado.
    e = chapman_estimate(500, 500, 0)
    assert e.estimate == float("inf")
    assert e.coverage == 0.0
    assert not e.trustworthy_complete


@pytest.mark.unit
def test_invalid_overlap_raises():
    with pytest.raises(ValueError):
        chapman_estimate(100, 50, 60)  # overlap > min(n1,n2)
    with pytest.raises(ValueError):
        chapman_estimate(-1, 10, 0)


@pytest.mark.unit
def test_standard_error_positive_and_ci_brackets_estimate():
    e = chapman_estimate(2000, 1500, 300)
    assert e.std_error > 0
    assert e.ci95_low <= e.estimate <= e.ci95_high
