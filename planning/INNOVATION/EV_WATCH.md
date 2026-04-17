# EV Watch — Battery Anomaly Signal

**Sprint:** 33  
**Branch:** `sprint/33-ev-watch`  
**Status:** Complete

## Problem

~2 million EVs return from leasing in the EU between 2025–2027. Dealers lack standardised battery
health (SoH) data. Listings with degraded batteries are priced identically to healthy units,
creating information asymmetry that harms buyers.

## Approach

Cohort-normalised price z-scores as a proxy for SoH degradation.

**Hypothesis:** A significantly underpriced EV within its make/model/year/country cohort is a weak
signal of reduced range or degraded battery — the seller discounts to compensate for the defect.

**Method:**
1. Load all EV listings (`fuel_type IN ('electric', 'hybrid_plugin', 'plug_in_hybrid')`).
2. Group by cohort: `(make, model, year, country)`.
3. Skip cohorts with fewer than 20 listings (insufficient statistical power).
4. OLS regression: `price ~ mileage_km` per cohort — adjusts for odometer bias.
5. Compute residuals: `residual = actual_price - predicted_price`.
6. Z-score of residuals: `z = (residual - mean_residual) / stddev_residuals`.
7. Flag: `z < -1.5` → anomaly; `z < -2.0` → severe.

## Thresholds

| Threshold | Signal | EstimatedSoH |
|-----------|--------|--------------|
| z < -2.0  | Severe — possible battery degradation | `suspicious` |
| -2.0 ≤ z < -1.5 | Moderate — below cohort average | `below_average` |
| z ≥ -1.5  | Normal | `normal` |

Boundaries are strict (`<`, not `≤`). A listing at exactly z = -2.0 is `below_average`.

## Confidence Score

`confidence = min(1.0, cohort_size / 100.0)`

Saturates at 100 listings. At 20 listings (minimum), confidence is 0.20. Buyers should weight
small-cohort flags accordingly.

## Architecture

```
quality-service (cron: 24h)
  └─ ev_watch.Analyzer.RunAnalysis()
       ├─ loadEVListings()      — vehicle_record JOIN dealer_entity WHERE fuel_type IN (...)
       ├─ groupByCohort()       — key: (make, model, year, country)
       ├─ analyzeOneCohort()    — OLS → z-scores → EVAnomalyScore slice
       └─ upsert ev_anomaly_scores  — UNIQUE(vehicle_id) ON CONFLICT DO UPDATE

HTTP API (on /metrics mux, port :9092)
  ├─ GET  /ev-watch/anomalies  — filtered list, default anomaly_only=true
  ├─ GET  /ev-watch/cohort     — aggregate stats for a make/model
  └─ POST /ev-watch/run        — trigger on-demand analysis

CLI (cardex ev-watch)
  ├─ list    — ANSI table with SoH colour badges
  └─ cohort  — stats panel + ASCII z-score histogram
```

## Prometheus Alerts

```yaml
- alert: EVWatchSevereAnomaly
  expr: increase(cardex_ev_watch_severe_anomaly_total[1h]) > 0
  labels:
    severity: warning
  annotations:
    summary: "New EV listings with suspected battery degradation detected"
```

The `severe_anomaly_total` counter increments when a listing satisfies both:
- `z < -2.0`
- `cohort_size >= 30` (enough data for high-confidence signal)

## Limitations & Roadmap

- **Correlation, not causation.** Low price may reflect cosmetic damage, accident history, or
  motivated seller — not battery degradation. EV Watch provides a triage signal, not a diagnosis.
- **No OBD/BMS data.** A direct SoH reading from the battery management system would supersede
  this heuristic. Roadmap: ingest third-party battery test certificates (AVILOO, DEKRA).
- **Model granularity.** Some cohorts (rare models, small markets) remain below the 20-listing
  threshold. Lowering the threshold increases noise; raising it reduces coverage. 20 is the
  current balance point.
- **Currency normalisation.** All prices are stored as EUR cents after V19 currency normalisation.
  Cross-border distortions (VAT, import duty) may inflate z-scores for grey-market imports.
- **Future:** integrate WLTP range data to normalise price by `(price / rated_range_km)` instead
  of raw price; compute range-adjusted z-scores for better SoH proxy.
