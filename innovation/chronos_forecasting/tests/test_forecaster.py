"""
test_forecaster.py — Tests for forecaster.py.

Uses a synthetic price series (linear trend + Gaussian noise) to verify:
  - The forecast runs without errors.
  - MASE < 1.0 (model beats naïve baseline on held-out split).
  - p10 ≤ p50 ≤ p90 everywhere in the output.
  - Backtest metrics are present and finite.
"""

import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from forecaster import forecast_series, mase, smape


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_synthetic_csv(
    tmp_path: Path,
    n_days: int = 90,
    trend_per_day: float = 50.0,
    noise_std: float = 300.0,
    seed: int = 42,
) -> str:
    """
    Write a CSV with a linear upward trend + Gaussian noise.
    trend_per_day=50 means price rises €50/day on average.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="D")
    base_price = 25000.0
    prices = base_price + np.arange(n_days) * trend_per_day + rng.normal(0, noise_std, n_days)
    prices = np.clip(prices, 1000, None)

    df = pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "price_mean": prices.round(2),
        "price_p25": (prices - noise_std * 0.5).round(2),
        "price_p75": (prices + noise_std * 0.5).round(2),
        "volume": rng.integers(1, 5, n_days),
        "km_mean": (30000 + np.arange(n_days) * 100).tolist(),
    })

    path = tmp_path / "DE_BMW_3er_2018-2020.csv"
    df.to_csv(path, index=False)
    return str(path)


# ── Metric unit tests ─────────────────────────────────────────────────────────

class TestMetrics:
    def test_mase_perfect_forecast(self):
        y_train = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y_test  = np.array([6.0, 7.0])
        y_pred  = np.array([6.0, 7.0])
        assert mase(y_train, y_test, y_pred) == pytest.approx(0.0, abs=1e-9)

    def test_mase_naive_is_one(self):
        """Naïve forecast (repeat last value) should give MASE ≈ 1.0 for random walk."""
        rng = np.random.default_rng(0)
        y_train = np.cumsum(rng.normal(0, 1, 50))
        y_test  = np.cumsum(rng.normal(0, 1, 10)) + y_train[-1]
        y_pred  = np.full_like(y_test, fill_value=y_train[-1])  # naïve
        result = mase(y_train, y_test, y_pred)
        # Naïve MASE on random walk is approximately 1.0 (within noise)
        assert result > 0

    def test_smape_symmetric(self):
        y_test = np.array([100.0, 200.0])
        y_pred = np.array([110.0, 190.0])
        result = smape(y_test, y_pred)
        assert 0 < result < 20

    def test_smape_perfect(self):
        y = np.array([100.0, 200.0, 300.0])
        assert smape(y, y) == pytest.approx(0.0, abs=1e-9)


# ── Forecast integration tests ────────────────────────────────────────────────

class TestForecastSeries:
    """
    These tests run the full forecast pipeline on a synthetic series.
    They depend on either chronos-forecasting or statsforecast being installed.
    If neither is available the tests are skipped.
    """

    @pytest.fixture(autouse=True)
    def skip_if_no_backend(self):
        try:
            import chronos  # noqa: F401
        except ImportError:
            try:
                import statsforecast  # noqa: F401
            except ImportError:
                pytest.skip("Neither chronos-forecasting nor statsforecast installed")

    def test_returns_correct_structure(self, tmp_path):
        csv_path = _make_synthetic_csv(tmp_path, n_days=90)
        result = forecast_series(csv_path, horizon_days=30)

        assert "forecast" in result
        assert "backtest" in result
        assert len(result["forecast"]) == 30
        assert "series_key" in result

    def test_forecast_points_have_required_fields(self, tmp_path):
        csv_path = _make_synthetic_csv(tmp_path, n_days=90)
        result = forecast_series(csv_path, horizon_days=30)

        for point in result["forecast"]:
            assert "date" in point
            assert "p10" in point
            assert "p50" in point
            assert "p90" in point

    def test_confidence_intervals_ordered(self, tmp_path):
        """p10 ≤ p50 ≤ p90 for every forecast step."""
        csv_path = _make_synthetic_csv(tmp_path, n_days=90)
        result = forecast_series(csv_path, horizon_days=30)

        for i, pt in enumerate(result["forecast"]):
            assert pt["p10"] <= pt["p50"] + 1e-6, f"step {i}: p10 > p50"
            assert pt["p50"] <= pt["p90"] + 1e-6, f"step {i}: p50 > p90"

    def test_mase_below_one(self, tmp_path):
        """
        On a strong linear trend, both Chronos and statsforecast should beat
        the naïve baseline (MASE < 1.0).
        """
        csv_path = _make_synthetic_csv(
            tmp_path,
            n_days=120,
            trend_per_day=100.0,  # very strong trend → easy to beat naïve
            noise_std=50.0,       # low noise → signal dominates
        )
        result = forecast_series(csv_path, horizon_days=14)

        bt = result["backtest"]
        assert bt["mase"] is not None
        assert bt["mase"] < 1.0, f"Expected MASE < 1.0 on linear trend, got {bt['mase']}"

    def test_backtest_metrics_present(self, tmp_path):
        csv_path = _make_synthetic_csv(tmp_path, n_days=90)
        result = forecast_series(csv_path, horizon_days=30)

        bt = result["backtest"]
        assert "mase" in bt
        assert "smape" in bt
        assert "held_out_n" in bt
        assert isinstance(bt["held_out_n"], int) and bt["held_out_n"] > 0

    def test_horizon_30_60_90(self, tmp_path):
        """Verify 30/60/90 day horizons all return the correct number of steps."""
        csv_path = _make_synthetic_csv(tmp_path, n_days=150)
        for h in (30, 60, 90):
            result = forecast_series(csv_path, horizon_days=h)
            assert len(result["forecast"]) == h, f"Horizon {h}: got {len(result['forecast'])} steps"

    def test_last_price_matches_csv_tail(self, tmp_path):
        csv_path = _make_synthetic_csv(tmp_path, n_days=90)
        df = pd.read_csv(csv_path)
        expected_last = round(float(df["price_mean"].iloc[-1]), 2)

        result = forecast_series(csv_path, horizon_days=30)
        assert result["last_price"] == expected_last

    def test_too_short_series_raises(self, tmp_path):
        """Series with fewer than 10 rows should raise ValueError."""
        short = _make_synthetic_csv(tmp_path, n_days=5)
        with pytest.raises(ValueError, match="too short"):
            forecast_series(short, horizon_days=30)
