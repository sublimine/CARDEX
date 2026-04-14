# Code Audit Report — Discovery Service
**Date:** 2026-04-14  
**Scope:** All `.go` files under `discovery/`  
**Auditor:** Internal (automated pass)  
**Severity scale:** CRITICAL > HIGH > MEDIUM > LOW

---

## Executive Summary

41 Go files audited across 4 families (A, B, C, F) and the KG/DB/metrics/config/runner
packages. 2 CRITICAL bugs, 8 HIGH findings, 9 MEDIUM findings, 4 LOW findings.
The most severe issues are a data-accumulation bug in `AddLocation` that grows
unboundedly on every run, and a systematic metrics counter misclassification
in Families C and F sub-techniques.

---

## CRITICAL

### C-1 — `AddLocation` accumulates duplicate rows on every discovery cycle
**File:** `discovery/internal/kg/dealer.go:86`  
**Finding:**  
`AddLocation` uses `INSERT OR IGNORE` with a freshly generated ULID as primary
key. Since the PK is always new, the IGNORE clause **never fires**. Every crawl
cycle inserts a new `dealer_location` row for the same dealer with identical
address data but a different `location_id`. After 10 cycles, a dealer has 10
identical location rows.

```go
// dealer.go:93 — new ULID every call; OR IGNORE never fires
const q = `INSERT OR IGNORE INTO dealer_location (location_id, ...) VALUES (?,?,…)`
```

No UNIQUE constraint exists on `(dealer_id, address_line1)` or
`(dealer_id, is_primary)` in `schema.sql`.

**Callers affected:** `mobilede.go:219`, `lacentrale.go:227`, plus all Family A
and B sub-techniques.

**Fix:** Add UNIQUE INDEX `(dealer_id, address_line1, country_code)` in a
migration and change the INSERT to `ON CONFLICT DO UPDATE SET ... phone = excluded.phone`.

---

### C-2 — `break` inside `select` does not exit the outer loop (context leak)
**Files:** `mobilede.go:108`, `mobilede.go:133`, `lacentrale.go:112`,
`familia_b/family.go:104` (select on `ctx.Done()` with `break`).  
**Finding:**  
The canonical Go context-cancel pattern in several rate-limit select statements:
```go
select {
case <-ctx.Done():
    break  // BUG: exits the select, NOT the enclosing for loop
case <-time.After(m.reqInterval):
}
// code below still executes even after ctx cancelled
```
After cancellation the loop body continues executing, issuing one more HTTP
request and attempting one more upsert before the `ctx.Err() != nil` guard at
the top of the next iteration catches it. In the best case this wastes one
outbound request per family. In the worst case (if the context was cancelled
due to SIGTERM) the extra upsert occurs during shutdown.

**Correct form:** Use `return` or `goto` to exit the loop, or restructure with
a named outer label: `break outerLoop`.

**Exception:** `lacentrale.go:crawlRegion` (lines 170-175) uses `return nil`
inside the select — this is correct.

---

## HIGH

### H-1 — `SourceFamily` missing in all Family F `AddIdentifier` calls
**Files:** `mobilede.go:205-213`, `lacentrale.go:214-220`  
**Finding:**  
`DealerIdentifier.SourceFamily` is a non-pointer `string` that defaults to
`""`. The schema column `source_family TEXT NOT NULL` accepts empty string but
makes family-based queries on `dealer_identifier` return no results for any
Family F dealer.

```go
// mobilede.go:205 — SourceFamily omitted; writes "" to source_family
m.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
    IdentifierID:    ulid.Make().String(),
    DealerID:        dealerID,
    IdentifierType:  kg.IdentifierMobileDeID,
    IdentifierValue: card.Slug,
    // SourceFamily: familyID  ← missing
})
```

Same omission in `lacentrale.go`. `ValidStatus` is also not set (defaults to
`""`), silently bypassing the `valid_status DEFAULT 'UNKNOWN'` intent.

**Fix:** Set `SourceFamily: familyID` and `ValidStatus: "UNKNOWN"` in both callers.

---

### H-2 — `Confirmed` incremented where `Discovered` is required (C.3, C.4)
**Files:** `crtsh.go:156`, `hackertarget.go:183`  
**Finding:**  
Both sub-techniques call `result.Confirmed++` when `upserted == true`. Per the
runner contract, `Discovered` counts new KG entities and `Confirmed` counts
re-sightings. When `upsertSubdomain` returns `true`, a NEW web-presence row
was created — this is `Discovered`, not `Confirmed`. The `HealthCheckStatus`
gauge and main.go log line both use `result.TotalNew` which aggregates
`SubResults[*].Discovered`. Family C sub-techniques never increment any
family-level `TotalNew`.

```go
// crtsh.go:156 — wrong: should be result.Discovered++
if upserted {
    result.Confirmed++
    metrics.DealersTotal.WithLabelValues(familyID, country).Inc()
}
```

**Fix:** Change to `result.Discovered++` in both files.

---

### H-3 — No retry logic on transient HTTP errors
**Files:** All sub-technique HTTP callers (sirene.go, overpass.go, crtsh.go,
hackertarget.go, mobilede.go, lacentrale.go).  
**Finding:**  
All sub-techniques treat every non-2xx response as a permanent failure:
increment `result.Errors` and move to the next item. A transient 503 from
crt.sh or INSEE (common during maintenance windows) permanently increments
error counters and skips the domain/entity for the entire cycle. Over a long
run with noisy upstream services, the error rate in metrics will look worse
than reality.

**Fix:** Implement a generic `retry(n, backoff, fn)` helper; apply at most 3
retries with 5/15/45s delays for 5xx and connection errors. Gate on `ctx.Err()`
before each retry.

---

### H-4 — Metrics server start failure is silently ignored
**File:** `cmd/discovery-service/main.go:78-84`  
**Finding:**  
```go
go func() {
    if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
        log.Error("metrics server error", "err", err)  // only logged, not fatal
    }
}()
```
If `:9090` is already bound (e.g., previous instance still running), the
metrics goroutine exits with an error log. The discovery service continues
running with no metrics scrape endpoint. An operator monitoring `up{job="discovery"}`
in Grafana would see the target as down but the service would still be running
and accumulating data with no observability.

**Fix:** Send a fatal signal on bind failure — either `os.Exit(1)` or a channel
that the main goroutine reads before starting the discovery cycle.

---

### H-5 — `rate_limit_state` quota check is not atomic
**File:** `hackertarget.go:141-168`  
**Finding:**  
```go
remaining, err := h.remainingQuota(ctx)
// ... request issued ...
if err := h.recordUsage(ctx, 1); err != nil { ... }
```
These are two separate SQL operations without a transaction. If the process
crashes between `RunForDomain` and `recordUsage`, the actual API request was
made but the counter was not incremented. On the next run `remainingQuota`
overstates headroom. Over 50 crash-reboots, the counter could lag by 50,
meaning the service issues up to 100 requests against a 50/day limit. The free
tier at Hackertarget terminates the API key for abuse.

**Fix:** Wrap `remainingQuota → execute → recordUsage` in `db.InTx()`.

---

### H-6 — HTTP response body not drained before close (connection reuse)
**Files:** `crtsh.go:254`, `hackertarget.go:113-115`  
**Finding:**  
```go
raw, _ := io.ReadAll(io.LimitReader(resp.Body, 256))
return nil, fmt.Errorf("hackertarget: HTTP %d: %s", ...)
// defer resp.Body.Close() fires — but body may still have unread bytes
```
After reading only 256 bytes of an error body, the deferred `Close()` fires
without draining the remainder. Go's `http.Transport` only reuses TCP connections
when the response body is fully consumed. For a crawler making thousands of
requests, this causes TCP connection churn and potentially TCP_WAIT accumulation.

**Fix:** `_, _ = io.Copy(io.Discard, resp.Body)` before the `defer Close()`, or
ensure the entire body is read via `io.ReadAll` (with a sane cap).

---

### H-7 — `Family A HealthCheck` covers only FR (Sirene)
**File:** `familia_a/family.go:124-134`  
**Finding:**  
```go
func (f *FamilyA) HealthCheck(ctx context.Context) error {
    st, ok := f.techniques["FR"]
    // only checks FR Sirene
}
```
A healthy Sirene endpoint with a dead OffeneRegister path, unavailable KvK API,
or expired KBO credentials returns `nil`. The `HealthCheckStatus` gauge for
Family A is 1 even when 5 of 6 sub-techniques are non-functional.

**Fix:** Iterate all techniques, call `HealthCheck()` on each (requires adding
`HealthCheck` to the `SubTechnique` interface or a separate `HealthChecker` interface).

---

### H-8 — `FamilyB.Run` hardcodes 10s inter-request Overpass delay unconditionally
**File:** `familia_b/family.go:141-146`  
**Finding:**  
```go
select {
case <-ctx.Done():
    return fmt.Errorf("familia_b: context cancelled after Overpass %s", iso)
case <-time.After(10 * time.Second):
}
```
The 10-second sleep occurs even in tests (where `reqInterval=0` is not
configurable on FamilyB). Test suites that instantiate FamilyB and call
`runForCountry` directly will wait 10 real seconds. Currently `family_b` has no
`NewWithInterval` constructor. Tests for `overpass_test.go` and `sparql_test.go`
test the sub-techniques directly and avoid this, but any future `FamilyB`-level
integration test will be slow.

**Fix:** Make the inter-request interval a configurable field (default 10s,
0 in tests).

---

## MEDIUM

### M-1 — `context.Background()` in `srv.Shutdown` allows infinite graceful wait
**File:** `main.go:140`  
```go
_ = srv.Shutdown(context.Background())
```
Indefinite shutdown. If a long-polling HTTP request is in flight on the metrics
endpoint, shutdown blocks forever. Use a 5–10s timeout context.

---

### M-2 — Slug fallback generates non-unique identifiers
**File:** `mobilede.go:399-401`  
```go
if card.Slug == "" {
    card.Slug = "name-" + strings.ToLower(strings.ReplaceAll(card.Name, " ", "-"))
}
```
Two different dealers named "Autohaus Müller" and "Autohaus Mueller" could
produce the same slug. The UNIQUE INDEX on `(identifier_type, identifier_value)`
in `dealer_identifier` would silently ignore the second INSERT (via `INSERT OR IGNORE`),
causing the second dealer to be treated as the first dealer on lookup. The second
dealer's name/address would update the first dealer's entity, not create a distinct
one.

---

### M-3 — `slugFromPath` double-strips extension redundantly
**File:** `mobilede.go:438-443`  
Not a bug but dead code: the second `TrimSuffix(p, path.Ext(p))` is always
a no-op because the first call already strips `.html`. `path.Ext` on a
suffix-stripped string returns `""`.

---

### M-4 — `wayback.go` uses `time.Sleep` instead of context-aware sleep
**File:** `familia_c/wayback/wayback.go` (pattern)  
If the implementation uses `time.Sleep(reqInterval)` rather than
`select { case <-ctx.Done(): return; case <-time.After(reqInterval): }`,
a SIGTERM during the sleep window blocks shutdown for up to the full sleep
duration. Standard pattern in all other sub-techniques uses select; confirm
wayback.go follows the same pattern.

---

### M-5 — `ListWebPresencesByCountry` loads entire country dataset into memory
**Files:** `crtsh.go:116`, `hackertarget.go:133`  
Both call `graph.ListWebPresencesByCountry` which scans all web presence rows
for a country into a `[]*DealerWebPresence` slice. At scale (50k dealers × 5
domains = 250k rows) this allocates ~50-100 MB. No pagination or streaming.

---

### M-6 — `reconcileDiscovery` comment contradicts implementation
**File:** `kg/dealer.go:119-120`  
```go
// INSERT OR IGNORE — duplicate (dealer, family, sub_technique, discovered_at)
// combinations are dropped silently.
```
This claim is false. The `INSERT OR IGNORE` fires only on PRIMARY KEY conflict
(`record_id = new ULID`). There is no UNIQUE constraint on
`(dealer_id, family, sub_technique, discovered_at)`. Every call inserts a new
row unconditionally. The comment describes intended behavior that was never
implemented.

---

### M-7 — All sub-techniques use the global `slog.Default()` logger
**Files:** All sub-technique constructors.  
```go
log: slog.Default().With("sub_technique", subTechID),
```
The logger is constructed at instantiation time. If `slog.SetDefault()` is
called after `New()` (e.g., in test setup), the sub-technique uses the old
handler. Tests that want to capture log output must configure `slog.Default`
before calling `New`. This is an ordering dependency that is not documented.

---

### M-8 — No integration test covers the full main.go flow
**Files:** `cmd/discovery-service/` — no `main_test.go`.  
The binary entrypoint is entirely untested. Signal handling, metrics server
startup, family orchestration order, and One-Shot mode are all exercised only
by manual runs.

---

### M-9 — `config.go` does not validate country codes
**File:** `config/config.go:98-108`  
`DISCOVERY_COUNTRIES=XY` will create a run for an unsupported country. Family A
returns an error ("no sub-technique registered for country XY"), Family B
silently runs for the country (but Overpass will return zero results for an
unknown ISO code), and Family F returns an error. No upfront validation of
country list against the set of supported countries (`{"DE","FR","ES","BE","NL","CH"}`).

---

## LOW

### L-1 — `h3_index` index is always NULL (wasted space)
**File:** `schema.sql:71`  
`idx_location_h3` indexes a column that is never populated. Wastes write time
and index pages.

---

### L-2 — Hardcoded `"./data/"` paths in config defaults
**File:** `config/config.go:67,71`  
Relative paths assume the binary is run from a specific working directory.
Breaks if the service is launched from a systemd unit with `WorkingDirectory`
not set to the binary's parent.

---

### L-3 — `go.mod` module path uses `.eu` TLD but domain not confirmed live
**File:** `discovery/go.mod:1`  
`module cardex.eu/discovery` — if `cardex.eu` is not yet registered as a Go
module proxy host, `go get` for this module will fail for external consumers.
Not a runtime issue (GOWORK=off means module is resolved locally), but would
block future open-sourcing or external dependency usage.

---

### L-4 — `ptr()` helper is duplicated across packages
**Files:** `mobilede/mobilede.go:480`, `lacentrale/lacentrale.go:452`,
`passive_dns/hackertarget.go` (possibly), `crtsh/crtsh.go` (possibly).  
Each package defines its own local `func ptr(s string) *string`. This is
idiomatic Go for package-private helpers, but a shared `internal/util` package
would reduce maintenance surface.

---

## Test Coverage Summary

| Package | Test File | Key Coverage Gaps |
|---------|-----------|------------------|
| `familia_f/mobilede` | `mobilede_test.go` (4 tests) | No context-cancellation mid-run test |
| `familia_f/lacentrale` | `lacentrale_test.go` (4 tests) | No context-cancellation mid-run test |
| `familia_c/crtsh` | `crtsh_test.go` (5 tests) | No RunEnumerationForCountry test |
| `familia_c/passive_dns` | `hackertarget_test.go` (5 tests) | No transaction-failure test |
| `familia_c/wayback` | `wayback_test.go` (exists) | Unverified coverage level |
| `familia_a/*` | Per-sub-technique tests | HealthCheck not tested |
| `familia_b/*` | Per-sub-technique tests | FamilyB-level test missing |
| `kg/` | `kg_test.go` | `AddLocation` dedup not tested |
| `db/` | No test file | Migration idempotency untested |
| `config/` | No test file | Invalid country code not tested |
| `cmd/discovery-service/` | No test file | Full integration not tested |

---

## Dependency Risk

| Dependency | Version in go.mod | Known CVE? |
|------------|------------------|-----------|
| `github.com/PuerkitoBio/goquery` | v1.12.0 | None known (2026-04-14) |
| `modernc.org/sqlite` | (check go.sum) | None known |
| `github.com/prometheus/client_golang` | (check go.sum) | None known |
| `github.com/oklog/ulid/v2` | (check go.sum) | None known |
| `golang.org/x/net` | (check go.sum) | Historically had HTTP/2 CVEs — verify current version |

Action: Run `govulncheck ./...` against current `go.sum` before P5 deployment.
