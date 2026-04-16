# CHANGELOG

All significant implementation milestones for CARDEX Phases 2–5.

## [Unreleased] — Sprint 29: GNN Dealer Inference + LayoutLMv3 PDF Extraction (2026-04-17)

**Branch:** `sprint/29-gnn-layoutlm`

### GNN Dealer Inference (`innovation/gnn_dealer_inference/`)
- GraphSAGE 2-layer model: SAGEConv(9→64→32) encoder + link predictor MLP + node classifier (WHOLESALE/RETAIL/BROKER/FLEET)
- 9-dim node features: listing volume, avg price/mileage (log-normalised), brand entropy, country, dealer age, V15 trust score, V21 cluster size, is_active
- Temporal split anti-leakage: edges sorted by `first_observed` timestamp; test=most recent 10%, val=next 10%
- CPU-only viable: <100K nodes ~200 MB RAM, batch inference <500ms
- PyTorch Geometric primary backend; DGL fallback documented for ARM64/Alpine
- Flask server: `POST /predict-links`, `GET /health`, `GET /metrics` (Prometheus text) on port 8501
- Checkpoint format: `{model_state, model_config, dealer_ids, backend, val_auc, test_auc}`
- 12 pytest cases: output shape, no-NaN, eval determinism, link probability range, node classifier shape, top-K count/order/range, training smoke
- 7 data loader tests: empty DB, node count, feature dim, unit range, dealer IDs, edges from VINs, temporal split leakage guard

### LayoutLMv3 PDF Extraction (`innovation/layoutlm_pdf/`)
- `extract_entities()` with fallback chain: LayoutLMv3ForTokenClassification → regex heuristics → PyMuPDF+heuristics
- Heuristic coverage: DE HRB/HRA, FR SIREN (9-digit), ES NIF (letter+digits), company suffixes (GmbH/AG/SA/SARL/SL), legal representatives, registered address
- Three fixture PDFs (DE Handelsregister, FR Extrait Kbis, ES Nota Simple) via reportlab or raw PDF fallback
- Go subprocess contract: valid JSON to stdout, exit 0 on success
- 11 pytest cases (no system deps): 9 heuristic entity tests, 2 ExtractionResult schema tests, 1 subprocess stdout-is-JSON test

### Go Integration (`discovery/internal/families/a_registries/`)
- `GNNClient`: `PredictLinks(ctx, dealerID)` → `[]PredictedLink`; env vars `GNN_SERVICE_URL`, `GNN_TOP_K`, `GNN_TIMEOUT_MS`, `GNN_SKIP`
- `dealer_predicted_links` SQLite table with `UNIQUE(dealer_a, dealer_b)` and `ON CONFLICT DO UPDATE` upsert
- Prometheus metrics: `cardex_gnn_predictions_total{result}`, `cardex_gnn_latency_seconds`, `cardex_gnn_links_stored_total`
- `EnrichDealer(ctx, db, client, dealerID)` — async-safe enrichment entry point
- 10 Go tests (race detector): schema idempotency, insert/upsert/empty persist, HTTP success/503/empty/skip, E2E with probability ordering

### Infrastructure
- Makefile: `gnn-setup`, `gnn-train`, `gnn-serve`, `gnn-test`, `layoutlm-setup`, `layoutlm-fixtures`, `layoutlm-test`
- `innovation/gnn_dealer_inference/Dockerfile` — Python 3.11-slim, CPU-only torch+PyG, graceful torch_scatter fallback
- Planning doc: `planning/02_MARKET_INTELLIGENCE/INNOVATION_GNN.md`

---

## [Unreleased] — Sprint 24: E2E integration test + terminal CLI (2026-04-16)

**Branch:** `sprint/24-e2e-terminal`

### E2E integration test (`tests/e2e/pipeline_test.go`)
- Full pipeline test: seed 3 dealers (DE/FR/ES) → E01 JSON-LD extraction → V01–V19 quality validators → SQLite persistence
- Three HTML fixtures committed at `tests/fixtures/e2e/` (BMW 320d DE, Renault Mégane FR, SEAT León ES)
- Valid ISO 3779 VINs with correct check digits; deterministic; no external network
- Assertions: listings > 0, V01 VIN pass, V07 price sanity pass, composite score ≥ 60%, Prometheus counter incremented
- Thin public facade packages (`discovery/run`, `extraction/run`, `quality/run`) expose internal types via Go type aliases
- Invoke: `go test ./tests/e2e/... -tags=e2e -v` or `make e2e`
- All 3 dealers pass at 90.9% composite score (MANUAL_REVIEW)

### Terminal buyer CLI (`frontend/terminal/`)
- Module `cardex.eu/cli`; binary `cardex-cli`; build via `make cli`
- `cardex search` — 9 filters (country, make, model, year-min/max, price-min/max, km-max, score, limit, page)
- `cardex show <id>` — listing detail panel + per-validator pass/fail breakdown
- `cardex stats` — aggregate counts, country breakdown, avg quality score
- ANSI table rendering via `charmbracelet/lipgloss v1.1.0`; CLI framework `spf13/cobra v1.9.1`; reads shared SQLite (`modernc.org/sqlite`)
- `CARDEX_DB_PATH` env var or `./data/discovery.db` default

### CI
- Forgejo workflow `e2e.yml` added: `e2e` job (go work sync + e2e test) and `unit` job (all modules + CLI build)

---

## [Phase 5] — Infrastructure (2026-04-14)

**Commit:** `79254b0 feat(P5-sprint23): infrastructure scaffolding`

- Multi-stage Dockerfiles for discovery/extraction/quality (Go 1.25 builder → distroless:nonroot)
- Docker Compose: dev stack (build from source) + prod overlay (pull from registry)
- systemd units for all 3 services: `MemoryMax`, `CPUQuota`, `NoNewPrivileges`, `ProtectSystem=strict`, `systemd-creds` for secrets
- Caddy reverse proxy: TLS 1.3, auto Let's Encrypt, HSTS, security headers
- Prometheus scrape config targeting `:9101`, `:9102`, `:9103`
- Grafana dashboards: discovery dealer metrics, extraction strategy metrics, quality V01–V20 + composite
- Alertmanager: 8 alert rules (ServiceDown, ErrorRateHigh, DiskSpaceLow, BackupStale, WALSizeHigh, QueueUnbounded)
- Scripts: `deploy.sh` (idempotent with auto-rollback), `backup.sh` (age-encrypted WAL checkpoint → rsync), `restore.sh`, `health-check.sh`, `secrets-generate.sh`, `test-deploy-local.sh`, `test-backup-restore.sh`
- Secrets management: age keypair + TLS certs + systemd-creds pattern documented
- Step-by-step `runbook.md`: 12 steps, fresh Debian 12 → production in ~45 min
- Nginx fallback config (alternative to Caddy for restricted environments)
- OPEX: ~€22/month (Hetzner CX42 ~€18 + Storage Box ~€3 + domain ~€1.25)

---

## [Phase 4, Sprint 22] — Quality validators V16–V20 (2026-04-14)

**Commit:** `400da06 feat(P4-sprint22): V16 phash + V17 sold + V18 language + V19 currency + V20 composite (Phase 4 complete 20/20)`

- **V16** `v16_photo_phash`: perceptual hashing via `goimagehash` (distance ≤4 = duplicate). Injectable `HashStore` interface.
- **V17** `v17_sold_status`: HTTP 410 → CRITICAL; sold keywords in 6 languages; schema.org `ItemAvailability` parsing.
- **V18** `v18_language_consistency`: listing language vs. dealer country (EN always accepted). Country map for DE/AT/CH/FR/BE/NL/ES/IT/LU.
- **V19** `v19_currency`: zero price → CRITICAL, negative → CRITICAL, >€1M → WARNING, CH country → INFO.
- **V20** `v20_composite`: reads V01–V19 results, weights 176 pts, produces PUBLISH/MANUAL_REVIEW/REJECT decision.
- `storage.go` `GetValidationResultsByVehicle()` fully implemented (previously stubbed).
- Config: `QUALITY_SKIP_V16` through `QUALITY_SKIP_V20` env vars.
- **Phase 4 complete: 20/20 validators.**

---

## [Phase 4, Sprint 21] — Quality validators V11–V15 (2026-04-13)

**Commit:** `8f6eb98 feat(P4-sprint21): V11 NLG quality + V12 cross-source dedup + V13 completeness + V14 freshness + V15 dealer trust (15/20)`

- **V11** `v11_nlg_quality`: stopword ratio, boilerplate detection, length checks.
- **V12** `v12_cross_source_dedup`: fingerprint_sha256 collision detection across sources.
- **V13** `v13_completeness`: required fields populated check (make, model, year, price, photos).
- **V14** `v14_freshness`: listing age delta, last-seen check.
- **V15** `v15_dealer_trust`: dealer trust score based on history.

---

## [Phase 4, Sprint 20] — Quality validators V05–V10 (2026-04-13)

**Commit:** `30a9633 feat(P4-sprint20): V05 image quality + V06 photo count + V07 price + V08 mileage + V09 year + V10 URL liveness (10/20 validators)`

- **V05–V10**: Image quality, photo count, price range, mileage range, year range, URL liveness.

---

## [Phase 4, Sprint 19] — Quality scaffolding + V01–V04 (2026-04-13)

**Commit:** `7e009d3 feat(P4-sprint19): scaffolding quality module + V01 VIN checksum + V02 NHTSA + V03 DAT + V04 NLP makemodel`

- `quality/` Go module scaffolded with `pipeline.Vehicle`, `pipeline.ValidationResult`, `pipeline.Storage` interface.
- SQLite storage with WAL, `modernc.org/sqlite` (pure Go, CGO-free).
- **V01**: VIN checksum (17-char + transliteration table + check digit).
- **V02**: NHTSA recall API (api.nhtsa.dot.gov).
- **V03**: DAT valuation lookup.
- **V04**: NLP make/model normalisation and consistency.

---

## [Phase 3, Sprint 18] — Extraction E08–E12 complete (2026-04-13)

**Commit:** `8dc8079 feat(P3-sprint18): E08 PDF + E09 Excel/CSV + E10 email + E11 manual queue + E12 edge stub (12/12 — Phase 3 complete)`

- PDF extraction (pdftotext), Excel/CSV parsing, email/EDI ingestion, manual queue, edge stub.
- **Phase 3 complete: 12/12 extraction strategies.**

---

## [Phase 3, Sprints 16–17] — Extraction E03–E07 (2026-04-13)

**Commits:** `82d3a25`, `86944a2`

- **E03**: Sitemap XML (multi-level crawl, up to 50K URLs).
- **E04**: RSS/Atom feed parsing.
- **E05**: DMS API (Incadea, MotorManager, Autentia native REST APIs).
- **E06**: Microdata + RDFa parsing.
- **E07**: Playwright XHR interception for JS-heavy listing pages.

---

## [Phase 3, Sprint 15] — Extraction scaffolding + E01–E02 (2026-04-13)

**Commit:** `6b77e4d feat(P3-sprint15): scaffolding extraction module + E01 JSON-LD + E02 CMS REST`

- `extraction/` Go module with `Extractor` interface and strategy registry.
- **E01**: JSON-LD structured data (schema.org Car/Vehicle).
- **E02**: CMS REST API (WordPress WP-JSON endpoint).

---

## [Phase 2, Sprints 14-E] — Discovery: Family E + DMS (2026-04-13)

**Commit:** `1c40f6b feat(P2-sprint14-E): Familia E -- DMS infrastructure mapping (closes A-O 15-family system)`

- **Family E**: DMS infrastructure detection (Incadea, MotorManager, Autentia, AutoBiz) — closes the 15-family system.
- **Family O**: Press archives (GDELT + RSS + Wayback stub).
- **Phase 2 complete: 15/15 discovery families.**

---

## [Phase 2, Sprints 1–13] — Discovery families A–N (2026-04-12 – 2026-04-13)

Key commits: `089d741` (sprint 1) through `f24f882` (sprint 13).

- **Families A–N** implemented iteratively across sprints 1–13.
- Family A: FR Sirene, DE Handelsregister, NL KvK, BE KBO, ES AEOC, CH UID.
- Family B: OSM Overpass, Wikidata SPARQL.
- Families C–D: Wayback/crt.sh, CMS fingerprinting.
- Family F: AutoScout24 + La Centrale Pro (Playwright).
- Family G: BOVAG, TRAXIO, Mobilians.
- Family H: VWG + BMW + Mercedes + Stellantis + Toyota + Hyundai + Renault + Ford OEM locators.
- Family I: TÜV/DEKRA/Applus inspection networks.
- Families J–N: sub-jurisdictions, SearXNG, social, VIES/UID-Register, infra intel.

---

## [Phase 1] — Planning & specification (pre-2026-04-12)

- `planning/` directory: 7 sections, full specification for discovery (15 families), extraction (12 strategies), quality (20 validators), architecture, roadmap.
- Innovation roadmap: 5 future AI/ML enhancements (GNN, VLM, RAG, Chronos-2, BGE-M3). **These are future, not implemented.**

---

## [Phase 0] — Legal compliance purge (2026-04-14)

**Commit:** `ed5e54f cleanup(P0): purga de código ilegal legacy — stealth, proxies, UA spoofing`

- Removed: `scrapers/dealer_spider/stealth_http.py`, `stealth_browser.py`, `scrapers/common/proxy_manager.py`.
- Removed: `curl_cffi` from all requirements.txt files.
- Rewrote: all UA strings to `CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)`.
- Added: Forgejo CI workflow `illegal-pattern-scan.yml` to block future violations.
