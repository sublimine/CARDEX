"""
forecaster.py — Chronos-2 (or statsforecast fallback) price forecasting.

Chronos-2 (amazon/chronos-bolt-mini, 28M params) runs fully on CPU.
If chronos-forecasting is not installed, the module falls back to
statsforecast (AutoETS + AutoARIMA ensemble) — pure statistical, zero ML deps.

Usage:
    python forecaster.py --csv timeseries/DE_BMW_3er_2019-2021.csv --horizon 30
    python forecaster.py --csv ... --horizon 60 --output forecasts/

Environment:
    CHRONOS_MODEL   HuggingFace model ID (default: amazon/chronos-bolt-mini)
    CHRONOS_BACKEND "chronos" | "statsforecast" (default: auto-detect)
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Backend detection ─────────────────────────────────────────────────────────

CHRONOS_MODEL = os.getenv("CHRONOS_MODEL", "amazon/chronos-bolt-mini")
_BACKEND_OVERRIDE = os.getenv("CHRONOS_BACKEND", "auto")


def _detect_backend() -> str:
    if _BACKEND_OVERRIDE in ("chronos", "statsforecast"):
        return _BACKEND_OVERRIDE
    try:
        import chronos  # noqa: F401
        return "chronos"
    except ImportError:
        pass
    try:
        import statsforecast  # noqa: F401
        return "statsforecast"
    except ImportError:
        raise RuntimeError(
            "Neither chronos-forecasting nor statsforecast is installed.\n"
            "Install one of:\n"
            "  pip install chronos-forecasting   # Chronos-2 (ML, ~200MB)\n"
            "  pip install statsforecast          # pure statistical, zero ML deps"
        )


BACKEND: str = _detect_backend()
logger.info("Using forecasting backend: %s", BACKEND)


# ── Metrics ───────────────────────────────────────────────────────────────────

def mase(y_train: np.ndarray, y_test: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Absolute Scaled Error (scale = naive seasonal error on train)."""
    naive_error = np.mean(np.abs(np.diff(y_train)))
    if naive_error == 0:
        return float("nan")
    mae = np.mean(np.abs(y_test - y_pred))
    return float(mae / naive_error)


def smape(y_test: np.ndarray, y_pred: np.ndarray) -> float:
    """Symmetric Mean Absolute Percentage Error."""
    denom = (np.abs(y_test) + np.abs(y_pred)) / 2.0
    mask = denom > 0
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs(y_test[mask] - y_pred[mask]) / denom[mask]) * 100)


# ── Chronos-2 backend ─────────────────────────────────────────────────────────

def _forecast_chronos(
    values: np.ndarray,
    horizon: int,
    num_samples: int = 20,
) -> dict[str, list[float]]:
    """
    Run Chronos-2 (chronos-bolt-mini) inference on `values`.
    Returns {"p10": [...], "p50": [...], "p90": [...]}.
    """
    import torch
    from chronos import BaseChronosPipeline

    pipeline = BaseChronosPipeline.from_pretrained(
        CHRONOS_MODEL,
        device_map="cpu",
        torch_dtype=torch.float32,
    )
    context = torch.tensor(values, dtype=torch.float32).unsqueeze(0)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        forecast = pipeline.predict(
            context,
            prediction_length=horizon,
            num_samples=num_samples,
            limit_prediction_length=False,
        )

    # forecast shape: (batch=1, num_samples, horizon)
    samples = forecast[0].numpy()  # (num_samples, horizon)

    return {
        "p10": np.percentile(samples, 10, axis=0).tolist(),
        "p50": np.percentile(samples, 50, axis=0).tolist(),
        "p90": np.percentile(samples, 90, axis=0).tolist(),
    }


# ── statsforecast backend ─────────────────────────────────────────────────────

def _forecast_statsforecast(
    values: np.ndarray,
    horizon: int,
) -> dict[str, list[float]]:
    """
    Fallback: AutoETS + AutoARIMA ensemble via statsforecast.
    Confidence intervals approximated from forecast error.
    Returns {"p10": [...], "p50": [...], "p90": [...]}.
    """
    from statsforecast import StatsForecast
    from statsforecast.models import AutoARIMA, AutoETS

    n = len(values)
    uid = ["series"] * n
    ds = pd.date_range("2020-01-01", periods=n, freq="D")
    df = pd.DataFrame({"unique_id": uid, "ds": ds, "y": values.tolist()})

    sf = StatsForecast(
        models=[AutoETS(season_length=7), AutoARIMA(season_length=7)],
        freq="D",
        n_jobs=1,
    )
    fc = sf.forecast(df=df, h=horizon, level=[80])

    # Average predictions from both models.
    p50_ets = fc["AutoETS"].values
    p50_arima = fc["AutoARIMA"].values
    p50 = ((p50_ets + p50_arima) / 2.0).tolist()

    # Use 80% PI from AutoETS for p10/p90.
    lo80 = fc.get("AutoETS-lo-80", fc["AutoETS"]).values
    hi80 = fc.get("AutoETS-hi-80", fc["AutoETS"]).values

    return {
        "p10": lo80.tolist(),
        "p50": p50,
        "p90": hi80.tolist(),
    }


# ── Core forecast function ────────────────────────────────────────────────────

def forecast_series(
    csv_path: str,
    horizon_days: int = 30,
    held_out_frac: float = 0.2,
) -> dict[str, Any]:
    """
    Load a time-series CSV, run Chronos-2 (or fallback) forecasting, and
    compute backtest metrics (MASE, sMAPE) on the held-out tail.

    Returns a dict with:
        series_key, horizon_days, backend,
        forecast: [{date, p10, p50, p90}, ...],
        backtest: {mase, smape, held_out_n},
        last_price, last_date, series_length, inference_seconds
    """
    df = pd.read_csv(csv_path, parse_dates=["date"])
    df = df.sort_values("date").dropna(subset=["price_mean"])

    if len(df) < 10:
        raise ValueError(f"Series too short ({len(df)} rows) for forecasting")

    values = df["price_mean"].values.astype(float)
    dates = df["date"].values

    # ── Backtest (held-out split) ─────────────────────────────────────────────
    n_held = max(1, int(len(values) * held_out_frac))
    n_train = len(values) - n_held

    train_vals = values[:n_train]
    test_vals = values[n_train:]

    t0 = time.perf_counter()
    if BACKEND == "chronos":
        bt_fc = _forecast_chronos(train_vals, n_held)
    else:
        bt_fc = _forecast_statsforecast(train_vals, n_held)
    bt_time = time.perf_counter() - t0

    bt_pred = np.array(bt_fc["p50"])
    backtest_metrics = {
        "mase": mase(train_vals, test_vals, bt_pred),
        "smape": smape(test_vals, bt_pred),
        "held_out_n": n_held,
    }

    # ── Full-series forecast ──────────────────────────────────────────────────
    t0 = time.perf_counter()
    if BACKEND == "chronos":
        fc = _forecast_chronos(values, horizon_days)
    else:
        fc = _forecast_statsforecast(values, horizon_days)
    fc_time = time.perf_counter() - t0

    last_date = pd.Timestamp(dates[-1])
    future_dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=horizon_days, freq="D")

    forecast_rows = [
        {
            "date": str(d.date()),
            "p10": round(float(fc["p10"][i]), 2),
            "p50": round(float(fc["p50"][i]), 2),
            "p90": round(float(fc["p90"][i]), 2),
        }
        for i, d in enumerate(future_dates)
    ]

    series_key = Path(csv_path).stem

    return {
        "series_key": series_key,
        "horizon_days": horizon_days,
        "backend": BACKEND,
        "model": CHRONOS_MODEL if BACKEND == "chronos" else "statsforecast-ensemble",
        "series_length": len(df),
        "last_date": str(last_date.date()),
        "last_price": round(float(values[-1]), 2),
        "inference_seconds": round(bt_time + fc_time, 3),
        "forecast": forecast_rows,
        "backtest": {
            **backtest_metrics,
            "mase": round(backtest_metrics["mase"], 4) if not math.isnan(backtest_metrics["mase"]) else None,
            "smape": round(backtest_metrics["smape"], 4) if not math.isnan(backtest_metrics["smape"]) else None,
        },
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Chronos-2 vehicle price forecasting")
    parser.add_argument("--csv", required=True, help="Input time-series CSV")
    parser.add_argument("--horizon", type=int, default=30, help="Forecast horizon in days")
    parser.add_argument("--output", default=None, help="Output JSON path (stdout if omitted)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    result = forecast_series(args.csv, args.horizon)
    payload = json.dumps(result, indent=2)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(payload)
        logger.info("Written to %s", args.output)
    else:
        print(payload)


if __name__ == "__main__":
    main()
