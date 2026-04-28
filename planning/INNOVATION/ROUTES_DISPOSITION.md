# CARDEX Routes — Fleet Disposition Intelligence

**Status:** Implemented — Sprint 36-39  
**Branch:** `sprint/36-routes-disposition`  
**Module:** `innovation/routes/` (Go, `cardex.eu/routes`)  
**API port:** 8504  
**CLI:** `cardex routes optimize | spread | batch`

---

## Executive Summary

Fleet managers at Arval, RCI Banque and Ayvens return ~2 million leasing vehicles per year across 6 EU/CH markets. Today, disposition decisions — auction, dealer sale, or cross-border export — are made with stale market data and static rules. A BMW 320d returning in France might fetch €24,000 locally, but €26,000 in the Netherlands after €800 transport and €0 intra-EU VAT: a net uplift of **€1,200 per vehicle**, or **€1.2 M on a 1,000-vehicle fleet**.

CARDEX Routes turns the live price spread (scraped daily from ~15 EU listing sites) into an automated, ranked disposition plan.

---

## Market Context

### The Disposition Problem

| Decision Factor | Current State | CARDEX Approach |
|---|---|---|
| Market price by country | Stale weekly/monthly reports | Live SQLite KG (daily scrape) |
| VAT/customs costs | Manual calculation | Tax Engine (Sprint 32) |
| Transport costs | Per-request quotes | Static carrier matrix, YAML-configurable |
| Dealer availability | Account manager knowledge | Active dealer count per country |
| Holistic ranking | Excel spreadsheet | Ranked DispositionPlan API |

### Fleet Managers at Scope

- **Arval** (BNP Paribas): ~500k returns/year, 6 markets
- **RCI Banque** (Renault Group): ~400k returns/year
- **Ayvens** (Société Générale): ~350k returns/year  
- **LeasePlan / ALD**: ~600k returns combined

Target addressable market: ~1.85M disposition decisions/year at an average CARDEX gain-share fee of ~€250/vehicle = **€460M annual fee potential** at full penetration.

---

## Architecture

### Component Map

```
SQLite KG (vehicle_record + dealer_entity)
      │
      ▼
SpreadCalculator ────────────────────────────────────────┐
  cohort price per country (make/model/year±1/km-bracket) │
                                                          │
Tax Engine (cardex.eu/tax)                               │
  intra-EU reverse charge: €0                            │
  EU→CH: 8.1% MWST + €500 customs                       │
  CH→EU: destination VAT + €400 customs                  │
                                                          ▼
TransportMatrix                                  Optimizer.Optimize()
  static defaults (Berlin/Paris hub distances)       ↓
  YAML override for real carrier rates        DispositionPlan
                                                Routes[] sorted by NetProfit
                                                BestRoute, TotalUplift
                                                          │
                                                          ▼
                                              BatchOptimizer
                                                per-destination cap: 20%
                                                fleet-level assignment
                                                          │
                                                          ▼
                                              HTTP API (:8504)
                                              POST /routes/optimize
                                              POST /routes/batch
                                              GET  /routes/spread
                                                          │
                                                          ▼
                                              cardex routes CLI
```

---

## Data Model

### DispositionRoute

```go
type DispositionRoute struct {
    FromCountry      string   // ISO 3166-1 alpha-2
    ToCountry        string
    Channel          Channel  // "dealer_direct" | "auction" | "export"
    EstimatedPrice   int64    // market median at destination (EUR cents)
    VATCost          int64    // irrecoverable VAT + customs (EUR cents)
    TransportCost    int64    // carrier cost (EUR cents)
    NetProfit        int64    // EstimatedPrice − VATCost − TransportCost
    TimeToSellDays   int      // estimated liquidation time
    AvailableDealers int      // active dealers in destination country
    Confidence       float64  // 0–1, based on cohort sample size
    Explanation      string   // human-readable narrative
}
```

### DispositionPlan

```go
type DispositionPlan struct {
    VehicleVIN     string
    Make           string
    Model          string
    Year           int
    MileageKm      int
    CurrentCountry string
    Routes         []DispositionRoute  // sorted by NetProfit desc
    BestRoute      DispositionRoute
    TotalUplift    int64               // BestRoute.NetProfit − local price
    ComputedAt     time.Time
}
```

---

## Market Spread Calculator

**Source:** Live SQLite KG — `vehicle_record JOIN dealer_entity`

**Cohort matching:**
1. `UPPER(make_canonical) = UPPER(?)` — exact make
2. `UPPER(model_canonical) LIKE UPPER('%model%')` — partial model match
3. `year BETWEEN (year−1) AND (year+1)` — ±1 year window for liquidity
4. Mileage bracket: 0-30k / 30-80k / 80k+
5. Optional fuel type filter

**Price metric:** `AVG(price_gross_eur)` per country. For production KGs with thousands of listings, this closely approximates the median.

**Confidence:** `1 − exp(−n/20)` where n = total samples. 20 listings → 0.63, 50 → 0.92, 100 → 0.99.

---

## VAT/Tax Logic

| Route | Regime | Cost |
|---|---|---|
| EU → EU (B2B, used vehicle) | Intra-community reverse charge | **€0** |
| EU → CH | Swiss MWST 8.1% + €500 customs | **~8.1% + €500** |
| CH → EU | Destination VAT + €400 customs | **~19–21% + €400** |
| Same country | No cross-border event | **€0** |

Source: Art. 20/138 Directive 2006/112/CE (intra-EU), Art. 146 + Swiss LIVA (CH).

---

## Transport Cost Matrix

Static defaults in EUR (carrier rate ~€1.50/km × road factor 1.3):

| Route | Cost | Basis |
|---|---|---|
| DE ↔ FR | €750 | Berlin–Paris ~1,050 km |
| DE ↔ ES | €1,500 | Berlin–Madrid ~2,250 km |
| DE ↔ NL | €450 | Berlin–Amsterdam ~640 km |
| DE ↔ BE | €500 | Berlin–Brussels ~750 km |
| DE ↔ CH | €600 | Berlin–Zurich ~860 km |
| FR ↔ ES | €900 | Paris–Madrid ~1,300 km |
| NL ↔ BE | €300 | Amsterdam–Brussels ~200 km |

**Override via YAML:** `innovation/routes/transport_costs.yaml` — add real carrier quotes per route.

---

## Batch Optimizer

**Concentration constraint:** No more than 20% of the fleet routed to a single destination country. Prevents saturating one market and depressing prices.

**Algorithm:**
1. Compute `DispositionPlan` for each vehicle independently.
2. Sort vehicles by descending best-unconstrained net profit (highest-value vehicles get first pick of destinations).
3. For each vehicle: assign best route whose destination count < cap. Fall back to next-best route if capped.
4. Report `CapConstraintApplied` count.

---

## Gain-Share Model

CARDEX charges a performance fee on **documented uplift**:

```
uplift     = actual_sale_price − local_baseline
fee        = uplift × fee_rate    (15–20%)
net_client = uplift − fee
```

Example: vehicle fetches €27,000 in NL vs €25,000 local baseline (FR).
- Uplift: €2,000
- CARDEX fee at 15%: €300
- Net client gain: €1,700

**Implementation:** `gainshare.go` — `CalculateGainShare(actual, baseline, rate)`. Used for post-sale invoicing.

---

## API Reference

Base URL: `http://localhost:8504` (env: `ROUTES_URL`)

### GET /health
```json
{"status": "ok", "db": "open", "time": "2026-04-18T10:00:00Z"}
```

### GET /routes/spread
```
?make=BMW&model=320d&year=2021[&km=45000&fuel=diesel]
```
→ `MarketSpread` with `prices_by_country_cents`, `best_country`, `spread_amount_cents`

### POST /routes/optimize
```json
{
  "make": "BMW",
  "model": "320d",
  "year": 2021,
  "mileage_km": 45000,
  "current_country": "FR",
  "vin": "WBAXXXXX",
  "channel": "dealer_direct"
}
```
→ `DispositionPlan` — 404 if no market data

### POST /routes/batch
```json
[
  {"make": "BMW", "model": "320d", "year": 2021, "mileage_km": 45000, "current_country": "FR"},
  {"make": "Renault", "model": "Clio", "year": 2020, "mileage_km": 62000, "current_country": "NL"}
]
```
→ `BatchPlan` with per-vehicle assignments and fleet summary

---

## CLI Reference

```bash
# Market spread (all countries)
cardex routes spread --make BMW --model 320d --year 2021 --km 45000

# Optimize single vehicle
cardex routes optimize --make BMW --model 320d --year 2021 \
  --km 45000 --country FR [--vin WBAAXXXX]

# Fleet batch from CSV
# CSV columns: vin,make,model,year,mileage_km,fuel_type,country
cardex routes batch --input fleet.csv --output plan.json
```

---

## Deployment

### Make targets

```bash
make routes-serve      # Start API on :8504 (ROUTES_DB_PATH required)
make routes-test       # Run test suite (35 tests, -race)
make routes-build      # Build routes-server binary
```

### Docker (planned)

```dockerfile
FROM golang:1.26-alpine AS builder
WORKDIR /app
COPY innovation/routes/ .
RUN go build -o routes-server ./cmd/routes-server/

FROM gcr.io/distroless/static:nonroot
COPY --from=builder /app/routes-server /routes-server
ENV ROUTES_DB_PATH=/data/discovery.db ROUTES_PORT=8504
EXPOSE 8504
ENTRYPOINT ["/routes-server"]
```

---

## Performance

| Operation | Typical latency |
|---|---|
| Market spread (5 countries, 100 listings) | < 10ms |
| Single optimize (5 countries × 3 channels) | < 15ms |
| Batch 100 vehicles | < 1.5s |
| Batch 1,000 vehicles | < 15s |

All operations are read-only SQLite queries. No external network calls in the hot path.

---

## Test Coverage

35 tests in `routes_test.go`:
- Transport costs: symmetric, DE→ES > DE→NL, YAML override, unknown pair penalty
- Tax engine: intra-EU zero, EU→CH 8.1%, CH→EU destination VAT, same country zero
- Market spread: correct prices, spread amount, confidence scaling, empty result
- Optimizer: FR→CH net profit, intra-EU zero VAT, CH VAT cost, sorted routes, empty plan, NetProfit formula
- Batch: 10-vehicle assignment, concentration constraint (≤20%), empty input, total uplift
- Gain-share: 15%, 20%, no-uplift zero fee, exact calculation, invalid rate error
- HTTP API: health, missing params 400, no-data 404, success 200, invalid JSON 400

---

## Roadmap

1. **Real-time carrier integration** — replace static matrix with live API calls to BCA Transport, Gefco, SEUR for spot rates.
2. **Time-to-sell ML model** — replace static estimates with a regression on historical listing velocity per (country, make, model, year_range).
3. **Trust tier weighting** — use `confidence_score` from `dealer_entity` to weight available dealers count by quality (silver/gold only).
4. **Pulse health filter** — exclude destination dealers with `health_tier = "critical"` from route recommendations.
5. **Gain-share ledger** — API endpoint to record post-sale actual prices and generate CARDEX invoices automatically.
6. **Multi-currency support** — CH routes in CHF with live EUR/CHF conversion.
