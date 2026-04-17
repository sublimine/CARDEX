"""
test_pipeline.py — Tests for data_pipeline.py.

Fixture: 100 BMW 3er 2020 DE listings spread over 60 days.
Expected: output CSV with exactly 60 rows (one per day).
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from data_pipeline import (
    SeriesKey,
    _year_bucket,
    aggregate_series,
    load_raw,
    make_fixture_db,
    run_pipeline,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_bmw_rows(n: int = 100, days: int = 60, start: str = "2025-01-01") -> list[dict]:
    """
    Generate n synthetic BMW 3er 2020 DE listings distributed across `days` days.
    Multiple listings on the same day are intentional — the pipeline aggregates them.
    """
    base = datetime.strptime(start, "%Y-%m-%d")
    rows = []
    for i in range(n):
        day = base + timedelta(days=i % days)
        rows.append({
            "vehicle_id": f"VEH{i:05d}",
            "dealer_id": "D001",
            "country_code": "DE",
            "make": "BMW",
            "model": "3er",
            "year": 2020,
            "price": 28000 + (i % 10) * 500,   # prices vary slightly
            "mileage": 30000 + i * 100,
            "indexed_at": day.strftime("%Y-%m-%d %H:%M:%S"),
        })
    return rows


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestYearBucket:
    def test_2020_width3(self):
        assert _year_bucket(2020, 3) == "2018-2020"

    def test_2021_width3(self):
        assert _year_bucket(2021, 3) == "2021-2023"

    def test_2019_width3(self):
        assert _year_bucket(2019, 3) == "2018-2020"


class TestSeriesKey:
    def test_filename_sanitizes_spaces(self):
        key = SeriesKey(country="DE", make="BMW", model="3er", year_range="2018-2020")
        assert key.to_filename() == "DE_BMW_3er_2018-2020.csv"

    def test_filename_sanitizes_special_chars(self):
        key = SeriesKey(country="FR", make="Renault", model="Mégane", year_range="2019-2021")
        fname = key.to_filename()
        # Should not contain é
        assert "é" not in fname
        assert fname.endswith(".csv")


class TestPipelineFixture:
    """Core test: 100 BMW listings across 60 days → 60-row CSV."""

    def test_60_day_output(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        out_dir = str(tmp_path / "timeseries")

        rows = _make_bmw_rows(n=100, days=60)
        make_fixture_db(db_path, rows)

        written = run_pipeline(db_path, out_dir, min_points=30)

        assert len(written) == 1, f"Expected 1 series file, got {len(written)}"

        df = pd.read_csv(written[0])
        assert len(df) == 60, f"Expected 60 rows (one per day), got {len(df)}"

    def test_csv_schema(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        out_dir = str(tmp_path / "timeseries")

        rows = _make_bmw_rows(n=100, days=60)
        make_fixture_db(db_path, rows)

        written = run_pipeline(db_path, out_dir, min_points=30)
        df = pd.read_csv(written[0])

        required_cols = {"date", "price_mean", "price_p25", "price_p75", "volume", "km_mean"}
        assert required_cols.issubset(set(df.columns)), f"Missing columns: {required_cols - set(df.columns)}"

    def test_price_statistics_monotonic(self, tmp_path):
        """p25 ≤ price_mean ≤ p75 for all rows."""
        db_path = str(tmp_path / "test.db")
        out_dir = str(tmp_path / "timeseries")

        rows = _make_bmw_rows(n=100, days=60)
        make_fixture_db(db_path, rows)

        written = run_pipeline(db_path, out_dir, min_points=30)
        df = pd.read_csv(written[0])

        # On days with single listing, p25=p50=p75; otherwise p25 ≤ mean ≤ p75.
        multi_day = df[df["volume"] > 1]
        if not multi_day.empty:
            assert (multi_day["price_p25"] <= multi_day["price_mean"] + 0.01).all()
            assert (multi_day["price_mean"] <= multi_day["price_p75"] + 0.01).all()

    def test_filename_contains_key(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        out_dir = str(tmp_path / "timeseries")

        rows = _make_bmw_rows(n=100, days=60)
        make_fixture_db(db_path, rows)

        written = run_pipeline(db_path, out_dir, min_points=30)
        fname = Path(written[0]).name

        assert "BMW" in fname
        assert "DE" in fname
        assert fname.endswith(".csv")

    def test_min_points_filter(self, tmp_path):
        """Series with < min_points days are discarded."""
        db_path = str(tmp_path / "test.db")
        out_dir = str(tmp_path / "timeseries")

        rows = _make_bmw_rows(n=20, days=20)  # only 20 days
        make_fixture_db(db_path, rows)

        written = run_pipeline(db_path, out_dir, min_points=30)
        assert len(written) == 0, "Should discard series with only 20 days when min=30"

    def test_volume_column(self, tmp_path):
        """Volume column reflects number of listings per day."""
        db_path = str(tmp_path / "test.db")
        out_dir = str(tmp_path / "timeseries")

        rows = _make_bmw_rows(n=100, days=60)
        make_fixture_db(db_path, rows)

        written = run_pipeline(db_path, out_dir, min_points=30)
        df = pd.read_csv(written[0])

        # 100 listings / 60 days ≈ 1-2 per day
        assert df["volume"].sum() == 100
        assert df["volume"].min() >= 1

    def test_empty_db(self, tmp_path):
        """Empty DB → no series written."""
        db_path = str(tmp_path / "empty.db")
        out_dir = str(tmp_path / "timeseries")

        make_fixture_db(db_path, [])
        written = run_pipeline(db_path, out_dir, min_points=30)
        assert written == []

    def test_dates_sorted(self, tmp_path):
        """Output CSV rows must be sorted ascending by date."""
        db_path = str(tmp_path / "test.db")
        out_dir = str(tmp_path / "timeseries")

        rows = _make_bmw_rows(n=100, days=60)
        make_fixture_db(db_path, rows)

        written = run_pipeline(db_path, out_dir, min_points=30)
        df = pd.read_csv(written[0], parse_dates=["date"])

        assert df["date"].is_monotonic_increasing
