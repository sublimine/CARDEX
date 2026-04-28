# 08 — CARDEX Check: Vehicle History Report Engine

Sprint 49. Backend-only: `workspace/internal/check/`.

---

## Scope

Free vehicle history reports for 6 countries (DE / FR / ES / BE / NL / CH) using **only** publicly accessible data sources. Rule R1: no invented endpoints, no simulated responses, clear scaffolds with documented blockers for unavailable registries.

---

## Architecture

```
GET /api/v1/check/{vin}          → Handler → Cache (hit?) → Engine → Providers (parallel)
GET /api/v1/check/{vin}/summary  → Handler → Engine (same flow, trimmed response)
```

### Package layout

| File | Purpose |
|---|---|
| `schema.go` | `check_cache` + `check_requests` DDL, `EnsureSchema` |
| `registry.go` | `RegistryProvider` interface, all shared domain types |
| `vin.go` | ISO 3779 validation, WMI table (~120 entries), NHTSA vPIC enrichment |
| `provider_nl.go` | **Live** — RDW Open Data (Socrata, public) |
| `provider_fr.go` | Scaffold — Histovec / SIV require professional access |
| `provider_be.go` | Scaffold — Car-Pass requires B2B contract |
| `provider_es.go` | Scaffold — DGT requires owner consent / professional access |
| `provider_de.go` | Scaffold — TÜV/DEKRA no public API; KBA recalls HTML only |
| `provider_ch.go` | Scaffold — MFK cantonal; ASTRA no structured API |
| `cache.go` | SQLite cache: 24h TTL for reports; cleanup goroutine |
| `ratelimit.go` | Sliding-window in-memory rate limiter (per-IP) |
| `report.go` | `Engine.GenerateReport` — parallel fetch, aggregation, mileage analysis |
| `metrics.go` | Prometheus counters + histograms (namespace `workspace_check_*`) |
| `handler.go` | HTTP handler: full report + summary; rate limiting wired in |
| `check_test.go` | 48 tests covering all components |

---

## VIN Decoding

### Validation (ISO 3779)
- 17 characters, no I / O / Q
- Check digit algorithm: transliterate → weight × position → sum mod 11 → compare position 9
- Characters validated against known transliteration table

### Local decode
- **WMI** (pos 1–3): ~120 real WMI entries; returns Manufacturer + Country ISO code
- **Model year** (pos 10): letter A–Y maps to 2010–2030 cycle; digits 1–9 map to 2001–2009
- **Plant code** (pos 11), **Serial number** (pos 12–17)

### NHTSA enrichment (non-fatal)
- `GET https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json`
- Extracts: Make, Model, ModelYear, BodyClass, FuelTypePrimary, DisplacementL, DriveType, PlantCountry
- If NHTSA fails: returns locally decoded info without error; no degraded user experience

---

## Registry Providers

### NL — RDW Open Data ✅ Live
- **Base URL**: `https://opendata.rdw.nl/resource`
- **Datasets**:
  - `m9d7-ebf2` — Gekentekende voertuigen (registered vehicles) — search by `voertuigidentificatienummer` via Socrata `$where`
  - `sgfe-77wx` — APK inspections — search by `kenteken` (plate, retrieved from step 1)
  - `8ys7-d773` — Stolen vehicles — search by `kenteken`
- **Rate limit**: 1 req/sec informal guideline (Socrata terms)
- **Limitation**: APK pass/fail field not directly available in sgfe-77wx; pass inferred from next-due-date presence

### FR — France ⚠️ Scaffold
- **Histovec**: interactive portal; no public API. Requires plate + SIV certificate data.
- **SIV**: restricted to ANTS-accredited professionals. Apply at `api.gouv.fr`.
- **Contrôle Technique (UTAC-OTC)**: commercial subscription at `utac.com`.
- **To enable**: ANTS professional API + SIRET registration required.

### BE — Belgium ⚠️ Scaffold
- **Car-Pass**: mileage certification; B2B API exists but requires paid contract with `car-pass.be`.
- **DIV**: government authority, not available to third parties.
- **To enable**: Car-Pass B2B agreement → `POST https://api.car-pass.be/check`.

### ES — Spain ⚠️ Scaffold
- **DGT**: requires owner's plate + DNI/NIE. Professional access needs Spanish CIF/NIF + DGT agreement.
- **ITV**: decentralised across 17 autonomous communities, no unified API.
- **To enable**: DGT B2B access per community.

### DE — Germany ⚠️ Scaffold
- **KBA Rückrufdatenbank**: HTML + Excel download only, no REST API.
- **TÜV / DEKRA**: each organisation holds own data, no central API. Consumer PDF reports only.
- **To enable**: negotiate data feed with TÜV Nord / TÜV Süd / DEKRA / GTÜ, or use commercial aggregator (CARFAX EU, AutoDNA).

### CH — Switzerland ⚠️ Scaffold
- **MFK**: cantonal (26 cantons), no centralised system. Each canton runs own portal.
- **MOFIS**: restricted to cantonal authorities.
- **ASTRA recalls**: HTML only, no structured API.
- **To enable**: per-canton MFK data access + ASTRA structured feed agreement.

---

## Report Aggregation

1. Validate VIN → check cache (SQLite, 24h TTL)
2. Decode VIN locally + NHTSA enrichment
3. Fan-out to all providers via `sync.WaitGroup` (parallel, non-blocking per provider)
4. Aggregate: merge Registrations, Inspections, Recalls, MileageRecords, TechnicalSpecs
5. Mileage consistency analysis:
   - Sort records chronologically
   - Flag rollback if `km[i] < km[i-1]` (and both > 0)
   - Flag high gap if annual rate > 50 000 km/year
6. Alerts: stolen flag, open recalls, mileage rollback, mileage high gap
7. Every provider consulted appears in `DataSources` with status: `success / error / unavailable / scaffold`
8. Cache result; emit Prometheus metrics

---

## HTTP API

### `GET /api/v1/check/{vin}`
Returns `VehicleReport` (full). Public, no auth middleware. Per-IP rate limit (10 req/hour anonymous, unlimited with `Authorization` header).

Response headers:
- `X-Cache-Hit: true|false`
- `X-Data-Sources: NL:success,FR:unavailable,...`

### `GET /api/v1/check/{vin}/summary`
Returns `SummaryReport` — VIN decode + alerts + mileage consistency only. Same rate limiting.

---

## Rate Limiting

`RateLimiter` uses sliding window over `[]time.Time` per IP, cleaned up every 5 minutes.
- Default: 10 requests / 1 hour for anonymous users
- Authenticated users (any valid `Authorization` header): unlimited
- Configurable via `NewRateLimiter(limit, window)` for other use-cases

---

## Metrics (Prometheus `workspace_check_*`)

| Metric | Type | Labels |
|---|---|---|
| `workspace_check_requests_total` | Counter | `cache_hit` |
| `workspace_check_provider_latency_seconds` | Histogram | `provider`, `country` |
| `workspace_check_provider_errors_total` | Counter | `provider`, `country`, `error_type` |
| `workspace_check_mileage_inconsistencies_total` | Counter | — |

---

## Cache Schema

```sql
CREATE TABLE check_cache (
    vin           TEXT PRIMARY KEY,
    report_json   BLOB NOT NULL,
    vin_info_json BLOB,
    fetched_at    TEXT NOT NULL,
    expires_at    TEXT NOT NULL          -- RFC3339, checked on read
);
CREATE TABLE check_requests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    vin           TEXT NOT NULL,
    ip            TEXT,
    tenant_id     TEXT,
    requested_at  TEXT NOT NULL,
    cache_hit     BOOLEAN NOT NULL DEFAULT 0
);
```
TTL: 24h for reports. Expired entries purged every hour by background goroutine.

---

## Test Coverage (48 tests)

| Area | Tests |
|---|---|
| VIN validation | 9 (short, long, I/O/Q, check digit, lowercase) |
| VIN decode | 5 (WMI BMW, year 2013, unknown WMI, serial, plant) |
| NHTSA enrichment | 3 (success, failure fallback, invalid VIN) |
| NL provider | 6 (SupportsVIN, Country, success, not found, inspections, not stolen) |
| Scaffold providers | 5 (FR, BE, ES, DE, CH → ErrProviderUnavailable) |
| Mileage consistency | 5 (normal, rollback, high gap, single record, zero skip) |
| Cache | 4 (set+get, miss, expired, overwrite) |
| Rate limiter | 4 (allow, block, different IPs, window expiry) |
| HTTP handler | 5 (valid VIN 200, invalid 400, cache hit header, rate limit, data sources header) |
| Integration | 2 (stolen alert, open recall alert) |

---

## Known Limitations & Future Work

1. **NL APK pass/fail**: `sgfe-77wx` dataset does not surface a direct pass/fail boolean in the public API. The current implementation infers pass from `vervaldatum_keuring_dt` presence. Validate against the RDW catalogue when field names evolve.

2. **Year ambiguity**: VIN position 10 letters A–H repeat with a 30-year period (1980/2010, 1981/2011, etc.). The decoder returns the 2010-cycle year; pre-2001 vehicles will show year+30.

3. **NL only live data**: The 5 other countries are scaffolded. Priority for activation: **BE (Car-Pass B2B)** for mileage history, then **FR (ANTS professional API)** for CT records.

4. **Recall aggregation**: A future RAPEX EU provider could aggregate recalls across all 6 countries from `ec.europa.eu/safety-gate` API in a single call, replacing country-specific scaffolds for recall data.
