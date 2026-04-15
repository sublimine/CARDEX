# CLEANUP_REPORT.md — Repo Consolidation Deletions
**Sprint/commit:** Task 42 consolidation — 2026-04-15  
**Auditor:** Claude (automated, cross-validated against code)

---

## Files deleted (git rm)

### 1. `nginx/nginx.conf` + `nginx/placeholder.svg`

**Reason:** This nginx configuration routes to the OLD full-stack architecture: Next.js web app (`:3000`), generic `/api/` to `cardex_api`, thumbnail serving from `/data/thumbs/`. None of these services exist in the current deployment. The `placeholder.svg` was only referenced from this nginx config (as a thumbnail fallback for the `/thumb/` route).

**Superseded by:** `deploy/nginx/nginx.conf` — routes correctly to `discovery:8080`, `extraction:8081`, `quality:8082`.

**Last touched:** `329cd1a docs: CARDEX Discovery Engine` (pre-Phase-2 era).

---

### 2. `monitoring/prometheus.yml`

**Reason:** Scrapes `gateway:9091`, `pipeline:9091`, `forensics:9091`, `alpha:9091`, `legal:9091`, `clickhouse:9363`. None of these services exist in the deployed MVP. The comment "Addresses Gap G-06: No monitoring/alerting stack defined" confirms this was a gap-fill placeholder.

**Superseded by:** `deploy/observability/prometheus.yml` — scrapes `discovery:9101`, `extraction:9102`, `quality:9103` with full Alertmanager integration and 30-day retention.

**Last touched:** `a3e257a feat(risk): risk register` (pre-Phase-2 era).

---

### 3. `docker-compose.yml` (root)

**Reason:** Full-stack development compose: PostgreSQL 16, ClickHouse, Redis, MeiliSearch, all 7+ microservices (gateway, pipeline, forensics, alpha, legal, census, scheduler, imgproxy). This reflects the SPEC.md vision (3-node AX102 cluster) which is NOT the current deployed architecture. Having this file at root was actively misleading — `docker compose up` from repo root would attempt to start 15 services pointing at non-existent modules.

**Superseded by:** `deploy/docker/docker-compose.yml` — discovers, extracts, and quality-validates vehicles using only the 3 active Go services + observability.

**Last touched:** Modified (pre-Phase-2, old architecture).

---

### 4. `DISCOVERY-ENGINE.md`

**Reason:** Early design document titled "CARDEX Discovery Engine v2.0". From the era of commits describing illegal techniques (`aedbdf4 feat: motor stealth TLS (curl_cffi), evasiones Playwright`). The document pre-dates the P0 purge and the Phase 2 implementation. All its relevant content has been superseded by `planning/03_DISCOVERY_SYSTEM/` (full 15-family documentation).

**Last touched:** `329cd1a docs: CARDEX Discovery Engine` (pre-P0-purge era).

---

### 5. `DISCOVERY-ENGINE-v3.md`

**Reason:** Same era and same issues as `DISCOVERY-ENGINE.md`. Titled "CARDEX — ESQUEMA MAESTRO v3". References architecture from when stealth scraping was the primary strategy. Superseded by `planning/03_DISCOVERY_SYSTEM/`.

**Last touched:** Same commit era.

---

## Files untracked from git (kept locally, now gitignored)

### 6. `CARDEX.pdf`, `CARDEX PROJECT.pdf`, `CARDEX QUANTUM EDGE.pdf`, `CARDEX v1.pdf`, `CARDEXXX.pdf`

**Reason:** Binary PDF blobs (~27MB total) tracked in git. PDFs should not be tracked in version control — they bloat git history, cannot be diffed meaningfully, and their content is captured in `SPEC.md` and `planning/`. Added `*.pdf` to `.gitignore`. Files are preserved locally.

**Action:** `git rm --cached` (untrack without deleting).

---

## Files replaced (full content rewrite)

### 7. `README.md`

**Old content:** Described the old architecture (gateway → pipeline → forensics → alpha). Referenced directories that are not the active modules. Phase status table showed everything as stubs.

**New content:** Accurate description of discovery/extraction/quality MVP. Correct build instructions with `GOWORK=off`. Accurate architecture diagram. Correct project layout.

---

### 8. `ARCHITECTURE.md`

**Old content:** Described PostgreSQL 16 (34 tables), ClickHouse OLAP, Redis, MeiliSearch, Next.js frontend, 7 Go microservices — none of which are deployed in the current MVP.

**New content:** Accurate architecture for current implementation. Three-stage pipeline. SQLite data model. Service interfaces. V20 composite decision logic. Technology decision table.

---

### 9. `Makefile`

**Old content:** Referenced `services/api`, `services/scheduler`, `services/gateway`, `services/pipeline`. `make dev` would call the deleted root `docker-compose.yml`. `make build` would try to build old services.

**New content:** `make build/test/lint` target the three active modules with `GOWORK=off`. `make dev` uses `deploy/docker/docker-compose.yml`. `make deploy` calls `deploy/scripts/deploy.sh`.

---

## Files updated (.gitignore content)

### 10. `.gitignore`

**Added:** `*.pdf` (binary blobs), `__pycache__/`, `*.pyc` (Python cache), `*.test`, `coverage.out`, `coverage.html` (Go test artifacts), `*/cmd/*/discovery-service` etc. (compiled binaries), `TEMP_AUDIT.md` (audit scratch file).

---

## New files created

| File | Purpose |
|------|---------|
| `CONTEXT_FOR_AI.md` | Authoritative AI/developer onboarding — what is real vs. planned |
| `CHANGELOG.md` | Phase-by-phase implementation history |
| `GETTING_STARTED.md` | Developer onboarding guide |
| `CONTRIBUTING.md` | Contribution guidelines (modules, patterns, UA policy, commit format) |
| `LICENSE` | MIT license |
| `SECURITY.md` | Security policy, crawling policy, prohibited techniques |
| `TEMP_AUDIT.md` | Atomic audit inventory (gitignored, ephemeral) |
| `CLEANUP_REPORT.md` | This file |

---

## Directories NOT deleted (flagged for operator decision)

| Directory | Files | Reason kept |
|-----------|-------|-------------|
| `services/` | ~150 files | Future full-stack microservices. Not deployed. Flag: recommend deletion if full SPEC.md vision will be re-scaffolded from scratch. |
| `scrapers/` | ~85 files | Python marketplace scrapers (cleaned, CardexBot UA). Not wired to current pipeline. Flag: may represent future marketplace-indexing strategy. |
| `ingestion/` | ~15 files | Go crawlers (cleaned, CardexBot UA). Not in go.work. Flag: same as scrapers. |
| `vision/` | ~5 files | Standalone image processing Go module. Not in go.work. Flag: could be merged into quality/ V16 extension. |
| `apps/web/` | ~30 files | Next.js 15 marketplace frontend. Not deployed. Flag: future consumer interface. |
| `extensions/chrome/` | ~10 files | Chrome dealer listing overlay. Not deployed. Flag: future consumer product. |
| `e2e/` | 3 files | E2E tests for OLD architecture. `go.mod` replace directives point to wrong paths. Flag: should be replaced with E2E tests for discovery/extraction/quality. |
