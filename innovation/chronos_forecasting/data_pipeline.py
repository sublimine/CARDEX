"""
data_pipeline.py — Extract vehicle price time-series from CARDEX SQLite KG.

Aggregates daily price statistics per (make, model, year_range, country) and
writes one CSV per series to the `timeseries/` output directory.

Usage:
    python data_pipeline.py --db /path/to/discovery.db --out timeseries/
    python data_pipeline.py --db discovery.db --min-points 30

Output CSV schema (one row per day):
    date,price_mean,price_p25,price_p75,volume,km_mean

Series are discarded when they have fewer than --min-points (default 30) rows.
File names: {country}_{make}_{model}_{year_range}.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Generator

import pandas as pd

logger = logging.getLogger(__name__)

# ── SQL ───────────────────────────────────────────────────────────────────────

_QUERY = """
SELECT
    date(vr.indexed_at)            AS day,
    de.country_code                AS country,
    vr.make_canonical              AS make,
    vr.model_canonical             AS model,
    vr.year                        AS year,
    vr.price_gross_eur             AS price_eur,
    vr.mileage_km                  AS mileage_km
FROM vehicle_record vr
JOIN dealer_entity de ON vr.dealer_id = de.dealer_id
WHERE
    vr.price_gross_eur IS NOT NULL
    AND vr.price_gross_eur > 500
    AND vr.price_gross_eur < 500000
    AND vr.make_canonical IS NOT NULL
    AND vr.model_canonical IS NOT NULL
    AND vr.year IS NOT NULL
    AND vr.year >= 1990
    AND de.country_code IN ('DE', 'FR', 'ES', 'BE', 'NL', 'CH', 'AT', 'IT')
ORDER BY day
"""


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SeriesKey:
    country: str
    make: str
    model: str
    year_range: str  # e.g. "2018-2020"

    def to_filename(self) -> str:
        safe = re.sub(r"[^\w\-]", "_", f"{self.country}_{self.make}_{self.model}_{self.year_range}")
        return f"{safe}.csv"


# ── Year bucketing ────────────────────────────────────────────────────────────

def _year_bucket(year: int, width: int = 3) -> str:
    """Return a year range bucket like '2018-2020' for width=3."""
    base = (year // width) * width
    return f"{base}-{base + width - 1}"


# ── Pipeline ──────────────────────────────────────────────────────────────────

def load_raw(db_path: str) -> pd.DataFrame:
    """Load all qualifying rows from the SQLite KG."""
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(_QUERY, conn)
    finally:
        conn.close()

    df["day"] = pd.to_datetime(df["day"])
    df["year_range"] = df["year"].apply(lambda y: _year_bucket(int(y)))
    return df


def aggregate_series(df: pd.DataFrame) -> dict[SeriesKey, pd.DataFrame]:
    """
    Group by (country, make, model, year_range, day) and compute daily stats.
    Returns a mapping from SeriesKey to a daily DataFrame.
    """
    series: dict[SeriesKey, pd.DataFrame] = {}

    grouped = df.groupby(["country", "make", "model", "year_range", "day"])

    agg = grouped["price_eur"].agg(
        price_mean="mean",
        price_p25=lambda x: x.quantile(0.25),
        price_p75=lambda x: x.quantile(0.75),
        volume="count",
    ).reset_index()

    km_agg = grouped["mileage_km"].mean().reset_index().rename(columns={"mileage_km": "km_mean"})
    agg = agg.merge(km_agg, on=["country", "make", "model", "year_range", "day"])

    for (country, make, model, year_range), grp in agg.groupby(
        ["country", "make", "model", "year_range"]
    ):
        key = SeriesKey(country=country, make=make, model=model, year_range=year_range)
        daily = grp[["day", "price_mean", "price_p25", "price_p75", "volume", "km_mean"]].copy()
        daily = daily.sort_values("day").reset_index(drop=True)
        daily["date"] = daily["day"].dt.strftime("%Y-%m-%d")
        daily = daily[["date", "price_mean", "price_p25", "price_p75", "volume", "km_mean"]]
        series[key] = daily

    return series


def run_pipeline(
    db_path: str,
    out_dir: str,
    min_points: int = 30,
) -> list[str]:
    """
    Full pipeline: load → aggregate → filter → write CSVs.

    Returns list of written file paths.
    """
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    logger.info("Loading raw data from %s", db_path)
    df = load_raw(db_path)
    logger.info("Loaded %d raw rows", len(df))

    series_map = aggregate_series(df)
    logger.info("Aggregated %d candidate series", len(series_map))

    written: list[str] = []
    skipped = 0

    for key, daily in series_map.items():
        if len(daily) < min_points:
            skipped += 1
            continue
        path = Path(out_dir) / key.to_filename()
        daily.to_csv(path, index=False)
        written.append(str(path))
        logger.debug("Written %s (%d rows)", path.name, len(daily))

    logger.info(
        "Wrote %d series, skipped %d (< %d datapoints)",
        len(written), skipped, min_points,
    )
    return written


# ── Fixture helpers (used by tests) ──────────────────────────────────────────

def make_fixture_db(db_path: str, rows: list[dict]) -> None:
    """
    Create a minimal SQLite DB with the relevant tables pre-populated.
    Used by tests to avoid needing a real CARDEX KG.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS dealer_entity (
            dealer_id    TEXT PRIMARY KEY,
            country_code TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS vehicle_record (
            vehicle_id     TEXT PRIMARY KEY,
            dealer_id      TEXT NOT NULL,
            make_canonical TEXT,
            model_canonical TEXT,
            year           INTEGER,
            price_gross_eur REAL,
            mileage_km     INTEGER,
            indexed_at     TIMESTAMP
        );
    """)

    cur.executemany(
        "INSERT OR IGNORE INTO dealer_entity (dealer_id, country_code) VALUES (?, ?)",
        [(r["dealer_id"], r["country_code"]) for r in rows],
    )
    cur.executemany(
        """INSERT INTO vehicle_record
           (vehicle_id, dealer_id, make_canonical, model_canonical,
            year, price_gross_eur, mileage_km, indexed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                r["vehicle_id"],
                r["dealer_id"],
                r["make"],
                r["model"],
                r["year"],
                r["price"],
                r["mileage"],
                r["indexed_at"],
            )
            for r in rows
        ],
    )
    conn.commit()
    conn.close()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="CARDEX time-series data pipeline")
    parser.add_argument("--db", required=True, help="Path to SQLite KG (discovery.db)")
    parser.add_argument("--out", default="timeseries", help="Output directory for CSV files")
    parser.add_argument(
        "--min-points", type=int, default=30,
        help="Minimum daily datapoints per series (default: 30)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    written = run_pipeline(args.db, args.out, args.min_points)
    print(f"Wrote {len(written)} series to {args.out}/")


if __name__ == "__main__":
    main()
