"""
test_serve.py — Integration tests for the FastAPI forecast server (serve.py).

Uses httpx.TestClient (via starlette.testclient) to test endpoints without
starting a real server.  The timeseries directory is mocked with a temporary
CSV fixture.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_csv(path: Path, n_days: int = 60, base_price: float = 28000.0) -> None:
    rng = np.random.default_rng(7)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="D")
    prices = base_price + np.arange(n_days) * 30.0 + rng.normal(0, 200, n_days)
    df = pd.DataFrame({
        "date":       [d.strftime("%Y-%m-%d") for d in dates],
        "price_mean": prices.round(2),
        "price_p25":  (prices - 500).round(2),
        "price_p75":  (prices + 500).round(2),
        "volume":     rng.integers(1, 4, n_days).tolist(),
        "km_mean":    (30000 + np.arange(n_days) * 50).tolist(),
    })
    df.to_csv(path, index=False)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def ts_dir(tmp_path, monkeypatch):
    """Patch TIMESERIES_DIR and write a synthetic CSV for BMW 3er DE."""
    ts = tmp_path / "timeseries"
    ts.mkdir()
    _write_csv(ts / "DE_BMW_3er_2018-2020.csv", n_days=60)
    return ts


@pytest.fixture()
def client(ts_dir, monkeypatch):
    """
    Build a TestClient against the FastAPI app with TIMESERIES_DIR patched.
    Skips if fastapi / httpx not available or if no forecasting backend is found.
    """
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")

    monkeypatch.setenv("TIMESERIES_DIR", str(ts_dir))

    # Re-import serve so it picks up the patched env var.
    import importlib
    import serve as serve_mod
    importlib.reload(serve_mod)

    from starlette.testclient import TestClient
    return TestClient(serve_mod.app)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestListSeries:
    def test_returns_list(self, client):
        resp = client.get("/series")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1

    def test_series_metadata_fields(self, client):
        resp = client.get("/series")
        item = resp.json()[0]
        for field in ("series_key", "country", "make", "model", "year_range",
                      "n_points", "date_start", "date_end", "last_price", "last_volume"):
            assert field in item, f"Missing field: {field}"

    def test_series_n_points(self, client):
        resp = client.get("/series")
        item = resp.json()[0]
        assert item["n_points"] == 60
        assert item["country"] == "DE"
        assert item["make"] == "BMW"


class TestForecast:
    @pytest.fixture(autouse=True)
    def skip_if_no_backend(self):
        try:
            import chronos  # noqa: F401
        except ImportError:
            try:
                import statsforecast  # noqa: F401
            except ImportError:
                pytest.skip("Neither chronos-forecasting nor statsforecast installed")

    def test_forecast_200(self, client):
        resp = client.post("/forecast", json={
            "make": "BMW",
            "model": "3er",
            "year_range": "2018-2020",
            "country": "DE",
            "horizon_days": 30,
        })
        assert resp.status_code == 200

    def test_forecast_structure(self, client):
        resp = client.post("/forecast", json={
            "make": "BMW", "model": "3er", "year_range": "2018-2020",
            "country": "DE", "horizon_days": 30,
        })
        data = resp.json()
        assert "forecast" in data
        assert "backtest" in data
        assert len(data["forecast"]) == 30

    def test_forecast_confidence_ordered(self, client):
        resp = client.post("/forecast", json={
            "make": "BMW", "model": "3er", "year_range": "2018-2020",
            "country": "DE", "horizon_days": 30,
        })
        for pt in resp.json()["forecast"]:
            assert pt["p10"] <= pt["p50"] + 1e-6
            assert pt["p50"] <= pt["p90"] + 1e-6

    def test_forecast_404_unknown_series(self, client):
        resp = client.post("/forecast", json={
            "make": "UNKNOWN", "model": "UNKNOWN", "year_range": "2000-2002",
            "country": "DE", "horizon_days": 30,
        })
        assert resp.status_code == 404

    def test_forecast_horizon_validation(self, client):
        resp = client.post("/forecast", json={
            "make": "BMW", "model": "3er", "year_range": "2018-2020",
            "country": "DE", "horizon_days": 0,  # invalid
        })
        assert resp.status_code == 422

    def test_forecast_horizon_max(self, client):
        resp = client.post("/forecast", json={
            "make": "BMW", "model": "3er", "year_range": "2018-2020",
            "country": "DE", "horizon_days": 366,  # exceeds max 365
        })
        assert resp.status_code == 422
