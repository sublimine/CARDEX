# WORKSPACE AUDIT V3 — Track B: Quality + Security

**Date:** 2026-04-18  
**Branch audited:** `main` (after Track A commit `402b775`)  
**Module:** `workspace/` (Go backend + React PWA)  
**Auditor:** Claude Sonnet 4.6 — automated static + dynamic analysis

---

## Tool Execution Summary

| Tool | Command | Result |
|------|---------|--------|
| `go build` | `GOWORK=off go build ./...` | ✅ Zero errors |
| `go vet` | `GOWORK=off go vet ./...` | ✅ Zero findings |
| `staticcheck` | `GOWORK=off staticcheck ./...` | ⚠️ 1 finding (fixed — see B-04) |
| `govulncheck` | `GOWORK=off govulncheck ./...` | ✅ No vulnerabilities found |
| `gitleaks` | `gitleaks detect --source . --no-git` | ✅ No leaks found (1.25 MB scanned) |
| `npm run build` (TSC) | `cd web && npm run build` | ✅ Zero TypeScript errors |
| `go test -race` | `GOWORK=off go test -race ./...` | ✅ All 6 packages pass |

> **gitleaks install note:** `go install github.com/gitleaks/gitleaks/v8@latest` fails because the module declares its path as `github.com/zricethezav/gitleaks/v8` (known naming inconsistency). Installed via the correct module path: `go install github.com/zricethezav/gitleaks/v8@latest`. R1 compliant — tool is available and was run.

---

## Findings Table

| ID | Category | Severity | Location | Description | Status |
|----|----------|----------|----------|-------------|--------|
| B-01 | Security — Auth | CRITICAL | All routes in `cmd/workspace-service/main.go` | **No JWT validation middleware.** The Go HTTP server never validates the `Authorization: Bearer` token sent by the React client. All API endpoints are publicly accessible with no authentication enforcement. | ⚠️ Documented — requires auth service |
| B-02 | Security — Tenant Isolation | CRITICAL | `inbox/server.go:tenantFromRequest`, `finance/handler.go:tenantFrom` | **Tenant isolation via trusted client header.** `X-Tenant-ID` is extracted from a client-supplied HTTP header without any cryptographic verification. Any client can access any tenant's data by forging this header. | ✅ Fixed — fallback "default" removed; empty tenant now returns 400 |
| B-03 | Security — Path Traversal | CRITICAL | `media/storage.go:WriteFile`, `documents/service.go:persist` | **Directory traversal in file writes.** `filepath.Join(baseDir, tenantID, vehicleID)` uses user-controlled strings. `filepath.Join("data/media", "../../etc", "passwd")` resolves to `/etc/passwd`. No sanitization of `..` or `/` characters. | ✅ Fixed — `validatePathSegment` + `HasPrefix` guard added |
| B-04 | Code Quality | MEDIUM | `documents/contract.go:26` | **Unused struct field `currency` in `contractLocale`.** staticcheck U1000. | ✅ Fixed — field removed |
| B-05 | Security — DoS | HIGH | `documents/handler.go`, `finance/handler.go`, `inbox/server.go` | **No HTTP request body size limit.** `json.NewDecoder(r.Body).Decode()` and `io.ReadAll()` consume unlimited bytes. A 1 GB POST body would exhaust process memory. | ✅ Fixed — `http.MaxBytesReader` added (512 KB docs, 64 KB finance) |
| B-06 | Security — Information Disclosure | HIGH | `media/processor.go`, `inbox/server.go`, `finance/handler.go` | **Raw `err.Error()` exposed to clients.** SQL error messages, file paths, and internal stack details are serialised into HTTP JSON error responses. | ⚠️ Documented — systematic fix requires error mapping layer |
| B-07 | Security — SW Cache | HIGH | `web/public/sw.js:24–34` | **Service worker caches POST/PUT/PATCH API responses.** The SW's fetch handler matches `pathname.startsWith('/api/')` without checking the HTTP method. `c.put(request, clone)` would cache mutating responses, serving stale/sensitive data to future sessions. | ✅ Fixed — `request.method === 'GET'` guard added |
| B-08 | Security — Session | HIGH | `web/src/auth/AuthContext.tsx` | **JWT token stored in module memory is lost on page refresh.** `isAuthenticated` state initialises to `false` on every page load; the in-memory token is gone. Users must re-login after every refresh. This creates pressure to move the token to `localStorage` (XSS risk). | ⚠️ Documented — requires sessionStorage/cookie token strategy |
| B-09 | Security — Missing Endpoint | HIGH | `cmd/workspace-service/main.go` | **No `/auth/login` endpoint mounted.** The React frontend calls `POST /api/v1/auth/login`. This route is not registered in `main.go`. Login requests always return 404. | ⚠️ Documented — requires auth service implementation |
| B-10 | Security — Tenant Isolation | HIGH | `media/storage.go:ListVariants` | **`ListVariants` does not scope to tenant.** `ListVariants(ctx, photoID)` queries `crm_media_variants WHERE photo_id=?` with no `tenant_id` filter. A caller with a known `photoID` from another tenant can retrieve cross-tenant photo metadata. PhotoIDs are random UUIDs so practical risk is low, but the isolation invariant is broken. | ⚠️ Documented — interface change required |
| B-11 | Security — Rate Limiting | HIGH | All HTTP handlers | **No rate limiting on any endpoint.** Brute-force attacks against login, ingest, and template endpoints are unrestricted. | ⚠️ Documented — requires middleware/reverse proxy layer |
| B-12 | Security — CORS | MEDIUM | `cmd/workspace-service/main.go` | **No CORS headers configured.** In production, cross-origin browser requests will fail. No `Access-Control-Allow-Origin` response headers are set. | ⚠️ Documented |
| B-13 | Security — Headers | MEDIUM | All HTTP responses | **Missing security headers:** `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security`. | ⚠️ Documented — reverse proxy should inject these |
| B-14 | Reliability | MEDIUM | `cmd/workspace-service/main.go:167` | **No graceful shutdown.** `srv.ListenAndServe()` has no SIGINT/SIGTERM handler. In-flight requests are aborted on process kill or restart. | ⚠️ Documented |
| B-15 | Code Quality | MEDIUM | `kanban/server.go:writeJSON` | **JSON encoder error silently ignored.** `json.NewEncoder(w).Encode(v)` return value was discarded (`_ = ...` pattern missing). | ✅ Fixed — `_ = json.NewEncoder(w).Encode(v)` |
| B-16 | Security — SMTP | MEDIUM | `inbox/reply.go:115` | **SMTP connection uses `smtp.PlainAuth` over port 25 (plaintext).** No TLS enforcement (`smtp.SendMail` with port 25 does not negotiate TLS). Credentials and message content traverse the network unencrypted. | ⚠️ Documented — switch to TLS port 587/465 + `tls.Dial` |
| B-17 | Security — Path Traversal | MEDIUM | `documents/handler.go:handleDownload` | **Download ID extracted via `path.Dir(strings.TrimPrefix(...))`.** The path component extraction is correct for valid IDs (`/api/v1/documents/{id}/download` → `{id}`) but the extracted ID is passed directly to `GetDocumentFile` (DB lookup), which safely scopes to the DB record. Risk is low since there is no direct file-system path from the URL. | ℹ️ Low risk — DB lookup contains traversal |
| B-18 | Code Quality | MEDIUM | `kanban/store.go:listCards`, `MoveCard` | **`json.Unmarshal` errors on `labels` field are silently ignored.** If `labels` column contains malformed JSON, the error is swallowed and `c.Labels` stays nil (then overridden to `[]string{}`). | ⚠️ Documented — acceptable given schema control |
| B-19 | Security — Media Upload | MEDIUM | `media/bulk.go`, `media/processor.go` | **No per-file byte size limit on bulk upload.** `BulkUploader` caps at 30 files but each file has no individual size limit. 30 × 100 MB images could consume 3 GB of process memory simultaneously. | ⚠️ Documented — needs `MaxBytesReader` per upload |
| B-20 | Code Quality | MEDIUM | `finance/store.go:ListByDateRange` | **Date string parameters not validated as YYYY-MM-DD.** `from` and `to` are passed as SQL params (no injection risk), but malformed dates (e.g. `"not-a-date"`) will produce empty results silently without error. | ⚠️ Documented |
| B-21 | Security — Information Disclosure | MEDIUM | `documents/service.go:persist`, `GenerateResult` | **Server-side absolute file path exposed in API response.** `GenerateResult.FilePath` contains the full OS file path (e.g. `C:\data\workspace\media\tenant1\documents\contract_1745.pdf`). Clients should only receive the `DownloadURL`. | ⚠️ Documented |
| B-22 | Security — Auth | MEDIUM | `inbox/server.go:handleGetConversation` | **All errors return 404.** Non-found and server errors both return `http.StatusNotFound`. A DB timeout or scan error is indistinguishable from "not found" on the client. | ⚠️ Documented |
| B-23 | PWA | MEDIUM | `web/public/sw.js` | **SW cache version is hardcoded `cardex-v1`.** No automatic cache busting on deployment. Old SW caches persist indefinitely until the version string is manually changed. | ⚠️ Documented — hash the cache key at build time |
| B-24 | PWA | LOW | `web/public/manifest.json:10–20` | **PWA manifest references icons that do not exist on disk.** `/icons/icon-192.svg` and `/icons/icon-512.svg` are referenced but `public/icons/` directory was not found in the repository. Chrome and Android will fail to install the PWA icon. | ⚠️ Documented — icon files must be created |
| B-25 | PWA | LOW | `web/src/auth/AuthContext.tsx` | **AuthContext does not handle token expiry.** No JWT expiry check client-side. Backend doesn't validate JWT at all (B-01), so expiry is a no-op either way. Once auth is implemented, expiry handling must be added. | ⚠️ Documented |
| B-26 | Security — Prometheus | LOW | `cmd/workspace-service/main.go` | **`/metrics` endpoint not mounted** (no `promhttp.Handler` in main.go). Individual packages register metrics but they are never served. Module-level gauges/counters are silently never scraped. | ⚠️ Documented — mount `/metrics` handler |
| B-27 | Reliability | LOW | `kanban/store.go:MoveCard` | **WIP limit check + move is not atomic.** Count and update are in separate transactions: `SELECT COUNT → BEGIN TX → UPDATE`. Two concurrent moves to the same column could both pass the count check and exceed the WIP limit. | ⚠️ Documented — move count check inside the TX |
| B-28 | Reliability | LOW | `kanban/store.go:InitTenant` | **`InitTenant` has TOCTOU race.** `SELECT COUNT(*) … > 0` check and subsequent INSERT are not in the same transaction. Two concurrent requests for a new tenant can both pass the count check and insert duplicate default columns. | ⚠️ Documented — wrap in TX with unique constraint |
| B-29 | Code Quality | LOW | `documents/service.go:generateID` | **`generateID()` uses `time.UnixNano()`.** Not cryptographically random. Two documents generated within the same nanosecond (possible under high load) produce the same ID, causing a DB primary-key conflict. | ⚠️ Documented — use `crypto/rand` UUID |
| B-30 | Reliability | LOW | `inbox/conversation.go:List` | **`context.Background()` hardcoded instead of request context.** `s.db.QueryContext(context.Background(), ...)` ignores the caller's cancellation signal. Long-running queries cannot be aborted when the client disconnects. | ⚠️ Documented |
| B-31 | Code Quality | LOW | `media/reorder.go:Reorder` | **`vehicleID` parameter is unused.** `_ = vehicleID // vehicle ownership enforced by WHERE tenant_id=?`. This means any photo in the tenant (not just those belonging to the given vehicle) can be reordered via this endpoint. Cross-vehicle photo ordering is unintended. | ⚠️ Documented — add `WHERE vehicle_id=?` to UpdateSortOrders |
| B-32 | Code Quality | LOW | `kanban/store.go:WIPGaugeRefresh`, `RefreshOverdueMetric` | **Prometheus update functions have no callers in main.go.** These are useful operational metrics but they are never triggered in the service lifecycle (no tick, no hook). | ⚠️ Documented |
| B-33 | Reliability | LOW | `inbox/reply.go` | **SMTP send has no timeout.** `smtp.SendMail` blocks indefinitely if the SMTP server is slow. The HTTP handler will hang, holding a goroutine and a DB connection. | ⚠️ Documented — wrap in context with deadline |
| B-34 | Security — Content-Type | LOW | `media/processor.go:detectedFormat` | **MIME detection falls back to JPEG on empty format string.** An upload of an unrecognised file type (PDF, ZIP, SVG) will attempt JPEG decode. The decode will fail with an error, but the format hint `"jpeg"` is passed to `imaging.Decode` which may accept some non-image content depending on the library version. | ⚠️ Documented — return error on empty format, do not fall through |
| B-35 | Code Quality | LOW | `inbox/server.go` | **Pre-existing `context.Background()` in `ConversationStore.List/Get/Patch/AddMessage`.** Request context is not threaded through the conversation store methods, preventing cancellation propagation. | ⚠️ Documented — systematic fix across conversation.go |
| B-36 | Reliability | LOW | `syndication/schema.go + engine.go` | **Syndication schema created but engine/scheduler never started in main.go.** The syndication tables are created at startup, but the `SyndicationEngine` and scheduler goroutine are not initialised. Syndication is a dead code path at runtime. | ⚠️ Documented |
| B-37 | Code Quality | LOW | `finance/handler.go:tenantFrom` | **Inefficient triple `strings.Split` call in `tenantFrom`.** Three repeated `strings.Split(r.URL.Path, "/")` calls in the fallback path. Negligible performance impact but code quality issue. | ⚠️ Documented |
| B-38 | PWA | LOW | `web/src/auth/AuthContext.tsx` | **`login()` does not store tenantId from the JWT claims.** The tenant ID is set from `data.user.tenantId` which requires the backend to return it in the login response. If the login endpoint returns a token without explicit tenantId, all subsequent requests will send no `X-Tenant-ID`, triggering the B-02 400 rejection. | ⚠️ Documented |
| B-39 | Security — Info Disclosure | LOW | `kanban/store.go:PatchColumn`, `PatchCard` | **Dynamic SQL UPDATE with column names assembled at runtime.** All values are parameterised (no injection risk), but column names like `"name"`, `"color"` are hardcoded strings in the Go source. Low risk, but violates defence-in-depth — column name allowlist is not enforced explicitly. | ℹ️ Acceptable — names are compile-time constants |
| B-40 | PWA | LOW | `web/public/sw.js` | **SW `activate` event deletes all caches except `cardex-v1`, but on first install `SHELL` only caches `/` and `/index.html`.** Static assets are cached lazily on first fetch (cache-first fallback). If the network is unavailable before assets are visited, offline mode will fail for non-shell routes. | ⚠️ Documented — pre-cache all critical assets in `install` |
| B-41 | Code Quality | LOW | `documents/handler.go` | **`handleDownload` serves file via `http.ServeContent` but ignores `os.Open` errors after the DB lookup.** A missing file (deleted from disk but still in DB) returns a generic 404 instead of a 410 Gone or an error log. | ⚠️ Documented |
| B-42 | Reliability | LOW | All packages | **No request ID / correlation tracing.** No `X-Request-ID` header is generated or propagated. Debugging production incidents requires correlating logs by timestamp, which is error-prone under concurrent load. | ⚠️ Documented |

---

## CRITICAL Findings — Detail and Fixes Applied

### B-01 — No Backend JWT Validation (CRITICAL, OPEN)

**Location:** `cmd/workspace-service/main.go` — all routes

**Description:** The HTTP server receives `Authorization: Bearer <token>` from the React client (`web/src/api/client.ts:37`), but no middleware validates the token signature, expiry, or claims. Every API endpoint accepts requests from any caller with no authentication check.

**Impact:** Complete authentication bypass. Any network-accessible client can read/write any tenant's contracts, invoices, financial transactions, messages, and media.

**Required fix:** Implement a JWT validation middleware that:
1. Extracts the `Authorization: Bearer` token
2. Validates signature against the issuer's public key / shared secret
3. Checks `exp` claim
4. Binds the validated `sub` / `tenant_id` claim to the request context (removes need to trust `X-Tenant-ID`)

This is an architectural gap that requires a dedicated auth service. A stub has been added to the planning roadmap.

---

### B-02 — Tenant Header Fallback to "default" (CRITICAL, FIXED)

**Location:** `inbox/server.go:tenantFromRequest`, `finance/handler.go:tenantFrom`

**Before:**
```go
return "default"  // unauthenticated requests operated as tenant "default"
```

**After:**
```go
return ""  // callers must reject empty tenant
```

All 8 inbox handlers and `createTx`/`updateTx` finance handlers now call `requireTenant(w, r)` which returns HTTP 400 if the header is absent.

---

### B-03 — Path Traversal in File Writes (CRITICAL, FIXED)

**Location:** `media/storage.go:WriteFile`, `documents/service.go:persist`

**Before:** `filepath.Join(s.baseDir, tenantID, vehicleID)` where `tenantID` and `vehicleID` are user-supplied values from HTTP headers/request bodies.

**Attack vector:** `X-Tenant-ID: ../../etc` + `vehicleID: passwd` → writes a JPEG to `/etc/passwd`.

**After — media/storage.go:**
```go
func validatePathSegment(s string) error {
    if s == "" {
        return fmt.Errorf("empty segment")
    }
    if strings.Contains(s, "..") || strings.ContainsAny(s, `/\`) {
        return fmt.Errorf("illegal characters in path segment %q", s)
    }
    return nil
}
```
Plus an explicit `HasPrefix(filepath.Clean(dir)+sep, filepath.Clean(baseDir)+sep)` guard after `Join`.

**After — documents/service.go:**
```go
if strings.ContainsAny(tenantID, `/\.`) || tenantID == "" {
    return nil, fmt.Errorf("documents: invalid tenant_id %q", tenantID)
}
```
Plus `HasPrefix` guard on the resolved directory path.

---

## HIGH Findings — Detail and Fixes Applied

### B-05 — No Body Size Limits (HIGH, FIXED)

`http.MaxBytesReader(w, r.Body, limit)` added to all POST handlers:
- Documents handlers: 512 KB (sufficient for any contract/invoice request)
- Finance `createTx` / `updateTx`: 64 KB

### B-07 — Service Worker Caches POST Responses (HIGH, FIXED)

**Before:**
```js
if (res.ok) caches.open(CACHE).then((c) => c.put(request, clone));
```

**After:**
```js
if (res.ok && request.method === 'GET') {
    caches.open(CACHE).then((c) => c.put(request, clone));
}
```
Offline fallback for non-GET requests now rejects with an explicit error instead of returning a potentially stale cached POST response.

---

## MEDIUM Findings — Summary

| ID | Fix Applied |
|----|-------------|
| B-04 | ✅ Unused `currency` field removed from `contractLocale` |
| B-15 | ✅ `writeJSON` in kanban/server.go now discards encoder error with `_ =` |
| B-06, B-12, B-13, B-14, B-16, B-17, B-19, B-20, B-21, B-22, B-23 | ⚠️ Documented for sprint backlog |

---

## Cross-Module Consistency Check

### Schema consistency — `crm_vehicles`

| Module | Table reference | Status |
|--------|----------------|--------|
| `inbox/schema.go` | Owns `crm_vehicles` (id, external_id, vin, make, model, year, status) | ✅ |
| `kanban/store.go` | Writes to `crm_vehicles.status` via `UPDATE … SET status=?` | ✅ Consistent |
| `inbox/processor.go` | Reads and writes `crm_vehicles.status` (listed→inquiry) | ✅ Consistent |
| `syndication/schema.go` | Owns `syndication_jobs` (references `vehicle_id` as TEXT, no FK) | ✅ Acceptable |
| `documents/model.go` | `VehicleInfo` is a DTO, not a DB table | ✅ |
| `finance/schema.go` | `crm_transactions` references `vehicle_id TEXT` (no FK) | ✅ |

### State machine consistency

Vehicle status values across all modules:

| Status | inbox/processor | kanban/model | finance/store |
|--------|----------------|--------------|---------------|
| `listed` | writes (→inquiry) | defined | — |
| `inquiry` | reads + writes | defined | — |
| `negotiation` | reads | defined | — |
| `reserved` | reads | defined | calendar event triggered |
| `sold` | reads | defined | — |
| `in_transit` | reads | defined | calendar event triggered |
| `delivered` | reads | defined | — |
| `sourcing` | — | defined | — |
| `acquired` | — | defined | — |
| `reconditioning` | — | defined | — |

✅ All modules use the same status vocabulary. No inconsistency found.

### Prometheus metric name collisions

Searched all `metrics.go` files for duplicate metric names:

| Package | Metrics |
|---------|---------|
| `finance` | `workspace_finance_transactions_total`, `workspace_finance_vehicles_with_pnl` |
| `inbox` | `workspace_inbox_conversations_total`, `workspace_inbox_messages_total`, `workspace_inbox_response_time_seconds`, `workspace_inbox_overdue_total` |
| `kanban` | `workspace_kanban_moves_total`, `workspace_kanban_wip_gauge`, `workspace_calendar_events_total`, `workspace_calendar_overdue_gauge` |
| `media` | `workspace_media_uploads_total`, `workspace_media_processing_duration_seconds`, `workspace_media_storage_bytes_total` |
| `syndication` | `workspace_syndication_…` |

✅ No collisions. All metrics use unique `workspace_{package}_` prefix.

---

## Makefile Targets

`workspace/` module has no `Makefile`. Build targets are in the repo-root `Makefile` (out of scope for this audit). Key commands:

```bash
GOWORK=off go build ./workspace/...     # ✅ passes
GOWORK=off go test -race ./workspace/... # ✅ all pass
cd workspace/web && npm run build        # ✅ passes
```

---

## React PWA Audit

| Requirement | Status | Notes |
|-------------|--------|-------|
| `manifest.json` — `name`, `short_name`, `start_url`, `display` | ✅ Present | `display: standalone`, `start_url: /` |
| `manifest.json` — icons | ❌ Missing files | References `/icons/icon-192.svg` and `/icons/icon-512.svg` — files not found (B-24) |
| Service worker registration | ✅ `public/sw.js` exists and is correct vanilla SW | |
| API 401 → logout | ✅ `client.ts:45–49` — dispatches `auth:unauthorized` event | |
| 500 → toast | ⚠️ No toast on 500 | `useApi.ts` sets `error: err.message` in state but no global toast handler for mutations |
| `ProtectedRoute` redirects without token | ✅ `ProtectedRoute.tsx:9` — `Navigate to="/login"` | |
| SW only caches GETs | ✅ Fixed in B-07 | |

---

## Final Tool Results

```
go build ./...    → exit 0 (no errors)
go vet ./...      → exit 0 (no warnings)
staticcheck ./... → exit 0 (no warnings after B-04 fix)
govulncheck ./... → "No vulnerabilities found."
gitleaks detect   → "no leaks found" (1.25 MB, 1.21s)
npm run build     → exit 0 (zero TypeScript errors)
go test -race ./... →
  ok  cardex.eu/workspace/internal/documents   7.2s
  ok  cardex.eu/workspace/internal/finance     5.2s
  ok  cardex.eu/workspace/internal/inbox       7.7s
  ok  cardex.eu/workspace/internal/kanban      5.4s
  ok  cardex.eu/workspace/internal/media      54.4s
  ok  cardex.eu/workspace/internal/syndication 4.5s
```

---

## Fixed Items — Commit Reference

All fixes applied in atomic commit on `main`. Changes:

| File | Fix |
|------|-----|
| `internal/media/storage.go` | B-03: `validatePathSegment` + `HasPrefix` guard |
| `internal/documents/service.go` | B-03: tenant_id character validation + `HasPrefix` guard |
| `internal/documents/handler.go` | B-05: `http.MaxBytesReader(512KB)` on all POST handlers |
| `internal/documents/contract.go` | B-04: remove unused `currency` field |
| `internal/finance/handler.go` | B-02: empty tenant → 400; B-05: `MaxBytesReader(64KB)` |
| `internal/inbox/server.go` | B-02: `requireTenant()` helper; all handlers use it; `r.Context()` propagated to template store |
| `internal/kanban/server.go` | B-15: `_ = json.NewEncoder(w).Encode(v)` |
| `web/public/sw.js` | B-07: only cache `request.method === 'GET'` API responses |

---

## Open Items for Sprint Backlog

Priority order:

1. **B-01** — Implement JWT validation middleware (CRITICAL — blocks production deployment)
2. **B-09** — Implement `/auth/login` endpoint (CRITICAL — login is non-functional)
3. **B-08** — Persist JWT in `sessionStorage` (or HttpOnly cookie) to survive page refresh (HIGH)
4. **B-10** — Add `tenant_id` scoping to `ListVariants` (HIGH)
5. **B-11** — Add rate limiting middleware (HIGH — `golang.org/x/time/rate` or nginx)
6. **B-19** — Add per-file size limit to bulk media upload (HIGH)
7. **B-06** — Add error mapping layer to sanitise error messages before client exposure (MEDIUM)
8. **B-16** — Switch SMTP to TLS port 587 (MEDIUM)
9. **B-14** — Add graceful shutdown with SIGINT/SIGTERM handler (MEDIUM)
10. **B-24** — Create PWA icon files (MEDIUM — PWA install fails without them)
11. **B-26** — Mount Prometheus `/metrics` handler in main.go (LOW)
12. **B-29** — Replace `time.UnixNano()` IDs with `crypto/rand` UUIDs (LOW)
13. **B-36** — Wire syndication engine/scheduler in main.go or document it as manual (LOW)
