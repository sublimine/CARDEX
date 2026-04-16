"""
serve.py — FastAPI server exposing Chronos-2 forecasting via HTTP.

Endpoints:
    POST /forecast   — forecast a series by (make, model, year_range, country)
    GET  /series     — list available series with metadata
    GET  /health     — liveness probe

Port: FORECAST_PORT env var (default 8503).

Usage:
    python serve.py
    FORECAST_PORT=8503 TIMESERIES_DIR=timeseries/ python serve.py
    uvicorn serve:app --host 0.0.0.0 --port 8503

Data contract:
    The server reads pre-computed CSVs from TIMESERIES_DIR.
    To generate CSVs first run: python data_pipeline.py --db discovery.db
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

import pandas as pd
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from forecaster import forecast_series

logger = logging.getLogger(__name__)

TIMESERIES_DIR = Path(os.getenv("TIMESERIES_DIR", "timeseries"))
FORECAST_PORT = int(os.getenv("FORECAST_PORT", "8503"))

app = FastAPI(
    title="CARDEX Chronos Forecast API",
    version="1.0.0",
    description="Vehicle price time-series forecasting via Chronos-2 mini (28M params).",
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


# ── Request / Response models ─────────────────────────────────────────────────

class ForecastRequest(BaseModel):
    make: str = Field(..., examples=["BMW"])
    model: str = Field(..., examples=["3er"])
    year_range: str = Field(..., examples=["2019-2021"])
    country: str = Field(..., examples=["DE"])
    horizon_days: int = Field(30, ge=1, le=365, examples=[30])


class ForecastPoint(BaseModel):
    date: str
    p10: float
    p50: float
    p90: float


class BacktestMetrics(BaseModel):
    mase: Optional[float]
    smape: Optional[float]
    held_out_n: int


class ForecastResponse(BaseModel):
    series_key: str
    horizon_days: int
    backend: str
    model: str
    series_length: int
    last_date: str
    last_price: float
    inference_seconds: float
    forecast: list[ForecastPoint]
    backtest: BacktestMetrics


class SeriesMetadata(BaseModel):
    series_key: str
    country: str
    make: str
    model: str
    year_range: str
    n_points: int
    date_start: str
    date_end: str
    last_price: float
    last_volume: int


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_csv_name(country: str, make: str, model: str, year_range: str) -> str:
    import re
    raw = f"{country}_{make}_{model}_{year_range}"
    return re.sub(r"[^\w\-]", "_", raw) + ".csv"


def _find_csv(req: ForecastRequest) -> Path:
    name = _build_csv_name(req.country, req.make, req.model, req.year_range)
    path = TIMESERIES_DIR / name
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Series not found: {name}. "
                   f"Run data_pipeline.py to generate CSV files.",
        )
    return path


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "timeseries_dir": str(TIMESERIES_DIR)}


@app.get("/series", response_model=list[SeriesMetadata])
async def list_series() -> list[SeriesMetadata]:
    """
    List all available time-series with metadata.
    Reads CSV headers + last row only — fast even with 1000+ series.
    """
    result: list[SeriesMetadata] = []
    csv_files = sorted(TIMESERIES_DIR.glob("*.csv"))

    for csv_path in csv_files:
        stem = csv_path.stem
        parts = stem.split("_", 3)  # country_make_model_yearrange
        if len(parts) < 4:
            continue
        country, make, model, year_range = parts[0], parts[1], parts[2], parts[3]

        try:
            df = pd.read_csv(csv_path, parse_dates=["date"])
            df = df.sort_values("date")
            n = len(df)
            if n == 0:
                continue
            result.append(SeriesMetadata(
                series_key=stem,
                country=country,
                make=make,
                model=model,
                year_range=year_range,
                n_points=n,
                date_start=str(df["date"].iloc[0].date()),
                date_end=str(df["date"].iloc[-1].date()),
                last_price=round(float(df["price_mean"].iloc[-1]), 2),
                last_volume=int(df["volume"].iloc[-1]),
            ))
        except Exception as exc:
            logger.warning("Could not read %s: %s", csv_path.name, exc)

    return result


@app.post("/forecast", response_model=ForecastResponse)
async def forecast(req: ForecastRequest) -> ForecastResponse:
    """
    Forecast vehicle prices for the requested series.

    The server reads the pre-computed CSV and runs Chronos-2 mini inference.
    Inference time: ~1-2s on CPU for Chronos-bolt-mini; <0.1s for statsforecast.
    """
    csv_path = _find_csv(req)
    try:
        result = forecast_series(str(csv_path), horizon_days=req.horizon_days)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Forecasting failed for %s", csv_path.name)
        raise HTTPException(status_code=500, detail=f"Forecasting error: {exc}")

    return ForecastResponse(
        series_key=result["series_key"],
        horizon_days=result["horizon_days"],
        backend=result["backend"],
        model=result["model"],
        series_length=result["series_length"],
        last_date=result["last_date"],
        last_price=result["last_price"],
        inference_seconds=result["inference_seconds"],
        forecast=[ForecastPoint(**p) for p in result["forecast"]],
        backtest=BacktestMetrics(**result["backtest"]),
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("Starting CARDEX Forecast API on port %d", FORECAST_PORT)
    logger.info("Timeseries dir: %s (%d CSVs)",
        TIMESERIES_DIR,
        len(list(TIMESERIES_DIR.glob("*.csv"))) if TIMESERIES_DIR.exists() else 0,
    )
    uvicorn.run(
        "serve:app",
        host="0.0.0.0",
        port=FORECAST_PORT,
        log_level="info",
        access_log=True,
    )
