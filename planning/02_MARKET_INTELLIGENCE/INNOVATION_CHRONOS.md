# Innovation Track: Chronos-2 Time-Series Price Forecasting

**Status:** Implemented — Sprint 31  
**Branch:** `sprint/31-chronos-forecasting`  
**Directories:**
- `innovation/chronos_forecasting/` — Python forecasting service
- `frontend/terminal/cmd/cardex/forecast.go` — Go CLI integration

---

## Problem Statement

CARDEX indexes ~1M vehicle listings across 6 EU markets but has no forward-looking
price signal. Buyers and dealers currently see only historical prices; they cannot
answer: "Will this BMW 3er (2018-2020) be worth more in 30 days, or should I buy
now?"

Used-car prices follow structured patterns — seasonal demand, new-model launches,
fuel regulation cycles, macro shocks. A time-series foundation model can learn
these patterns from daily aggregated listing data without hand-crafted features.

---

## Architecture

### Data Pipeline (`data_pipeline.py`)

```
SQLite KG (vehicle_record + dealer_entity)
    → SQL: GROUP BY (country, make, model, year_range, date)
    → daily price_mean / price_p25 / price_p75 / volume / km_mean
    → one CSV per (country, make, model, year_range) series
```

**Year bucketing:** 3-year ranges anchored to 2018 epoch:
`bucket_start = ((year - 2018) // 3) * 3 + 2018`
→ 2018-2020, 2021-2023, 2024-2026, …

**Minimum threshold:** series with fewer than 30 daily data-points are discarded
(configurable via `--min-points`). This prevents noise-only series from degrading
forecast quality.

**CSV schema:**

| Column | Type | Description |
|--------|------|-------------|
| `date` | YYYY-MM-DD | Aggregation day |
| `price_mean` | float | Mean listing price (EUR) |
| `price_p25` | float | 25th percentile |
| `price_p75` | float | 75th percentile |
| `volume` | int | Number of active listings |
| `km_mean` | float | Mean odometer reading |

---

### Forecasting Engine (`forecaster.py`)

#### Primary backend: Chronos-2

- **Package:** `chronos-forecasting>=2.2.2` (PyPI)
- **Model:** `amazon/chronos-bolt-mini` (28M params, encoder-only transformer)
- **RAM:** ~200 MB (mini) / ~500 MB (base)
- **Inference:** 1–2 seconds on CPU for 30-day horizon
- **API:** `BaseChronosPipeline.from_pretrained(model, device_map="cpu")` →
  `pipeline.predict(context, prediction_length, num_samples=20)`
- **Quantiles:** median (p50) + empirical 10th/90th from sample ensemble
- Override model via `CHRONOS_MODEL` env var

#### Fallback backend: statsforecast

Activated automatically when `chronos-forecasting` is not importable. Zero ML
dependencies (~50 MB), pure statistical:

- **AutoETS** (season_length=7, additive trend+seasonality)
- **AutoARIMA** (season_length=7)
- p50: average of AutoETS and AutoARIMA medians
- p10/p90: AutoETS 80% prediction interval (scaled from ±1.28σ)

#### Backtest Protocol

- 20% held-out tail (min 7 days)
- **MASE** (Mean Absolute Scaled Error): `MAE(test, pred) / mean(|Δtrain|)`
  — MASE < 1.0 means model beats naïve baseline
- **sMAPE** (Symmetric MAPE): `200 * |y-ŷ| / (|y| + |ŷ|)` — scale-independent

---

### Forecast API (`serve.py`)

FastAPI on port 8503 (env: `FORECAST_PORT`).

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service status + timeseries_dir |
| `/series` | GET | List available series with metadata |
| `/forecast` | POST | Run forecast for a given series |

**POST /forecast request:**
```json
{
  "make": "BMW",
  "model": "3er",
  "year_range": "2018-2020",
  "country": "DE",
  "horizon_days": 30
}
```

**Response:** `ForecastResponse` with `forecast[{date, p10, p50, p90}]` array,
`backtest{mase, smape, held_out_n}`, `backend`, `last_price`, `inference_seconds`.

---

### Batch Mode (`forecast_all.py`)

```bash
python forecast_all.py --timeseries timeseries/ --out forecasts/ --horizon 30 --workers 1
```

- Discovers all CSVs in `timeseries/`
- Runs `forecast_series()` per file (threaded)
- Writes per-series `{stem}_forecast.json` + `_batch_summary.json`
- Note: `--workers 1` recommended when using Chronos (model loads once per worker)

---

### Go CLI (`cardex forecast`)

```
cardex forecast \
  --make BMW \
  --model "3er" \
  --year-min 2018 \
  --year-max 2020 \
  --country DE \
  --horizon 30 \
  [--spark]
```

Calls `POST /forecast` on the FastAPI service (default: `http://localhost:8503`,
override with `FORECAST_URL` env var). Renders:

- Series metadata (last price, last date, inference time)
- Forecast table: selected p10/p50/p90 rows at evenly-spaced intervals
- Trend indicator: ↑ / ↓ / → based on p50(horizon) vs last_price (±2% threshold)
- Confidence band at horizon: `€p10 – €p90`
- Percent change from last price to p50(horizon)
- Backtest MASE with ✓ / ⚠ baseline comparison
- `--spark`: Unicode block-character sparkline of p50 values (▁▂▃▄▅▆▇█)

---

## Deployment

### Docker (full stack with Chronos-2)

```bash
# Build
docker build -t cardex-forecast innovation/chronos_forecasting/

# Run (mount timeseries data volume)
docker run -p 8503:8503 \
  -v $(pwd)/data/timeseries:/data/timeseries \
  -e TIMESERIES_DIR=/data/timeseries \
  cardex-forecast
```

### Minimal (statsforecast only, ~100 MB)

```bash
pip install -r innovation/chronos_forecasting/requirements-minimal.txt
```

### Makefile targets

```bash
make forecast-pipeline   # SQLite → CSVs
make forecast-serve      # Start API on :8503
make forecast-test       # pytest suite
```

---

## RAM Budget

| Component | RAM |
|-----------|-----|
| Chronos-bolt-mini | ~200 MB |
| Chronos-bolt-base | ~500 MB |
| statsforecast | <50 MB |
| FastAPI + pandas | ~80 MB |
| **Total (mini)** | **~280 MB** |

Fits comfortably in 512 MB containers. For production, 1 GB recommended to handle
concurrent requests (the model is loaded once at startup and reused per worker).

---

## Roadmap

1. **Persistent caching** — cache forecast JSON by `(series_key, horizon, date)`;
   invalidate when the underlying CSV is updated by the pipeline.
2. **Scheduled refresh** — cron job: run `forecast_all.py` nightly after the
   extraction pipeline completes. Store results in a `forecasts/` directory.
3. **Frontend integration** — embed p10/p50/p90 chart in the b2b-dashboard
   vehicle detail page (React component consuming GET /series + POST /forecast).
4. **Multi-horizon output** — return 7d / 30d / 90d forecasts in a single request
   to reduce inference calls from the dashboard.
5. **Chronos-bolt-base** — upgrade to 200M param model if GPU available; the
   `CHRONOS_MODEL` env var makes this a one-line change.
