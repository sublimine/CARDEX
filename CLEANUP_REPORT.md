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

## Round 2 deletions (Task 43 — 2026-04-15)

### 11. `services/` (9 Go modules, ~150 files)

**Modules:** alpha, api, census, forensics, frontier, gateway, imgproxy, legal, pipeline, scheduler.

**Reason:** None of these modules are imported by or deployed by discovery/extraction/quality/deploy. The `go.work` listed them but `GOWORK=off` is used for all production builds. These represent the ambitious full-stack vision from `SPEC.md` (3-node AX102) but that architecture has not been built and the current MVP deliberately uses a simpler stack. They are not "future components waiting to be wired up" — they are a different architectural era. If the full vision is ever revived, these should be re-scaffolded fresh with updated dependencies (most use Go 1.22–1.24, now at Go 1.25).

**Cross-reference check:** Zero imports from discovery/, extraction/, quality/, deploy/. False-positive grep matches were URL strings containing "/services/" as a path component in dealer website URLs.

---

### 12. `scrapers/` (~85 Python files)

**Reason:** Python marketplace scrapers for AutoScout24, mobile.de, AutoHero, Marktplaats, La Centrale, etc. Cleaned in P0 purge (CardexBot UA, no stealth). NOT wired to the current extraction/ pipeline (which targets individual dealer websites, not marketplace aggregators). No Go module dependency. No reference from active modules. Represents an entirely different data acquisition strategy (marketplace scraping) vs. what extraction/ does (direct dealer site extraction via E01–E12). Per SPEC.md V6: "No scraping: All data from licensed B2B feeds" — so even honest marketplace scraping is out of scope for the institutional regime.

---

### 13. `ingestion/` (~15 files — Go module + compiled binaries)

**Reason:** `api_crawler` and `sitemap_vacuum` — H3-based crawler for mobile.de and sitemap vacuum tool. Cleaned in P0 purge. Go 1.21 module, NOT in go.work. Not referenced by any active module. Compiled `.exe` binaries already gitignored. Completely superseded by the discovery/extraction pipeline.

---

### 14. `vision/` (~5 files — Go module)

**Reason:** Standalone image processing module (`github.com/cardex/vision`, Go 1.25). Uses `goimagehash` + Redis worker for image pHash. NOT in go.work. Not referenced by any active module. The same `goimagehash` functionality is already implemented in `quality/internal/validator/v16_photo_phash/` as part of the quality pipeline. Having a separate standalone service for this is premature.

---

### 15. `e2e/` (3 files — Go module)

**Reason:** E2E tests for the OLD architecture: imports `github.com/cardex/alpha`, `github.com/cardex/forensics`, `github.com/cardex/gateway`, `github.com/cardex/pipeline` — all of which have been deleted. The `go.mod` replace directives pointed to `../alpha`, `../forensics`, etc. (wrong paths — they were under `services/`). These tests do not cover discovery, extraction, or quality. They cannot build now that `services/` is deleted. No value in keeping broken tests for a deleted architecture.

---

### 16. `apps/` (Next.js 15 web app)

**Reason:** `apps/web/` — marketplace frontend with deck.gl maps, CRM pages, analytics, MeiliSearch integration. NOT deployed. Requires PostgreSQL, MeiliSearch, Redis — none of which exist in the current MVP. The project is API-only in its current state. Future frontend work should be started fresh when the API layer (services/) is built out, not carried as dead weight now.

---

### 17. `extensions/` (Chrome extension)

**Reason:** Chrome Manifest V3 extension — car listing overlay. NOT deployed. No build system, no tests. Consumer product feature for a future phase. Deleting doesn't affect any current functionality.

---

### 18. `scripts/` (6 files — SQL + shell init scripts)

**Reason:** PostgreSQL schema (`init-pg.sql`, 46KB), ClickHouse schema (`init-ch.sql`), MeiliSearch indices (`init-meili.sh`), Redis config (`init-redis.sh`), demo seed (`seed-demo.sql`, `seed-vehicles.py`). ALL for the old architecture stack. The current MVP uses SQLite (no init scripts needed; schema created by `modernc.org/sqlite` at startup). The `deploy/` scripts are completely separate (`deploy/scripts/`). Having PostgreSQL init scripts in the repo with no PostgreSQL in the deployment is actively misleading.

---

### 19. `go.work` — updated

Removed `./e2e` and all `./services/*` entries (now deleted). Retained: `./discovery`, `./extraction`, `./internal/shared`, `./quality`.

---

## Final state

**Total files before Task 42+43:** 714  
**Total files after Task 42+43:** 425 (before go.work update staged)  
**Deleted:** ~289 files across 8 directories + 11 binary blob PDFs untracked
