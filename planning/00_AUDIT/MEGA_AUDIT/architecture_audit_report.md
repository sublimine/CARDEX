# Architecture Audit Report — Discovery Service
**Date:** 2026-04-14  
**Scope:** System architecture, deployment artifacts, observability, operational design  
**Reference documents:** `planning/06_ARCHITECTURE/`, `planning/07_ROADMAP/PHASE_2_DISCOVERY_BUILDOUT.md`,
`cmd/discovery-service/main.go`  
**Severity scale:** CRITICAL > HIGH > MEDIUM > LOW

---

## Executive Summary

The discovery service runs as a single-threaded Go binary against a local
SQLite database with a Prometheus metrics endpoint. The architecture is
functional for local development but is not deployed and missing several
operationally critical components specified in the architecture documents.
The most severe gaps are: no retry or backpressure mechanism, fully sequential
execution with no parallelism, and the complete absence of deployment artifacts
(Dockerfile, systemd unit, docker-compose).

---

## CRITICAL

### A-C1 — No deployment artifacts exist in the repository
**Finding:**  
The architecture spec (06_ARCHITECTURE/02_CONTAINER_ARCHITECTURE.md,
06_ARCHITECTURE/07_DEPLOYMENT_TOPOLOGY.md) describes an 18-container Docker
Compose deployment with systemd units, Caddyfile reverse proxy, and Hetzner
Storage Box backup. None of these artifacts are present in the repository:

- `Dockerfile` — absent
- `docker-compose.yml` — absent  
- `systemd/*.service` unit files — absent
- `Caddyfile` — absent
- `scripts/backup.sh` — absent
- Any CI/CD pipeline config (Forgejo `.woodpecker.yml` or equivalent) — absent

Phase 5 (infrastructure) is supposed to build on an already-testable service.
Without deployment artifacts, Phase 5 cannot be executed. The "deploy and run
for 7 days without manual intervention" exit criterion (CS-5-1) is blocked.

**Fix:** Before P5, create at minimum: `Dockerfile` for the discovery binary,
`docker-compose.yml` for local integration stack, and a `systemd/discovery-service.service`
template. The illegal-pattern-scan CI linter referenced in P0 must also be defined.

---

### A-C2 — Sequential execution: discovery cycle is O(countries × families)
**Finding:**  
`cmd/discovery-service/main.go:112-132` runs families in a strict nested loop:
```go
for _, country := range cfg.Countries {
    for _, fam := range families {
        result, err := fam.Run(ctx, country)
```
With 6 countries × 4 families = 24 sequential runs. Each run can take minutes
to hours depending on dataset size and rate limits. A full cycle for 6 countries
with all 15 families (Phase 2 target) at 1 req/3s, processing 20k dealers per
country, would take:

- Family A: ~8h per country × 6 = 48h
- Family B: ~20min per country × 6 = 2h
- Family C: ~5h per country × 6 = 30h (crt.sh + hackertarget)
- Family F: ~3h per country × 2 = 6h

Estimated sequential total: **86+ hours per cycle** for just 4 families.
This directly violates the "≥20min freshness HOT" SLA from success criteria.

The architecture spec (06_ARCHITECTURE/03_COMPONENT_DETAIL.md) describes a
"Worker Pool Orchestrator" that runs families in parallel per country. This is
not implemented.

**Fix:** At minimum, allow per-family goroutines with a semaphore (max 3-4
concurrent families) to parallelize within a country. SQLite WAL mode supports
concurrent reads; all writes go through a single goroutine or use serialized
transactions.

---

## HIGH

### A-H1 — No retry or resilience for external API failures
**Finding:**  
Every external HTTP call (INSEE, OffeneRegister, crt.sh, mobile.de, La Centrale,
Hackertarget, Overpass, Wikidata) either succeeds or immediately moves on.
There is no:
- Retry with exponential backoff for 5xx or transient errors
- Circuit breaker to suspend a repeatedly-failing sub-technique
- Timeout escalation policy

A single transient network interruption during an 8-hour Family A cycle
increments `TotalErrors` and silently skips a batch of dealers. The operators
have no signal distinguishing "temporary outage, resolved itself" from "API key
expired, permanent failure since yesterday."

**Fix:** Implement a `retry(ctx, n, baseDelay, fn)` wrapper. Apply to all HTTP
calls with max 3 retries and 5/15/45s delays for 5xx only (not 4xx). Add a
`failure_streak` counter per sub-technique; trigger alert if streak > 10.

---

### A-H2 — `rate_limit_state` quota is not transaction-safe across restarts
**Finding:** (See also code audit H-5)  
The Hackertarget daily quota is maintained in `rate_limit_state.reqs_today`. If
the service crashes between issuing a request and calling `recordUsage`, the
counter is not updated. Each crash during the 50-request daily budget burns a
request but doesn't record it. Over many crash-restart cycles the true consumed
count diverges from the stored count, risking over-quota usage and key
termination.

The same table is shared with `nl_kvk` (per code comments) but there is no
`ensureRateLimitTable` call in the KvK sub-technique — it relies on hackertarget
having run first to create the table. This is an undocumented order dependency.

**Fix:** Use `db.InTx()` to wrap quota-check + API call + usage-record atomically.
Add explicit `ensureRateLimitTable` call in KvK initialization.

---

### A-H3 — Metrics server failure is non-fatal but undetected
**Finding:** (See also code audit H-4)  
If the Prometheus metrics server fails to bind (EADDRINUSE or permission error),
the error is logged and the goroutine exits. The discovery service continues
running and writing data to the KG, but no metrics are exported. The only signal
is a single structured log line at startup. An operator checking Grafana will
see `cardex_discovery_health_check_status` go stale, which could be
misinterpreted as a scrape configuration issue rather than a bind failure.

No alerting rule in the observability spec covers "metrics endpoint unreachable
while service is running" because the only visibility is through the endpoint
itself.

---

### A-H4 — Single SQLite file is a SPOF for the entire discovery system
**Finding:**  
All families write to a single SQLite file (`data/discovery.db`). `db.Open()`
sets `MaxOpenConns(1)` for WAL safety. This means:

1. All discovery families compete for the same single write slot.
2. If the SQLite file is corrupted (power cut during write, filesystem error),
   the entire KG is lost. The WAL checkpoint strategy is not defined.
3. Backup is referenced in the architecture spec but not implemented.
4. The `PRAGMA journal_mode(WAL)` reduces lock contention but does not provide
   multi-writer parallelism.

For Phase 2 with 4 families, this is acceptable. For Phase 2 with 15 families
running concurrently (as the architecture envisions), write serialization through
a single `MaxOpenConns=1` connection will be the primary throughput bottleneck.

**Mitigation available within design:** Since reads don't need serialization,
allow multiple read connections with `MaxOpenConns=1` for writes by using
separate `*sql.DB` instances for read-only queries. Not urgent at current scale.

---

### A-H5 — No WAL checkpoint policy
**Finding:**  
SQLite WAL mode accumulates a write-ahead log file (`discovery.db-wal`). Without
periodic checkpointing, the WAL file grows indefinitely and reads become slower
(WAL frames must be scanned on every read). The `db.Open()` function enables WAL
but does not schedule checkpoints.

Go's `database/sql` with `modernc.org/sqlite` does not automatically checkpoint
the WAL. Under continuous write load the WAL can reach gigabytes, causing read
latency degradation.

**Fix:** Schedule `PRAGMA wal_checkpoint(TRUNCATE)` every N writes or on a
timer (e.g., every 1000 inserts or every 60 minutes of idle time).

---

## MEDIUM

### A-M1 — No dead-letter queue for failed discovery items
**Finding:**  
Dealers that fail to upsert (DB errors, network timeouts, parse failures) are
logged and `result.Errors` is incremented. There is no mechanism to retry them
in a subsequent cycle. If a transient error occurs on 5% of dealers in a cycle,
those dealers are simply not in the KG until the next full cycle. The error
counter resets each cycle and provides no cumulative view of "dealers we've
tried and consistently failed to discover."

The architecture spec describes a DLQ and manual review queue (Phase 3), but
the groundwork isn't laid in the discovery layer.

---

### A-M2 — `ListWebPresencesByCountry` returns all rows into memory (no pagination)
**Finding:**  
```go
// webpresence.go:73-124 — fetches entire country dataset
rows, err := g.db.QueryContext(ctx, q, country)
var wps []*DealerWebPresence
for rows.Next() {
    // appends all rows to slice
```
Both `crtsh.RunEnumerationForCountry` and `hackertarget.RunAll` call this.
At 50k dealers × 5 domains = 250k rows, this allocates a slice of 250k pointers
with full struct data. At ~200 bytes/struct = ~50 MB in RAM for a single country
query. For 6 countries this becomes 300 MB just for web presence data.

The architecture spec targets a 4 vCPU / 16 GB RAM VPS with a 3.8 GB steady-state
memory budget. Family C alone could consume 300 MB if run naively for all countries.

**Fix:** Use cursor-based pagination:
```go
const pageSize = 1000
for offset := 0; ; offset += pageSize {
    wps, err := graph.ListWebPresencesByCountry(ctx, country, offset, pageSize)
    if len(wps) == 0 { break }
```

---

### A-M3 — No structured correlation between discovery cycles
**Finding:**  
Each discovery cycle is a separate main.go execution (DISCOVERY_ONE_SHOT=true)
or a one-shot run within a daemon. There is no `cycle_id` or `run_id` that
correlates log entries, `discovery_record` rows, and Prometheus metrics from
a single run. If a cycle is interrupted and restarted, there is no way to:

- Determine which dealers were processed before the interruption
- Distinguish "found in cycle 1" from "found in cycle 2" in the KG
- Correlate Prometheus `cardex_discovery_dealers_total` increments to specific runs

**Fix:** Generate a UUID at startup. Pass it through the logger context and write
it to `discovery_record.source_record_id` (currently unused). Export a
`cardex_discovery_cycle_id` gauge with the run ID as label.

---

### A-M4 — No graceful degradation for missing credentials
**Finding:**  
`config/config.go` does not validate that required credentials are present.
If `INSEE_TOKEN` is empty and `FR` is in `DISCOVERY_COUNTRIES`, Family A will
start the FR sub-technique, make an API call without authorization, receive
HTTP 401, and record an error. The service does not warn at startup that
required credentials are missing.

**Fix:** Add a startup validation pass in `main.go` that checks `cfg.InseeToken != ""`
when "FR" is in `cfg.Countries`, etc. Log a startup warning (not fatal) for
each missing optional credential with a clear message about which sub-technique
is skipped.

---

### A-M5 — Health check framework (`runner/health.go`) is not integrated
**Finding:**  
`runner/health.go` defines a `HealthChecker` interface and `RunHealthChecks`
function. `main.go` does not call this. The `HealthCheck()` method on each
family is never invoked in production. The `cardex_discovery_health_check_status`
gauge is updated only reactively (after a cycle error), not proactively at
startup.

---

## LOW

### A-L1 — No observability for KG growth over time
**Finding:**  
There is no gauge or counter tracking:
- Total rows in `dealer_entity` per country
- Total rows in `dealer_web_presence` per family
- Total `discovery_record` rows (audit log size)
- SQLite file size on disk

Operators have no way to see KG growth trends in Grafana without writing ad-hoc
SQL queries. The architecture spec references 6 Grafana dashboards; none are
defined yet.

---

### A-L2 — No backup implementation
**Finding:**  
Architecture spec describes Hetzner Storage Box with `age`-encrypted backups.
No backup script, cron job, or systemd timer exists. The SQLite file has no
snapshot mechanism. A disk failure or accidental overwrite of `data/discovery.db`
would lose all discovery work to date.

---

### A-L3 — Secrets management is environment-variable-only with no validation
**Finding:**  
Credentials (`INSEE_TOKEN`, `KBO_USER`, `KBO_PASS`, `KVK_API_KEY`) are loaded
from environment variables. There is no integration with a secrets manager
(Vault, SOPS, age-encrypted `.env`). For the single-VPS deployment this is
acceptable, but credentials are logged as part of Go panic stack traces if any
function erroneously passes them as arguments. No audit trail for credential
rotation.

---

### A-L4 — `srv.Shutdown(context.Background())` blocks indefinitely
**File:** `main.go:140`  
On SIGTERM, the metrics HTTP server is shut down with no timeout. An open
scrape request from Prometheus (30s timeout by default) would block shutdown
for up to 30 seconds. Use `context.WithTimeout(context.Background(), 5*time.Second)`.

---

## Architecture Gap vs. Specification

| Spec Component | Implemented? | Gap |
|---------------|-------------|-----|
| 15 discovery families | 4/15 (A, B, C, F) | 11 families absent |
| Worker pool orchestrator | No | Sequential only |
| Retry with backoff | No | All failures permanent |
| Dead-letter queue | No | Failed items silently dropped |
| WAL checkpoint policy | No | WAL grows unbounded |
| Backup (age-encrypted) | No | No backup exists |
| Dockerfile | No | Cannot containerize |
| docker-compose.yml | No | No local integration stack |
| systemd unit files | No | Cannot deploy to VPS |
| Forgejo CI pipeline | No | No illegal-pattern scan enforced |
| Grafana dashboards | No | Metrics exported but no dashboards |
| Health check at startup | No | `runner/health.go` unused |
| Cursor pagination on KG reads | No | All-rows-in-memory pattern |
| Secrets manager integration | No | Plain env vars only |
