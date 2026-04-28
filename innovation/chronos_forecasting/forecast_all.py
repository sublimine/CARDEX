"""
forecast_all.py — Batch mode: forecast every CSV in timeseries/ → forecasts/.

Usage:
    python forecast_all.py
    python forecast_all.py --timeseries timeseries/ --out forecasts/ --horizon 30
    python forecast_all.py --horizon 90 --workers 4

Environment:
    CHRONOS_MODEL   HuggingFace model ID (default: amazon/chronos-bolt-mini)
    CHRONOS_BACKEND "chronos" | "statsforecast" (default: auto-detect)

Notes:
    - CPU-only.  Chronos-bolt-mini: ~1-2s per series on modern CPU.
    - 1000 series × 2s ≈ 33 min.  Schedule as a nightly cron job.
    - Errors on individual series are logged but do not abort the batch.
    - Existing JSON files are overwritten.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from forecaster import forecast_series

logger = logging.getLogger(__name__)


def _forecast_one(
    csv_path: Path,
    out_dir: Path,
    horizon: int,
) -> tuple[str, bool, str]:
    """Forecast a single CSV and write JSON to out_dir. Returns (name, ok, msg)."""
    name = csv_path.stem
    out_path = out_dir / f"{name}.json"
    try:
        result = forecast_series(str(csv_path), horizon_days=horizon)
        out_path.write_text(json.dumps(result, indent=2))
        return name, True, f"{result['series_length']} pts → {horizon}d forecast"
    except Exception as exc:
        return name, False, str(exc)


def run_batch(
    timeseries_dir: str = "timeseries",
    out_dir: str = "forecasts",
    horizon: int = 30,
    workers: int = 1,
) -> dict:
    """
    Iterate over all CSVs in timeseries_dir, forecast each, write JSON to out_dir.

    Returns a summary dict: {total, succeeded, failed, elapsed_seconds}.
    """
    ts_path = Path(timeseries_dir)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    csv_files = sorted(ts_path.glob("*.csv"))
    if not csv_files:
        logger.warning("No CSV files found in %s", timeseries_dir)
        return {"total": 0, "succeeded": 0, "failed": 0, "elapsed_seconds": 0.0}

    logger.info(
        "Batch forecasting %d series (horizon=%dd, workers=%d)",
        len(csv_files), horizon, workers,
    )
    t0 = time.perf_counter()

    succeeded = 0
    failed = 0

    if workers <= 1:
        for i, csv_file in enumerate(csv_files, 1):
            name, ok, msg = _forecast_one(csv_file, out_path, horizon)
            if ok:
                succeeded += 1
                logger.info("[%d/%d] OK  %s — %s", i, len(csv_files), name, msg)
            else:
                failed += 1
                logger.warning("[%d/%d] ERR %s — %s", i, len(csv_files), name, msg)
    else:
        # Note: chronos-forecasting loads the model per thread.
        # For true parallelism with Chronos, prefer workers=1 and batch via cron sharding.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_forecast_one, csv_file, out_path, horizon): csv_file
                for csv_file in csv_files
            }
            for i, fut in enumerate(as_completed(futures), 1):
                name, ok, msg = fut.result()
                if ok:
                    succeeded += 1
                    logger.info("[%d/%d] OK  %s — %s", i, len(csv_files), name, msg)
                else:
                    failed += 1
                    logger.warning("[%d/%d] ERR %s — %s", i, len(csv_files), name, msg)

    elapsed = time.perf_counter() - t0
    summary = {
        "total": len(csv_files),
        "succeeded": succeeded,
        "failed": failed,
        "elapsed_seconds": round(elapsed, 1),
    }
    logger.info(
        "Batch complete: %d/%d succeeded in %.1fs",
        succeeded, len(csv_files), elapsed,
    )
    # Write summary manifest.
    (out_path / "_batch_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch forecast all time-series")
    parser.add_argument("--timeseries", default="timeseries", help="Input CSV directory")
    parser.add_argument("--out", default="forecasts", help="Output JSON directory")
    parser.add_argument("--horizon", type=int, default=30, help="Forecast horizon in days")
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers (1=sequential)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    summary = run_batch(args.timeseries, args.out, args.horizon, args.workers)
    print(json.dumps(summary, indent=2))
    sys.exit(0 if summary["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
