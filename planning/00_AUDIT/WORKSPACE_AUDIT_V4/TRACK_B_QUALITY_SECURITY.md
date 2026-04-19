# WORKSPACE AUDIT V4 — Track B: Quality + Security
**Scope:** `workspace/` module post-sprints 40–50 (auth, check, config, kanban, media, syndication, web)
**Date:** 2026-04-19
**Auditor:** Claude Code (Sonnet 4.6)
**Rule R1:** All mandatory tools executed — no shortcuts.

---

## 1. Build Verification

| Tool | Result | Notes |
|------|--------|-------|
| `go build ./...` | ✅ PASS | Zero errors |
| `npm run build` | ✅ PASS | 6 chunks, zero TS errors |
| `go vet ./...` | ✅ PASS | Zero findings |
| `staticcheck ./...` | ✅ PASS (post-fix) | 1 finding fixed: `rdwMinIntervalMs` U1000 |
| `govulncheck ./...` | ✅ PASS | No vulnerabilities found |
| `gitleaks detect` | ⚠️ 2 historical leaks | Same key, deleted file in git history (see F-11) |
| `go test -race ./...` | ✅ PASS (post-fix) | All 9 packages pass |

---

## 2. Security Findings

### CRITICAL

#### F-01 — Open self-registration endpoint
**File:** `internal/auth/handler.go` · `POST /api/v1/auth/register`
**Severity:** CRITICAL
**Status:** ✅ FIXED
**Description:** Any unauthenticated caller could POST with an arbitrary `tenant_id` and create accounts for any tenant, enabling tenant impersonation and account squatting.
**Fix:** Registration now requires a matching `X-Register-Token` header. If `REGISTER_TOKEN` env var is empty, the endpoint returns 403 for all callers. `NewHandlerWithRegisterToken()` and `NewHandlerForTest()` constructors added.

---

### HIGH

#### F-02 — X-Forwarded-For spoofing bypasses check rate limiter
**File:** `internal/check/handler.go:clientIPCheck()`
**Severity:** HIGH
**Status:** ✅ FIXED
**Description:** `clientIPCheck()` extracted the first value of `X-Forwarded-For` and used it as the rate-limit key. Any caller could rotate spoofed XFF values to bypass the 10 req/hour anonymous rate limit entirely.
**Fix:** `clientIPCheck()` now reads `X-Real-IP` first (set by the trusted reverse proxy, single value, can't be forged by the client), then falls back to `RemoteAddr`.

#### F-03 — X-Forwarded-For spoofing bypasses login rate limiter
**File:** `internal/auth/handler.go:clientIP()`
**Severity:** HIGH
**Status:** ✅ FIXED
**Description:** Same XFF-first extraction in `clientIP()`. Attacker could rotate spoofed header values to bypass the 5-attempt / 15-minute login rate limit, enabling credential brute-force.
**Fix:** `clientIP()` now reads `X-Real-IP` first, then falls back to `RemoteAddr`.

#### F-04 — Authorization header presence (not validity) bypasses check rate limit
**File:** `internal/check/handler.go`
**Severity:** HIGH
**Status:** ✅ FIXED
**Description:** `authenticated := r.Header.Get("Authorization") != ""` — any caller sending `Authorization: anything` bypassed the anonymous rate limit without having a valid JWT.
**Fix:** Added `isAuthenticated()` method that extracts the `Bearer` token and validates it cryptographically via an injected `func(string) bool`. `NewHandlerWithValidator()` constructor wires this in `main.go` using `jwtSvc.ValidateToken`.

---

### MEDIUM

#### F-05 — staticcheck U1000: `rdwMinIntervalMs` unused constant
**File:** `internal/check/provider_nl.go:35`
**Severity:** MEDIUM
**Status:** ✅ FIXED
**Description:** Constant declared but never used; rate limiting described in comment (1 req/sec) was not implemented. Failing `staticcheck`.
**Fix:** Constant removed.

#### F-06 — `NewVINDecoder()` hardcodes NHTSA URL, ignores `NHTSA_BASE_URL` env var
**File:** `internal/check/vin.go` / `cmd/workspace-service/main.go`
**Severity:** MEDIUM
**Status:** ✅ FIXED
**Description:** `main.go` called `check.NewVINDecoder()` which hardcodes `"https://vpic.nhtsa.dot.gov"`. The `NHTSA_BASE_URL` env var was loaded by `config.go` and documented in `env.example` but never passed to the decoder.
**Fix:** `main.go` now calls `check.NewVINDecoderWithBase(envOrDefault("NHTSA_BASE_URL", "https://vpic.nhtsa.dot.gov"))`.

#### F-07 — `NewNLProvider()` hardcodes RDW URL, ignores `RDW_BASE_URL` env var
**File:** `internal/check/provider_nl.go` / `cmd/workspace-service/main.go`
**Severity:** MEDIUM
**Status:** ✅ FIXED
**Description:** Same pattern as F-06. `RDW_BASE_URL` env var documented but not wired.
**Fix:** `main.go` now calls `check.NewNLProviderWithBase(envOrDefault("RDW_BASE_URL", "https://opendata.rdw.nl/resource"))`.

#### F-08 — bcrypt cost 10 — below OWASP minimum recommendation
**File:** `internal/auth/handler.go`
**Severity:** MEDIUM
**Status:** ✅ FIXED
**Description:** `bcrypt.DefaultCost` (10) was used. OWASP recommends ≥ 12 for new systems. On modern hardware, cost 10 processes ~200 hashes/sec, making offline attacks faster.
**Fix:** Production cost raised to 12 via `h.bcryptCost` field. `NewHandlerForTest()` uses `bcrypt.MinCost` to keep tests fast.

#### F-09 — `DataSource.Note` never populated — errors invisible to API clients
**File:** `internal/check/report.go`
**Severity:** MEDIUM
**Status:** ✅ FIXED
**Description:** `DataSource.Error` (tagged `json:"-"`) was set on fetch failures, but `DataSource.Note` (tagged `json:"note,omitempty"`) was never copied from it. The frontend `DataSource` type has a `note` field that was always empty.
**Fix:** `ds.Note = fetchErr.Error()` added alongside `ds.Error` assignment.

#### F-10 — Summary endpoint bypasses audit log and cache-hit header
**File:** `internal/check/handler.go:summary()`
**Severity:** MEDIUM
**Status:** ✅ FIXED
**Description:** `summary()` called `engine.GenerateReport()` directly, which does check the engine-level cache, but the HTTP handler never called `cache.RecordRequest()` and never set `X-Cache-Hit`. Cache hits were untracked and the response header was missing.
**Fix:** `summary()` now checks `h.cache.GetReport()` at the handler level (matching `fullReport`), calls `RecordRequest()`, and sets `X-Cache-Hit`.

#### F-11 — Prometheus metrics registered but never served
**File:** `cmd/workspace-service/main.go`
**Severity:** MEDIUM
**Status:** ✅ FIXED
**Description:** `promauto`-registered metrics (`workspace_check_requests_total`, `workspace_check_provider_latency_seconds`, etc.) were collected but `/metrics` endpoint was never exposed. `WORKSPACE_METRICS_ADDR` env var documented but unused.
**Fix:** A separate `http.Server` on `WORKSPACE_METRICS_ADDR` (default `:9091`) with `promhttp.Handler()` is now started at service boot.

#### F-12 — `login()` rate limiter counts valid logins on first attempt
**File:** `internal/auth/middleware.go:Allow()`
**Severity:** MEDIUM
**Status:** ⚠️ NOT FIXED (design decision)
**Description:** `Allow()` increments the counter on every call, including the first attempt. A legitimate user logging in for the first time consumes one of their 5 attempts before any failure occurs. The counter is reset on success, so brute-force protection is unaffected.
**Recommendation:** Increment only on failure by checking the bcrypt result before calling `Allow()`. Deferred — current behavior is not a security regression, only a UX concern.

#### F-13 — Retry-After header absent on 429 responses
**File:** `internal/auth/handler.go`, `internal/check/handler.go`
**Severity:** MEDIUM
**Status:** ✅ FIXED
**Description:** RFC 6585 requires `Retry-After` on 429 responses. Frontend `useCheck.ts` attempted to read `retryAfterSeconds` from JSON but the header was never set by the backend.
**Fix:** `Retry-After: 900` added to login 429; `Retry-After: 3600` added to check 429.

#### F-14 — `config` package never used by `main.go`
**File:** `cmd/workspace-service/main.go`
**Severity:** MEDIUM
**Status:** ⚠️ NOT FIXED (tracked as tech debt)
**Description:** `config.LoadFromEnv()` and `config.Validate()` exist and are tested, but `main.go` duplicates env-reading with its own `envOrDefault()`. The two are now kept in sync manually (drift risk). F-06/F-07 were partially addressable because `envOrDefault` is already present.
**Recommendation:** Migrate `main.go` to use `config.LoadFromEnv()` in a separate sprint to remove the duplicate.

#### F-15 — `config.Validate()` does not check empty `CARDEX_JWT_SECRET`
**File:** `internal/config/config.go`
**Severity:** MEDIUM
**Status:** ⚠️ NOT FIXED (mitigated)
**Description:** `Validate()` checks Port, DBPath, MediaDir, NHTSABaseURL, RDWBaseURL but NOT `JWTSecret`. A deployment with an empty secret silently starts with an ephemeral key (all sessions invalidated on restart).
**Mitigation:** `main.go` emits a `log.Warn` and continues (logged, not fatal). For production hardening, add `config.Validate()` call with a `JWTSecret` check.

#### F-16 — `check_requests` stores raw IPs with no retention policy
**File:** `internal/check/schema.go`, `internal/check/cache.go`
**Severity:** MEDIUM (GDPR)
**Status:** ⚠️ NOT FIXED (tracked)
**Description:** `check_requests` audit table accumulates raw IP addresses indefinitely. `check_cache` has TTL + hourly cleanup; `check_requests` has none. Under GDPR, IP addresses are personal data requiring a defined retention period.
**Recommendation:** Add a 90-day cleanup via `DELETE FROM check_requests WHERE requested_at < ?` in the hourly cleanup loop.

#### F-17 — NL provider: 1 req/sec guideline not implemented
**File:** `internal/check/provider_nl.go`
**Severity:** MEDIUM
**Status:** ⚠️ NOT FIXED (tracked)
**Description:** The removed `rdwMinIntervalMs = 1000` comment described a rate limit that was never implemented. The provider can issue 3 sequential requests (vehicle → APK → stolen) without delay, violating RDW's informal 1 req/sec guideline.
**Recommendation:** Add a `time.Sleep(time.Duration(rdwMinIntervalMs) * time.Millisecond)` between sub-requests within `FetchHistory()`.

#### F-18 — `Alert.ID` collision potential
**File:** `internal/check/registry.go:newAlert()`
**Severity:** MEDIUM
**Status:** ⚠️ NOT FIXED
**Description:** Alert IDs are constructed as `string(alertType) + "_" + string(severity)`. If a vehicle is reported stolen in multiple countries, all stolen alerts share the same ID `"stolen_critical"`.
**Recommendation:** Append a counter or source suffix to ensure uniqueness.

---

### LOW

#### F-19 — gitleaks: API key in git history
**File:** `scrapers/fr/leboncoin.py` (deleted)
**Severity:** LOW
**Status:** ⚠️ HISTORICAL (git history only)
**Description:** Two gitleaks detections of the same `api_key = ba0c2dad52b3585c9c4b529781058dbc` in commits 97ca84bf and f3d903f6. The file no longer exists in the working tree.
**Recommendation:** Verify the key is no longer valid. If it was a real credential, rotate it. Consider `git filter-repo` to expunge from history if the repo is public or the secret is sensitive.

#### F-20 — No per-provider sub-context timeout in `GenerateReport`
**File:** `internal/check/report.go`
**Severity:** LOW
**Status:** ⚠️ NOT FIXED
**Description:** Provider goroutines receive the HTTP request context. If the NL provider's 15s HTTP client timeout fires, the WaitGroup eventually unblocks, but there's no explicit sub-context with a shorter deadline per provider. A single slow provider cannot block longer than its own HTTP client timeout.
**Recommendation:** Wrap each goroutine context with `context.WithTimeout(ctx, 20*time.Second)` for defense-in-depth.

#### F-21 — `TestRefresh_ExpiredToken` used `NewHandler` (no register token)
**File:** `internal/auth/auth_test.go`
**Severity:** LOW (test quality)
**Status:** ✅ FIXED
**Description:** Test created a handler with no register token, so the register call returned 403 and the "expired token" test was not actually testing token expiry — it was testing missing token.
**Fix:** Updated to use `NewHandlerForTest(db, shortJWT, testRegisterToken)` with `postRegister`.

#### F-22 — `VINInput.tsx` validation regex uses redundant `/i` flag
**File:** `web/src/components/VINInput.tsx`
**Severity:** LOW
**Status:** ⚠️ NOT FIXED (harmless)
**Description:** Pattern `/^[A-HJ-NPR-Z0-9]{17}$/i` — the `/i` flag makes the character class match lowercase too, but the component uppercases input before validation. No functional impact.

#### F-23 — `MileageRecord.IsAnomaly` never populated
**File:** `internal/check/registry.go`
**Severity:** LOW
**Status:** ⚠️ NOT FIXED
**Description:** The `IsAnomaly bool` field is defined and JSON-tagged but no provider or the mileage analyser sets it. The frontend renders anomaly dots using this field; they never appear.
**Recommendation:** In `analyseMileage`, mark records at rollback indices with `IsAnomaly = true`.

#### F-24 — `useCheck.ts` has no fetch timeout
**File:** `web/src/hooks/useCheck.ts`
**Severity:** LOW
**Status:** ⚠️ NOT FIXED
**Description:** AbortController is used for unmount cleanup but not for timeouts. A stalled API response holds the loading state indefinitely.
**Recommendation:** Add `setTimeout(() => controller.abort(), 30_000)` in the fetch call.

#### F-25 — RDW APK inspection result: failed inspections incorrectly marked `pending`
**File:** `internal/check/provider_nl.go:fetchAPK()`
**Severity:** LOW
**Status:** ⚠️ NOT FIXED
**Description:** RDW does not expose pass/fail directly. Current logic: if `NextDueDate` is present → `pass`, else → `pending`. A failed inspection also has no next due date, so it would be incorrectly classified as `pending`.
**Recommendation:** Check `tellerstandoordeel` field for values like `Afwijzing` (rejection) to differentiate fail from pending.

#### F-26 — `Check.tsx` does not restore `document.title` on unmount
**File:** `web/src/pages/Check.tsx`
**Severity:** LOW
**Status:** ⚠️ NOT FIXED
**Description:** Title is set in a `useEffect` but the cleanup function doesn't restore the previous title. If a user navigates away quickly, the VIN-specific title persists.

#### F-27 — Auth schema: `crm_users` has no global email uniqueness
**File:** `internal/auth/schema.go`
**Severity:** LOW
**Status:** ⚠️ NOT FIXED (by design)
**Description:** `UNIQUE(tenant_id, email)` allows the same email to be registered across multiple tenants. This is intentional for multi-tenant SaaS but should be documented.

#### F-28 — Register endpoint does not validate email format
**File:** `internal/auth/handler.go:register()`
**Severity:** LOW
**Status:** ⚠️ NOT FIXED
**Description:** Any non-empty string is accepted as email. A malformed email would be stored and could cause issues with SMTP-based features.
**Recommendation:** Add basic RFC 5322 check: `strings.Contains(email, "@")` at minimum.

#### F-29 — `check_cache` JSON not compressed
**File:** `internal/check/cache.go`
**Severity:** LOW
**Status:** ⚠️ NOT FIXED
**Description:** Full report JSON stored as-is in SQLite BLOB. A report with many inspections/mileage records can be 10–50 KB. Compression (zstd or gzip) would reduce DB size significantly.

#### F-30 — `deploy/env.example` missing `REGISTER_TOKEN`
**File:** `deploy/env.example`
**Severity:** LOW
**Status:** ✅ FIXED
**Description:** New `REGISTER_TOKEN` env var was not documented.
**Fix:** Added entry with generation command (`openssl rand -hex 32`).

---

## 3. Integration Coherence

| Check | Result |
|-------|--------|
| `auth.EnsureSchema` called before handler | ✅ |
| `check.EnsureSchema` called | ✅ |
| All 6 providers wired | ✅ (NL, FR, BE, ES, DE, CH) |
| NHTSA URL from env | ✅ (post-fix) |
| RDW URL from env | ✅ (post-fix) |
| JWT validator wired to check handler | ✅ (post-fix) |
| Register token wired from env | ✅ (post-fix) |
| Prometheus metrics served | ✅ (post-fix) |
| Graceful shutdown covers metrics server | ✅ |
| Kanban/Calendar registered | ✅ |
| Media reorder handler registered | ✅ |
| Syndication scheduler started | ✅ |

---

## 4. Cross-Module Consistency

| Item | Status |
|------|--------|
| `deploy/env.example` covers all workspace env vars | ✅ (post-fix) |
| Frontend `DataSource.note` matches Go `DataSource.Note` JSON tag | ✅ |
| Frontend `VehicleAlert` fields match Go `Alert` struct | ✅ |
| Frontend `MileageRecord.isAnomaly` — never set by backend | ⚠️ F-23 |
| `config` package and `main.go` env vars in sync | ⚠️ F-14 (drift risk) |
| `VehicleReport` JSON tags match frontend `VehicleReport` TS type | ✅ |

---

## 5. Summary of Fixes Applied

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| F-01 | CRITICAL | Open register endpoint | `X-Register-Token` protection + `REGISTER_TOKEN` env var |
| F-02 | HIGH | XFF spoofing in check rate limiter | `X-Real-IP` → `RemoteAddr` |
| F-03 | HIGH | XFF spoofing in auth rate limiter | `X-Real-IP` → `RemoteAddr` |
| F-04 | HIGH | Auth header presence bypasses check rate limit | JWT validation via `isValidToken` func |
| F-05 | MEDIUM | `rdwMinIntervalMs` unused (staticcheck U1000) | Constant removed |
| F-06 | MEDIUM | NHTSA URL hardcoded | `NewVINDecoderWithBase(envOrDefault(...))` in main.go |
| F-07 | MEDIUM | RDW URL hardcoded | `NewNLProviderWithBase(envOrDefault(...))` in main.go |
| F-08 | MEDIUM | bcrypt cost 10 | Cost raised to 12; `NewHandlerForTest` uses `bcrypt.MinCost` |
| F-09 | MEDIUM | `DataSource.Note` never populated | `ds.Note = fetchErr.Error()` added |
| F-10 | MEDIUM | Summary endpoint skips audit log / cache-hit header | Handler-level cache check + `RecordRequest` |
| F-11 | MEDIUM | Prometheus metrics not served | Separate metrics HTTP server on `:9091` |
| F-13 | MEDIUM | No `Retry-After` header on 429 | Added to both auth and check handlers |
| F-21 | LOW | `TestRefresh_ExpiredToken` false pass | Fixed to use `NewHandlerForTest` + `postRegister` |
| F-30 | LOW | `REGISTER_TOKEN` missing from env.example | Added to `deploy/env.example` |

**14 findings fixed. 16 tracked for follow-up sprints.**

---

## 6. Tool Output Summary

```
go build ./...          → EXIT 0
staticcheck ./...       → EXIT 0  (1 finding fixed: rdwMinIntervalMs U1000)
go vet ./...            → EXIT 0
govulncheck ./...       → No vulnerabilities found
gitleaks detect         → 2 historical leaks (same key, deleted file)
go test -race ./...     → PASS (9 packages)
npm run build           → EXIT 0 (6 chunks)
```
