# DEALER_PULSE — CARDEX PULSE: Dealer Health Score (Sprint 35)

**Status:** DELIVERED — Sprint 35  
**Branch:** `sprint/35-dealer-pulse`  
**Directories:** `discovery/internal/pulse/`, `discovery/cmd/pulse-service/`

---

## Overview

CARDEX PULSE computes a real-time **0–100 health score** for each dealer from
inventory-derived signals. It acts as a leading indicator **6–18 months ahead**
of traditional bank floorplan-lending risk assessments, which rely on 12–18-month-
lagged financial statements.

Seven signals are extracted directly from `vehicle_record` and combined via
configurable weighted arithmetic on normalised stress values.

---

## Architecture

```
SQLite (vehicle_record + dealer_entity)
        │
        ▼
 pulse.ComputeSignals()      ←── 7 SQL queries per dealer
        │
        ▼
 pulse.Score()               ←── weighted stress → 0-100 score
        │
        ├── pulse.SaveSnapshot()  → dealer_health_history (SQLite, migration v8)
        │
        └── HTTP handler  (:8504)
              GET /pulse/health/{dealer_id}
              GET /pulse/watchlist
              GET /pulse/trend/{dealer_id}
              GET /metrics  (Prometheus)

cardex pulse show <id>
cardex pulse watchlist [--tier] [--country]
  └── calls pulse-service REST API
```

---

## Seven Inventory-Derived Signals

| # | Signal | SQL source | Stress threshold |
|---|--------|-----------|-----------------|
| 1 | **Liquidation ratio** | removed/new in 14d | > 1.5 |
| 2 | **Price trend** | avg price %/week | < −5%/week |
| 3 | **Volume z-score** | weekly listings vs 90d baseline | \|z\| > 1.5 |
| 4 | **Time on market** | avg days since indexed_at (active) | rising |
| 5 | **ToM delta** | % change vs prior 30d | > 20% |
| 6 | **Composite score delta** | confidence_score change (14d) | < −10 pts |
| 7 | **Brand HHI** | Herfindahl-Hirschman Index of makes | > 0.5 |
| 7b | **Price vs market** | dealer avg / country avg | < 0.85 |

---

## Scoring Model

```
stress_i   ← normalised [0,1] per signal
health_score = 100 × (1 − Σ wᵢ × stress_i)
```

### Default Weights (`WeightConfig`)

| Signal | Weight |
|--------|--------|
| liquidation | 20% |
| price_trend | 15% |
| volume | 15% |
| time_on_market | 15% |
| composite_delta | 10% |
| brand_hhi | 10% |
| price_vs_market | 15% |
| **Total** | **100%** |

Override at runtime via `PULSE_WEIGHTS_PATH` (JSON file).

### Health Tiers

| Tier | Score Range |
|------|------------|
| healthy | ≥ 70 |
| watch | ≥ 50 |
| stress | ≥ 30 |
| critical | < 30 |

---

## REST API (port 8504)

### `GET /pulse/health/{dealer_id}`

On-demand scoring. Computes signals, scores, and returns the full
`DealerHealthScore` JSON. Does not persist to history automatically.

### `GET /pulse/watchlist`

Returns the most recent snapshot for each dealer whose latest score
is below the threshold.

Query parameters:
- `tier=watch|stress|critical` (default: `watch` → threshold 70)
- `country=DE` (optional ISO-3166-1 filter)

### `GET /pulse/trend/{dealer_id}`

Returns the last 30 `HistoryPoint` rows for a dealer, oldest-first.

### `GET /metrics`

Prometheus metrics:
- `cardex_pulse_critical_dealers_total` — gauge, dealers with score < 30
- `cardex_pulse_watch_dealers_total` — gauge, dealers with score < 70
- `cardex_pulse_score_compute_duration_seconds` — histogram

---

## CLI

```bash
# Show dealer health score
cardex pulse show 01HQ3F7X2...

# Show watchlist (worst-first)
cardex pulse watchlist --tier critical --country DE
cardex pulse watchlist --tier watch
```

Environment variable: `CARDEX_PULSE_URL` (default: `http://localhost:8504`)

---

## Database Schema

Migration version 8 adds `dealer_health_history`:

```sql
CREATE TABLE dealer_health_history (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  dealer_id    TEXT    NOT NULL REFERENCES dealer_entity(dealer_id),
  health_score REAL    NOT NULL,
  health_tier  TEXT    NOT NULL,
  signals_json TEXT    NOT NULL,
  computed_at  TEXT    NOT NULL
);
CREATE INDEX idx_dhh_dealer_time ON dealer_health_history(dealer_id, computed_at);
```

---

## Environment Variables (pulse-service)

| Variable | Default | Description |
|----------|---------|-------------|
| `PULSE_DB_PATH` | `./data/discovery.db` | SQLite KG path |
| `PULSE_ADDR` | `:8504` | HTTP bind address |
| `PULSE_WEIGHTS_PATH` | _(none)_ | JSON weight-override file |
| `PULSE_RETAIN_DAYS` | `90` | History retention days |

---

## Testing

```bash
cd discovery && GOWORK=off go test -race ./internal/pulse/...
```

20 tests covering:
- `TierFromScore` at all tier boundaries (5 tests)
- `Score` healthy dealer → score ≥ 70
- `Score` stressed dealer → score < 30 (all signals red)
- `BrandHHI` single-make = 1.0, four equal makes = 0.25
- `DetectTrend` improving / deteriorating / stable / insufficient history (4 tests)
- `CollectRiskSignals` liquidation, price erosion, no signals (3 tests)
- `EnsureTable` idempotent
- `SaveSnapshot` + `LoadHistory` ordered oldest-first
- `Watchlist` threshold filtering
- Default weights sum to 1.0

---

## Deployment

Run alongside the discovery-service on the same host (shares the SQLite WAL database):

```bash
PULSE_DB_PATH=/data/discovery.db \
PULSE_ADDR=:8504 \
./pulse-service
```

Cron: run a scoring sweep across all active dealers every 4 hours and persist
snapshots via `SaveSnapshot` to populate trend history.
