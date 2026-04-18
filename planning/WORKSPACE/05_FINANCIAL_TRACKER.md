# Sprint 45 — CARDEX Financial Tracker + P&L per Vehicle

**Branch:** `sprint/45-financial-tracker`
**Package:** `workspace/internal/finance/`
**Status:** Complete

---

## Objective

Provide per-vehicle and fleet-wide financial P&L tracking for dealer operations. Track acquisition cost, reconditioning, fees, and sale revenue in EUR with multi-currency support. Surface actionable alerts for underperforming inventory.

---

## Data Model

### `crm_transactions`

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | crypto/rand UUID |
| `tenant_id` | TEXT | multi-tenant isolation |
| `vehicle_id` | TEXT | references vehicle |
| `type` | TEXT | 12 types (see below) |
| `amount_cents` | INTEGER | always positive |
| `currency` | TEXT | default EUR |
| `vat_cents` | INTEGER | optional VAT component |
| `vat_rate` | REAL | e.g. 0.20 for 20% |
| `counterparty` | TEXT | supplier / buyer name |
| `reference` | TEXT | invoice / PO number |
| `date` | TEXT | YYYY-MM-DD |
| `notes` | TEXT | free text |
| `created_at` / `updated_at` | TEXT | RFC3339 |

**Transaction types:**

| Type | Category |
|---|---|
| `purchase` | cost |
| `transport` | cost |
| `reconditioning` | cost |
| `inspection` | cost |
| `registration` | cost |
| `insurance` | cost |
| `storage` | cost |
| `syndication_fee` | cost |
| `platform_fee` | cost |
| `tax` | cost |
| `other` | cost |
| `sale` | revenue |

### `crm_exchange_rates`

Stores configurable FX rates per currency pair and effective date. Queried with `ORDER BY valid_from DESC LIMIT 1` to find the most recent rate on or before the transaction date.

---

## P&L Engine

### Vehicle P&L (`computeVehiclePnL`)

Pure function — no DB dependency, injectable `rateFunc` for currency conversion.

```
GrossMargin   = TotalRevenue − TotalCost
MarginPct     = GrossMargin / TotalRevenue × 100
ROIPct        = GrossMargin / TotalCost × 100
DaysInStock   = SaleDate (or today) − EarliestPurchaseDate
CostPerDay    = TotalCost / DaysInStock
```

### Fleet P&L (`CalculateFleetPnL`)

Aggregates across all vehicles with transactions in `[from, to]`. Computes:
- Total cost / revenue / gross margin
- Average margin %
- Best and worst vehicles by gross margin
- Cost breakdown by transaction type

### Monthly P&L (`CalculateMonthlyPnL`)

Computes current month vs previous month. Derives:
- `RevGrowthPct = (currRev − prevRev) / prevRev × 100`
- `MarginGrowthPct = (currMargin − prevMargin) / |prevMargin| × 100`

---

## Automatic Alerts

| Alert | Type | Threshold | Severity |
|---|---|---|---|
| Negative gross margin (sold vehicle) | `negative_margin` | `GrossMargin < 0` | critical |
| Long stock duration (unsold vehicle) | `stock_too_long` | `DaysInStock ≥ 60` | warning |
| High reconditioning cost | `reconditioning_high` | `recond / purchase > 15%` | warning |

---

## Multi-Currency

- Base currency: **EUR**
- Supported: CHF, GBP (extensible via `crm_exchange_rates` table)
- Conversion: `amountEUR = amountCents × rate` where rate is fetched per `(fromCurrency, date)` pair
- Fallback: if no rate found, amount treated as EUR (no conversion) — graceful degradation

---

## HTTP API

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/vehicles/{id}/transactions` | Create transaction |
| GET | `/api/v1/vehicles/{id}/transactions` | List transactions |
| GET | `/api/v1/vehicles/{id}/pnl` | Vehicle P&L |
| GET | `/api/v1/fleet/pnl?from=&to=` | Fleet P&L (date range) |
| GET | `/api/v1/fleet/pnl/monthly?year=&month=` | Monthly P&L |
| GET | `/api/v1/fleet/alerts` | Active alerts |
| PUT | `/api/v1/transactions/{id}` | Update transaction |
| DELETE | `/api/v1/transactions/{id}` | Delete transaction |

All endpoints are tenant-scoped via `X-Tenant-ID` header (falls back to `"default"`).

---

## Prometheus Metrics

| Metric | Type | Description |
|---|---|---|
| `finance_transactions_total` | Counter | Transactions created |
| `finance_margin_cents` | Histogram | Gross margin per vehicle P&L call (EUR cents) |
| `finance_alerts_active` | Gauge | Active alerts across fleet |

Metrics registered once via `sync.Once` to prevent duplicate-registration panics in tests.

---

## Test Coverage (33 tests, `-race`)

| Group | Tests |
|---|---|
| CRUD | 8 — create defaults, invalid type, zero amount, list, list sorted, update, update not-found, delete |
| Vehicle P&L | 7 — empty, cost-only, positive margin, negative margin, DaysInStock, ROI, multi-currency |
| Fleet P&L | 4 — multi-vehicle, best/worst, cost-by-type, empty range |
| Monthly P&L | 4 — basic, with previous month, growth rates, empty month |
| Alerts | 4 — negative margin trigger, stock-too-long trigger, reconditioning-high trigger, no-alert clean |
| Exchange Rates | 3 — upsert, fallback (no rate), same-currency short-circuit |
| HTTP | 3 — create+list, vehicle P&L endpoint, alerts endpoint |

---

## Files

```
workspace/internal/finance/
├── types.go        — TransactionType enum, structs (Transaction, VehiclePnL, FleetPnL, MonthlyPnL, Alert)
├── schema.go       — DDL for crm_transactions + crm_exchange_rates; EnsureSchema()
├── store.go        — CRUD + ListByDateRange / ListByMonth / GetExchangeRate / UpsertExchangeRate
├── calculator.go   — computeVehiclePnL (pure), CalculateVehiclePnL, CalculateFleetPnL, CalculateMonthlyPnL
├── alerts.go       — AlertService.GetAlerts, checkVehicleAlerts (3 conditions)
├── metrics.go      — Prometheus counter / histogram / gauge, sync.Once init
├── handler.go      — Handler() with 8 routes, tenantFrom helper
└── finance_test.go — 33 tests
```
