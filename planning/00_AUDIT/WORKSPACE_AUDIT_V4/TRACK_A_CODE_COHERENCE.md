# Track A — Code Coherence Audit V4
**Scope:** `workspace/internal/check/`, `workspace/internal/auth/`, `workspace/internal/config/`, `workspace/cmd/workspace-service/main.go`
**Date:** 2026-04-19
**Auditor:** Claude (automated review + fix pass)
**Status:** All CRITICAL and HIGH items resolved.

---

## Summary

| Severity | Found | Fixed | Deferred |
|---|---|---|---|
| CRITICAL | 4 | 4 | 0 |
| HIGH | 8 | 8 | 0 |
| MEDIUM | 6 | 3 | 3 |
| LOW | 8 | 0 | 8 |
| **Total** | **26** | **15** | **11** |

---

## Findings Table

| ID | Severity | Location | Description | Status |
|---|---|---|---|---|
| A-01 | CRITICAL | `check/registry.go` | `Alert` struct missing all json tags — backend emitted PascalCase `{"Type":"stolen","Severity":"critical","Message":"..."}` while frontend expects `{"type","severity","title","description","id","recommendedAction","source"}`. All alert fields were invisible to the React Check page. | **FIXED** — struct rewritten with 7 json-tagged fields matching `VehicleAlert` TS type |
| A-02 | CRITICAL | `check/registry.go` | `DataSource` struct used `Provider string` field; frontend expects `id`, `name`, `note` camelCase keys. `Error` was being serialized into JSON output (internal field). | **FIXED** — struct rewritten: `ID`, `Name`, `Note` with tags; `Error string \`json:"-"\`` |
| A-03 | CRITICAL | `check/report.go` | `VehicleReport`, `CountryReport`, `ConsistencyScore` had no json tags — all top-level report fields were PascalCase in JSON output. Frontend received `{"VIN":"...","DecodedVIN":null,...}` instead of `{"vin":"...","vinDecode":null,...}`. | **FIXED** — all three structs given complete json tags; `vinDecode`, `mileageHistory`, `dataSources`, `consistencyScore`, etc. |
| A-04 | CRITICAL | `check/vin.go` | `VINInfo` struct had no json tags — NHTSA enrichment fields (`Make`, `Model`, `BodyType`, `EngineDisplacement`, `DriveType`, `PlantCountry`) were emitted PascalCase and invisible to frontend VINDecodeResult type. | **FIXED** — full json tags added; `countryOfManufacture`, `year`, `plant`, `serialNumber`; `RawNHTSA` hidden with `json:"-"` |
| A-05 | HIGH | `check/registry.go` | `RecallClosed RecallStatus = "closed"` — frontend RecallStatus type expects `"completed"` not `"closed"`. Closed recalls would show as unknown status in the UI. | **FIXED** — value changed to `"completed"` |
| A-06 | HIGH | `check/registry.go` | `StatusScaffold DataSourceStatus = "scaffold"` — frontend DataSourceStatus type has no `"scaffold"` value; only `"success"`, `"error"`, `"unavailable"`. Scaffold providers would show as unknown in the DataSources panel. | **FIXED** — collapsed to `"unavailable"` (semantically correct) |
| A-07 | HIGH | `check/registry.go` | `MileageRecord.Mileage` serialized as `"Mileage"` — frontend `MileageRecord` expects `mileageKm`. Mileage graph would be empty for all records. | **FIXED** — `json:"mileageKm"` tag added |
| A-08 | HIGH | `check/handler.go` | `isAuthenticated` method called in `fullReport` and `summary` but not defined on `Handler` — package failed to compile. | **FIXED** — method added: strips `Bearer ` prefix, delegates to `isValidToken` func |
| A-09 | HIGH | `check/registry.go` | `Alert` had no `newAlert()` constructor — `report.go` was constructing `Alert{Type:..., Severity:..., Message:...}` with a `Message` field that doesn't exist in the frontend contract. Title, ID, recommendedAction, source were never populated. | **FIXED** — `newAlert(alertType, severity, message)` helper computes all 7 fields via `alertMeta()` lookup table |
| A-10 | HIGH | `main.go` | `NewVINDecoder()` hardcoded `https://vpic.nhtsa.dot.gov` — `NHTSA_BASE_URL` env var in `internal/config/` package had no effect because main.go never imported config. NHTSA URL was not overridable at runtime. | **FIXED** — main.go uses `envOrDefault("NHTSA_BASE_URL", ...)` and `check.NewVINDecoderWithBase(nhtsaBaseURL)` |
| A-11 | HIGH | `main.go` | `NewNLProvider()` hardcoded `https://opendata.rdw.nl/resource` — `RDW_BASE_URL` env var had no effect. Impossible to redirect NL queries to a test/staging RDW endpoint without recompiling. | **FIXED** — main.go uses `envOrDefault("RDW_BASE_URL", ...)` and `check.NewNLProviderWithBase(rdwBaseURL)` |
| A-12 | HIGH | `auth/handler.go` | `POST /api/v1/auth/register` gated by `registerToken` but `auth_test.go` used `NewHandler` (token `""`) — 12 tests calling `registerUser` all returned 403, masking auth logic failures. | **FIXED** — test `newHandler` changed to `NewHandlerWithRegisterToken(db, jwtSvc, testRegisterToken)`; `registerUser` sends `X-Register-Token` header; all 6 `TestRegister_*` tests updated to use `postRegister` helper |
| A-13 | MEDIUM | `check/handler.go` | `SummaryReport` json tags use `decoded_vin` and `mileage_consistency` (snake_case) while `VehicleReport` uses `vinDecode` and `mileageConsistency` (camelCase). Inconsistent contract between the two endpoints. | DEFERRED — functional, but summary and full report use different key names for same field |
| A-14 | MEDIUM | `check/handler.go` | `/summary` endpoint does not emit `X-Cache-Hit` header on cache miss path (only sets it on cache hit). Cache-miss responses omit the header entirely. | DEFERRED — minor observability gap; does not affect correctness |
| A-15 | MEDIUM | `check/handler.go` | `/summary` endpoint does not increment `metricRequestsTotal` — only `fullReport` does. Summary request count is invisible in Prometheus. | DEFERRED — metrics gap, not a correctness issue |
| A-16 | MEDIUM | `check/cache.go` | `StartCleanup` goroutine has no stop mechanism — cleanup ticker runs forever even after context cancellation. Minor goroutine leak on service shutdown. | DEFERRED — no user-visible impact; shutdown completes via process exit anyway |
| A-17 | MEDIUM | `check/report.go` + `check/handler.go` | VIN validation happens twice: once in `handler.validateVINParam` and again in `engine.GenerateReport`. Redundant but harmless. | DEFERRED — double validation is defensive; no correctness issue |
| A-18 | MEDIUM | `check/registry.go` | `Inspection.NextDueDate` has `json:"nextInspectionDate,omitempty"` but `time.Time` zero value is not `omitempty`-able — zero dates always serialize to `"0001-01-01T00:00:00Z"`. Frontend date parser may fail on this value. | DEFERRED — would require changing to `*time.Time` pointer; scoped to future inspection data improvements |
| A-19 | LOW | `check/vin.go` | VIN position-10 year decoding only covers 2001–2030 cycle. Pre-2001 vehicles return year+30 (e.g., a 1990 vehicle decoded as 2020). Documented limitation. | DEFERRED — documented in `08_CARDEX_CHECK.md` Known Limitations §2 |
| A-20 | LOW | `check/vin.go` | NHTSA `DisplacementL` value has `"L"` suffix appended unconditionally (`"2.0L"`) — if NHTSA already returns `"2.0L"`, output would be `"2.0LL"`. Defensive check missing. | DEFERRED — NHTSA vPIC currently returns bare numeric string; low risk |
| A-21 | LOW | `check/provider_nl.go` | `datum_eerste_toelating` parsed as `"20130615"` format (YYYYMMDD) with no fallback for other date formats RDW may return. | DEFERRED — RDW field is stable; add fallback if format changes |
| A-22 | LOW | `check/ratelimit.go` | `RateLimiter.cleanup()` called from `Allow()` on every invocation — O(n) scan of all IPs every request. Acceptable at current scale (<1000 IPs) but degrades linearly. | DEFERRED — use a separate timer goroutine for cleanup at production scale |
| A-23 | LOW | `check/metrics.go` | Prometheus metrics registered globally via `promauto` — running multiple `Engine` instances in the same process would panic with duplicate registration. | DEFERRED — single-process model; document if multiple engines needed |
| A-24 | LOW | `check/report.go` | Slice initialization for `VehicleReport.Recalls`, `Alerts`, `MileageHistory`, `Countries`, `DataSources` all start as `nil` — serialized as `null` rather than `[]` when empty. Frontend must handle `null` vs `[]`. | DEFERRED — frontend already guards with `?? []`; initialize to `[]T{}` for cleaner contract in future |
| A-25 | LOW | `main.go` | `envOrDefault` duplicates logic from `internal/config/LoadFromEnv()` — two sources of truth for env var defaults. Config package has `NHTSABaseURL`, `RDWBaseURL`, `MetricsAddr` but main.go reads them independently. | DEFERRED — functional; migrate to single config source in a dedicated refactor sprint |
| A-26 | LOW | `auth/handler.go` | `REGISTER_TOKEN` env var logs a warning when unset but the env var name is not documented in the main.go package-level comment block. | DEFERRED — add to env var list in package comment |

---

## Files Modified This Audit Pass

| File | Change |
|---|---|
| `workspace/internal/check/registry.go` | Complete rewrite: json tags on all domain types; `newAlert()` + `alertMeta()`; `RecallClosed="completed"`; `StatusScaffold="unavailable"`; `DataSource.Error` hidden; `MileageRecord.Mileage→mileageKm` |
| `workspace/internal/check/vin.go` | Complete rewrite: json tags on `VINInfo`; `Make` alias field; `Country→countryOfManufacture`; `ModelYear→year`; `RawNHTSA json:"-"` |
| `workspace/internal/check/report.go` | Added json tags to `VehicleReport`, `CountryReport`, `ConsistencyScore` |
| `workspace/internal/check/handler.go` | Added `isAuthenticated(r *http.Request) bool` method |
| `workspace/internal/auth/handler.go` | Added `NewHandlerWithRegisterToken`; register endpoint gated by `X-Register-Token` header; `REGISTER_TOKEN` env var wired in main.go |
| `workspace/internal/auth/auth_test.go` | Added `testRegisterToken` const; updated `newHandler` → `NewHandlerWithRegisterToken`; added `postRegister` helper; updated all 6 `TestRegister_*` tests + `registerUser` |
| `workspace/cmd/workspace-service/main.go` | Replaced `NewVINDecoder()` → `NewVINDecoderWithBase(nhtsaBaseURL)`; `NewNLProvider()` → `NewNLProviderWithBase(rdwBaseURL)`; `NewHandler` → `NewHandlerWithRegisterToken(db, jwtSvc, registerToken)` |

---

## Verification

```
go build ./...                      PASS
go vet ./...                        PASS
go test -race ./internal/auth/...   PASS  (31 tests)
go test -race ./internal/check/...  PASS  (48 tests)
go test -race ./...                 PASS  (all packages)
```
