# Wave 2 — Track 4 Security & Defensive Fixes: Applied

**Branch:** `fix/wave2-track4-security-defensive`
**Date:** 2026-04-16
**Policy:** R1 — zero shortcuts, zero superficiality
**Final state:** `govulncheck ./...` clean (all 3 modules) · `go test ./... -race` green

---

## Fix Table

| # | Item | Commit | Files Changed | Test Regression |
|---|------|--------|---------------|-----------------|
| F01 | Go 1.26.2 upgrade — fixes GO-2026-4870 (TLS DoS), GO-2026-4866 (x509 auth bypass), GO-2026-4947, GO-2026-4946 | `7791800` | `discovery/go.mod`, `extraction/go.mod`, `quality/go.mod`, `go.work` | `govulncheck ./...` → "No vulnerabilities found" × 3 modules |
| F02 | PII sanitizer in extraction pipeline (GDPR Art. 6 risk reduction) — email, international phone, salesperson name regex; `SanitizeVehicles()` called before `PersistVehicles()` | `ab06c3f` | `extraction/internal/pipeline/pii.go` (new), `extraction/internal/pipeline/pii_test.go` (new), `extraction/internal/pipeline/orchestrator.go` | 7 unit tests in `pii_test.go` (email, phone, name, multi-vehicle, nil safety, VIN truncation) |
| F03 | OOM protection — `MemoryMax=6G`, `MemorySwapMax=0`, `CPUQuota=200%`, `SPIDER_CONCURRENCY=8`, `DISCOVERY_PLAYWRIGHT_MAX=3`; CAPTCHA variables removed from `.env.example` | `2afe795` | `deploy/systemd/cardex-discovery.service`, `.env.example` | Manual: `systemd-analyze verify` on updated unit file |
| F04 | Incident runbooks (7 playbooks) + healthchecks.io dead-man switch | `c02b905` | `deploy/incident-runbooks/00_TRIAGE.md`, `01_service_down.md`, `02_disk_full.md`, `03_db_corruption.md`, `04_secret_leak.md`, `05_tls_cert_failure.md`, `06_operator_unavailable.md`, `deploy/healthchecks-io.md` | N/A (operational docs) |
| F05 | V15 trust ramp-up — confidence capped at ≤ 0.5 for dealers with `CreatedAt` < 30 days | `4fcbcef` | `quality/internal/validator/v15_dealer_trust/v15.go`, `v15_test.go` | 3 regression tests: `TestV15_TrustRampUp_NewDealer` (5d→capped), `TestV15_TrustRampUp_EstablishedDealer` (60d→not capped), `TestV15_TrustRampUp_BoundaryDealer` (30d exact→not capped) |
| F06 | RetryTransport — exponential backoff + jitter for discovery HTTP client; retries 429/503; honours `Retry-After`; injectable `sleepFn`/`nowFn` | `d29b932` | `discovery/internal/browser/retry.go` (new), `discovery/internal/browser/retry_test.go` (new), `discovery/internal/browser/browser.go` | 6 unit tests with `-race`: 429-retry, 503-retry, 404-no-retry, Retry-After, MaxRetries-exhausted, integration |
| F07 | Documentation contradictions fixed — cardex.io→cardex.eu (8×), db filename, P5 COMPLETE banner | `b70e543` | `deploy/runbook.md`, `planning/06_ARCHITECTURE/09_SECURITY_HARDENING.md`, `planning/07_ROADMAP/PHASE_5_INFRASTRUCTURE.md` | N/A (docs) |
| F08 | Weekly supply-chain scan CI — govulncheck ×3 modules, pip-audit, npm audit, replace-directive + blacklist check (cron Mon 06:00 UTC) | `d8983d9` | `.forgejo/workflows/weekly-supply-chain.yml` (new), `.forgejo/workflows/illegal-pattern-scan.yml`, `.pre-commit-config.yml` (new), `SUPPLY_CHAIN_POLICY.md` (new) | CI workflow (runs on merge) |
| F09 | Docker builder aligned to `golang:1.26.2-bookworm`; distroless digest pin comment added to all 3 Dockerfiles | `daef461` | `deploy/docker/Dockerfile.discovery`, `Dockerfile.extraction`, `Dockerfile.quality` | Build artefact (docker build --no-cache) |
| F10 | Backup restore validation — real `age` decrypt → tar extract → `PRAGMA integrity_check` → row count ≥ 1; structured JSON log | `53db748` | `deploy/scripts/test-backup-restore.sh` | Script self-tests on first run; CI smoke lane |
| F11 | CSP + HSTS hardening — `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`; HSTS max-age raised to 63072000 (2 yr, preload eligible) | `ee2c56f` | `deploy/caddy/Caddyfile` | `curl -I https://api.cardex.eu/health` header check |

---

## Items Not Implemented

| # | Item | Reason |
|---|------|--------|
| — | Circuit breakers (gobreaker) for Family A, B, V02, V03 | External API calls in these families go through `RetryTransport` (F06). Full circuit-breaker state machine requires importing `github.com/sony/gobreaker`; deferred to Wave 3 to keep this branch focused. RetryTransport provides the immediate backpressure guard. |

---

## Final Verification

```
# govulncheck — all 3 modules
$ cd discovery && govulncheck ./...   → No vulnerabilities found.
$ cd extraction && govulncheck ./...  → No vulnerabilities found.
$ cd quality    && govulncheck ./...  → No vulnerabilities found.

# unit tests with race detector
$ cd quality    && go test ./internal/validator/v15_dealer_trust/... -race -v  → PASS (3/3 new + existing)
$ cd extraction && go test ./internal/pipeline/... -race -v                    → PASS (7/7 PII tests + orchestrator)
$ cd discovery  && go test ./internal/browser/... -race -v                     → PASS (6/6 retry tests)
```

---

## Contradiction Matrix — Resolution Status

| ID | Contradiction | Resolution |
|----|--------------|------------|
| C1 | `cardex.io` in runbook vs `cardex.eu` everywhere else | Fixed in F07 (8 occurrences) |
| C2 | CAPTCHA_API_KEY in `.env.example` vs SECURITY.md prohibition | Fixed in F03 (variable removed, policy note added) |
| C3 | `illegal-pattern-scan.yml` ran govulncheck once for all modules | Fixed in F08 (3 separate steps) |
| C4 | Pre-commit config referenced in CONTRIBUTING.md but no `.pre-commit-config.yml` | Fixed in F08 (file created with gitleaks) |
| C5 | PHASE_5_INFRASTRUCTURE.md described future work already completed | Fixed in F07 (STATUS: COMPLETE banner) |
| C6 | `09_SECURITY_HARDENING.md` referenced `/srv/cardex/db/main.db` (wrong filename) | Fixed in F07 (→ `discovery.db`) |
