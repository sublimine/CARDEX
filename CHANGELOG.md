# CHANGELOG

All significant implementation milestones for CARDEX Phases 2–5.

## [Sprint 35] — CARDEX PULSE: Dealer Health Score (2026-04-18)

**Branch:** `sprint/35-dealer-pulse`  
**Module:** `discovery/internal/pulse/` + `discovery/cmd/pulse-service/`

### Core Package
- `model.go` — `DealerHealthScore`, `HistoryPoint`, `TierFromScore()`, tier constants (healthy/watch/stress/critical)
- `config.go` — `WeightConfig`, `DefaultWeights()`, `LoadWeights(path)` (JSON override)
- `signals.go` — `ComputeSignals()`: 7 SQL queries against `vehicle_record` (liquidation ratio, price trend, volume z-score, time on market, ToM delta, composite score delta, brand HHI, price vs market)
- `scorer.go` — `Score()`, `DetectTrend()`, `CollectRiskSignals()`, per-signal stress normalisation
- `storage.go` — `EnsureTable()`, `SaveSnapshot()`, `LoadHistory()`, `Watchlist()`, `PruneOld()`
- `metrics.go` — `cardex_pulse_critical_dealers_total`, `cardex_pulse_watch_dealers_total`, `cardex_pulse_score_compute_duration_seconds`
- `handler.go` — HTTP mux: `GET /pulse/health/{id}`, `GET /pulse/watchlist`, `GET /pulse/trend/{id}`

### Scoring Model
- Health score = 100 × (1 − Σ wᵢ × stress_i), clamped [0, 100]
- Default weights: liquidation 20%, price_trend 15%, volume 15%, ToM 15%, composite_delta 10%, HHI 10%, price_vs_market 15%
- Tiers: healthy ≥ 70, watch ≥ 50, stress ≥ 30, critical < 30

### Database — Migration v8
- `dealer_health_history` table + `idx_dhh_dealer_time` index

### pulse-service Binary
- HTTP server on `:8504`; env vars: `PULSE_DB_PATH`, `PULSE_ADDR`, `PULSE_WEIGHTS_PATH`, `PULSE_RETAIN_DAYS`
- Graceful shutdown on SIGINT/SIGTERM; Prometheus `/metrics`, `/healthz`

### CLI
- `cardex pulse show <dealer_id>` — ANSI signal table, tier badge, trend indicator
- `cardex pulse watchlist [--tier watch|stress|critical] [--country DE]` — worst-first
- `CARDEX_PULSE_URL` env var (default: `http://localhost:8504`)

### Tests
- 20 tests, `go test -race`: TierFromScore boundaries (5), healthy/stressed scoring (2), BrandHHI single/equal (2), DetectTrend 4 cases, CollectRiskSignals 3 cases, EnsureTable idempotent, Save+Load history, Watchlist filter, weights sum to 1.0

---

## [Sprint 36-39] — CARDEX Routes: Fleet Disposition Intelligence (2026-04-18)

**Branch:** `sprint/36-routes-disposition`  
**Module:** `innovation/routes/` (Go, `cardex.eu/routes`)

### Market Spread Calculator (`spread.go`)
- `SpreadCalculator.Calculate(make, model, year, km, fuel)` → `MarketSpread`
- Cohort: `vehicle_record JOIN dealer_entity`, year ±1, km bracket (0-30k/30-80k/80k+)
- `PricesByCountry` map with `AVG(price_gross_eur)*100` per country, `SamplesByCountry`
- `BestCountry` / `WorstCountry` / `SpreadAmount` / `Confidence` (exp-decay on sample count)

### Disposition Optimizer (`optimizer.go`)
- `Optimizer.Optimize(OptimizeRequest)` → `DispositionPlan`
- Evaluates all 6 countries × 3 channels (dealer_direct / auction / export)
- Per route: market price, VAT/customs (Tax Engine), transport cost (carrier matrix)
- Auction: adds 3% buyer premium to transport cost
- Routes sorted by `NetProfit = EstimatedPrice − VATCost − TransportCost`
- `TotalUplift`: best net profit vs selling locally

### Transport Cost Matrix (`transport.go`)
- Static defaults for all 30 directional country pairs (DE/FR/ES/NL/BE/CH)
- YAML override: `transport_costs.yaml` — configurable real carrier rates per pair
- `timeToSellDays`: calibrated static estimates by country/channel (BCA 2024 data)

### Tax Engine Integration (`tax.go`)
- `DefaultTaxEngine.VATCost(from, to, price)`: intra-EU B2B = €0; EU→CH = 8.1%+€500; CH→EU = dest VAT+€400
- Mirrors `cardex.eu/tax` logic; standalone (no module dependency)

### Batch Optimizer (`batch.go`)
- `BatchOptimizer.Optimize([]VehicleInput)` → `BatchPlan`
- Per-destination concentration cap: ≤20% of fleet to single country
- Vehicles sorted by best net profit (highest-value first, for fair cap allocation)
- `BatchSummary` helper with route breakdown, uplift totals

### Gain-Share Calculator (`gainshare.go`)
- `CalculateGainShare(actual, baseline, feeRate)` → `GainShare{Uplift, Fee, NetToClient}`
- Fee rate 15–20%; zero fee when actual ≤ baseline; error on rate > 1
- Ready for post-sale invoicing integration

### HTTP API (`server.go`, port 8504)
- `GET /health` → `{status, db, time}`
- `GET /routes/spread?make=&model=&year=[&km&fuel]` → `MarketSpread`
- `POST /routes/optimize` → `DispositionPlan` (404 if no data)
- `POST /routes/batch` → `BatchPlan`

### Go CLI (`frontend/terminal/cmd/cardex/routes.go`)
- `cardex routes optimize --make BMW --model 320d --year 2021 --km 45000 --country FR`
- `cardex routes spread --make BMW --model 320d --year 2021`
- `cardex routes batch --input fleet.csv --output plan.json`
- Fleet CSV: `vin,make,model,year,mileage_km,fuel_type,country`
- Renders: ANSI route table, market spread by country, batch summary with destination breakdown

### Test suite (35 tests, `go test -race`)
- Transport: DE→FR cost, DE→ES > DE→NL, symmetry, same-country=0, YAML override, unknown pair penalty
- Tax: intra-EU=0, EU→CH 8.1%+€500, CH→EU dest VAT+€400, same country=0
- Spread: 5-country fixture, spread amount, confidence, empty result
- Optimizer: best route net profit, intra-EU zero VAT, CH VAT cost present, sorted, no-data empty plan, formula
- Batch: 10-vehicle all assigned, concentration ≤20%, empty input, validation
- Gain-share: 15% fee, 20% fee, no-uplift=0, invalid rate error
- HTTP: health 200, missing params 400, no-data 404, success 200, invalid JSON 400

### Makefile
- `make routes-build` — compile `bin/routes-server`
- `make routes-serve` — run API on :8504
- `make routes-test` — full test suite

### Planning
- `planning/INNOVATION/ROUTES_DISPOSITION.md` — exhaustive architecture doc, market context, API reference, deployment guide

---

## [Unreleased] — Sprint 33: EV Watch — Battery Anomaly Signal (2026-04-18)

**Branch:** `sprint/33-ev-watch`

### EV Anomaly Analyzer (`quality/internal/ev_watch/`)
- `EVAnomalyScore` struct — vehicle identity + cohort stats + z-score + SoH classification
- `Analyzer.RunAnalysis()` — loads all EV listings (fuel_type IN electric/hybrid_plugin/plug_in_hybrid), groups by (make, model, year, country) cohort, runs OLS regression (price ~ mileage_km), computes z-score of price residuals
- OLS fallback: constant-X denominator → use `mean(y)` as predicted price, avoiding division by zero
- `MinCohortSize = 20` — cohorts below threshold silently skipped (insufficient statistical power)
- `AnomalyFlag`: `z < -1.5` (strict); `EstimatedSoH`: "suspicious" z<-2.0 / "below_average" z<-1.5 / "normal"
- `Confidence = min(1.0, cohortSize/100.0)` — saturates at 100 listings
- `EnsureSchema()` — `ev_anomaly_scores` table with UNIQUE(vehicle_id) upsert; 4 indexes
- Prometheus: `cardex_ev_watch_anomalies_detected_total`, `severe_anomaly_total`, `cohort_size` histogram, `analysis_duration_seconds`

### HTTP API (`quality/internal/ev_watch/handler.go`)
- `GET /ev-watch/anomalies` — query params: country, make, model, year, min_z, max_z, min_confidence, limit, anomaly_only
- `GET /ev-watch/cohort` — make+model required; returns count/mean/stddev/price-range/anomaly counts
- `POST /ev-watch/run` — triggers full analysis run, returns scored/anomalies/duration_ms
- `RunAnalysisWithContext()` — called from quality service cron; structured log on severe anomalies (VIN, z-score, price_eur, cohort_size)

### Quality Service Integration (`quality/cmd/quality-service/main.go`)
- EV watch HTTP routes registered on `/metrics` mux
- Daily cron: `evWatchInterval = 24h`; resets on each cycle; structured `slog.Warn` on z < -2.0 AND cohort >= 30

### CLI (`frontend/terminal/cmd/cardex/ev_watch.go`)
- `cardex ev-watch list [--country --make --model --year --min-confidence --limit --all]` — ANSI table with SoH color badges
- `cardex ev-watch cohort --make --model [--year --country]` — cohort stats + ASCII z-score histogram (7 buckets, color-coded by severity)
- `sohStyle()` — 🔴 suspicious / 🟡 below_avg / 🟢 normal via lipgloss

### Tests (`quality/internal/ev_watch/analyzer_test.go`)
- 15 tests: anomaly detection (50 normal + 3 anomalous fixtures), non-EV filtering, small cohort skip, severity levels, exact MinCohortSize boundary, upsert idempotency, confidence range [0,1], multi-country independence, OLS perfect line, OLS constant-X, mean/stddev, cohortConfidence, estimateSoH, schema idempotency, detectedAt timestamp
- `go test ./... -race`: all 27 packages pass; govulncheck: no vulnerabilities

### Planning
- `planning/INNOVATION/EV_WATCH.md` — methodology, thresholds, deployment, roadmap

---

## [Unreleased] — Sprint 31: Chronos-2 Time-Series Price Forecasting (2026-04-17)

**Branch:** `sprint/31-chronos-forecasting`

### Data Pipeline (`innovation/chronos_forecasting/data_pipeline.py`)
- SQL aggregation: `vehicle_record JOIN dealer_entity` → daily price_mean/p25/p75/volume/km_mean per (country, make, model, year_range)
- `_year_bucket(year, width=3)` — 3-year buckets anchored to 2018 epoch
- `SeriesKey.to_filename()` — sanitized CSV filenames (regex, no accented chars)
- `run_pipeline(db_path, out_dir, min_points=30)` — discards sparse series; returns list of written paths
- `make_fixture_db(db_path, rows)` — in-memory SQLite fixture for tests

### Forecasting Engine (`innovation/chronos_forecasting/forecaster.py`)
- **Primary:** `chronos-forecasting>=2.2.2`, model `amazon/chronos-bolt-mini` (28M, ~200 MB RAM, ~1-2s CPU)
- **Fallback:** `statsforecast` (AutoETS + AutoARIMA ensemble, zero ML deps); auto-detected on import failure
- Override model via `CHRONOS_MODEL` env var; override backend via `CHRONOS_BACKEND=statsforecast`
- `mase()` / `smape()` — backtest metrics; MASE < 1.0 confirms model beats naïve baseline
- 20% held-out tail backtest; raises `ValueError` on series < 10 points

### Batch Mode (`innovation/chronos_forecasting/forecast_all.py`)
- `run_batch(timeseries_dir, out_dir, horizon, workers)` with `ThreadPoolExecutor`
- Writes `_batch_summary.json` with total/succeeded/failed/elapsed

### Forecast API (`innovation/chronos_forecasting/serve.py`)
- FastAPI on port 8503 (`FORECAST_PORT` env var); `GZipMiddleware`
- `GET /health`, `GET /series` (metadata list), `POST /forecast` (pydantic v2 validated)
- 404 on missing series; 422 on horizon=0 or >365 or series too short

### Python packaging
- `requirements.txt` — full stack: Chronos-2 + statsforecast + FastAPI + pytest
- `requirements-minimal.txt` — statsforecast only, <100 MB, zero ML deps
- `Dockerfile` — Python 3.11-slim; `TIMESERIES_DIR` + `FORECAST_PORT` env vars; port 8503

### pytest suite (38 tests, no network/GPU required)
- `test_pipeline.py` (10 tests) — year buckets, SeriesKey, 60-day output, schema, price stats, min_points filter, volume sum, empty DB, date sort
- `test_forecaster.py` (12 tests) — MASE/sMAPE unit tests; integration tests skipped if no backend installed (MASE < 1.0 on linear trend, p10≤p50≤p90, horizons 30/60/90, short series raises)
- `test_serve.py` (8 tests) — TestClient with monkeypatched TIMESERIES_DIR; health, /series metadata, /forecast structure + CI ordering, 404, 422 horizon validation

### Go CLI (`frontend/terminal/cmd/cardex/forecast.go`)
- `cardex forecast --make BMW --model 3er --year-min 2018 --year-max 2020 --country DE --horizon 30 [--spark]`
- HTTP client to FastAPI with 120s timeout; `FORECAST_URL` env var
- Renders: series metadata, forecast table (sampled rows), trend (↑/↓/→ at ±2%), %Δ, 90% CI band
- `--spark`: Unicode block sparkline (▁▂▃▄▅▆▇█) of p50 series
- MASE backtest with ✓/⚠ baseline comparison

### Makefile
- `make forecast-pipeline` — SQLite → CSVs
- `make forecast-serve` — uvicorn on :8503 with --reload
- `make forecast-test` — pytest suite

### Planning
- `planning/02_MARKET_INTELLIGENCE/INNOVATION_CHRONOS.md` — architecture, RAM budget, deployment, roadmap

---

## [Sprint 30] — Local RAG Search — nomic-embed-text + FAISS + Llama 3.2 (2026-04-17)

**Branch:** `sprint/30-rag-search`

### RAG search service (`innovation/rag_search/`)
- `config.py` — central config: model, paths, FAISS params, API port, rate-limit; all params env-overridable
- `indexer.py` — SQLite `vehicle_record` -> nomic-embed-text-v1.5 (768 dims, L2-normalised, `search_document:` prefix) -> FAISS IVF-Flat (nlist=100; Flat fallback for small datasets); `--incremental` skips known IDs
- `query_engine.py` — query embed (`search_query:` prefix) -> FAISS top-50 ANN -> hard filters (country, price, km, year, fuel) -> top-20 `SearchResult` list
- `llm_reranker.py` — opt-in Llama 3.2 3B Q4 reranker via llama-cpp-python (~2 GB RAM, 5-10s/query); parses JSON score array; falls back to cosine order on error
- `serve.py` — FastAPI :8502: `POST /search`, `GET /health`, `POST /reload`; 100 req/min rate limit (slowapi)

### Python packaging
- `requirements.txt` — faiss-cpu, sentence-transformers, torch, fastapi, uvicorn, pydantic, slowapi
- `Dockerfile` — Python 3.11-slim, pre-downloads nomic model at build time; data + models volumes

### Go CLI: `cardex search-natural`
- New subcommand wired into `newRootCmd()`; calls `POST /search` on RAG server; renders ANSI table
- Flags: `--country`, `--price-min/max`, `--km-max`, `--year-min/max`, `--fuel`, `--top`, `--rerank`
- SQL keyword fallback (LIKE on make/model) when RAG server unavailable; `CARDEX_RAG_URL` env var

### Makefile
- `make cli` — build `bin/cardex-cli`
- `make rag-index` / `rag-index-incremental` / `rag-serve` / `rag-test`

### Tests (mocked embedding model — no GPU, no network required)
- `test_indexer.py` (5 tests) — index size == 10 fixtures, id_map coverage, persistence, incremental no-op
- `test_query.py` (6 tests) — FAISS search, BMW DE in top-5, country/price/km filters, empty index guard
- `test_reranker.py` (7 tests) — reorder by LLM scores, count, empty input, bad output fallback, score parsing

### Planning
- `planning/02_MARKET_INTELLIGENCE/INNOVATION_RAG.md` — architecture, component docs, RAM budget, cron schedule

---

## [Sprint 29] — GNN Dealer Inference + LayoutLMv3 PDF Extraction (2026-04-17)

**Branch:** `sprint/29-gnn-layoutlm`

### GNN Dealer Inference (`innovation/gnn_dealer_inference/`)
- GraphSAGE 2-layer model: SAGEConv(9→64→32) encoder + link predictor MLP + node classifier (WHOLESALE/RETAIL/BROKER/FLEET)
- 9-dim node features: listing volume, avg price/mileage (log-normalised), brand entropy, country, dealer age, V15 trust score, V21 cluster size, is_active
- Temporal split anti-leakage: edges sorted by `first_observed` timestamp; test=most recent 10%, val=next 10%
- CPU-only viable: <100K nodes ~200 MB RAM, batch inference <500ms
- PyTorch Geometric primary backend; DGL fallback documented for ARM64/Alpine
- Flask server: `POST /predict-links`, `GET /health`, `GET /metrics` (Prometheus text) on port 8501
- Checkpoint format: `{model_state, model_config, dealer_ids, backend, val_auc, test_auc}`
- 12 pytest cases; 7 data loader tests; temporal leakage guard

### LayoutLMv3 PDF Extraction (`innovation/layoutlm_pdf/`)
- `extract_entities()` with fallback chain: LayoutLMv3ForTokenClassification → regex heuristics → PyMuPDF+heuristics
- Heuristic coverage: DE HRB/HRA, FR SIREN, ES NIF, company suffixes, legal reps, registered address
- Three fixture PDFs (DE Handelsregister, FR Extrait Kbis, ES Nota Simple)
- 11 pytest cases, Go subprocess contract

### Go Integration (`discovery/internal/families/a_registries/`)
- `GNNClient`: `PredictLinks(ctx, dealerID)` → `[]PredictedLink`
- `dealer_predicted_links` SQLite table with upsert; 10 Go tests (race detector)
- Prometheus metrics: `cardex_gnn_predictions_total`, `cardex_gnn_latency_seconds`, `cardex_gnn_links_stored_total`
- Makefile: `gnn-setup`, `gnn-train`, `gnn-serve`, `gnn-test`, `layoutlm-setup`, `layoutlm-fixtures`, `layoutlm-test`

---

## [Sprint 28] — E12 Edge Tauri gRPC Push MVP (2026-04-16)

**Branch:** `sprint/28-edge-tauri-grpc`

- **E12 gRPC server** (`extraction/internal/extractor/e12_edge/server/`):
  - Client-streaming `PushListings` RPC + unary `Heartbeat`
  - API key auth (SHA-256 hash in `edge_dealers` SQLite table)
  - Per-dealer rate limit: 1000 listings/60s sliding window
  - Prometheus: `cardex_edge_push_listings_total{dealer,status}`, `cardex_edge_push_latency_seconds`
  - 7 Go tests pass with `-race`: heartbeat, valid batch, short VIN, bad key, multi-batch, extraction_method tag, DB lifecycle
- **Proto definition** (`extraction/api/proto/edge_push.proto`) + hand-written wire-compatible Go types in `extraction/api/edgepb/`; `make proto` for protoc generation
- **Dealer CLI** (`extraction/cmd/cardex-dealer/`): `register --name --country --vat` (VIES validated), `list`, `revoke`
- **Edge Push server binary** (`extraction/cmd/edge-push-server/`): TLS 1.3, Prometheus `/metrics :9102`
- **Tauri client scaffold** (`clients/edge-tauri/`): Rust backend (login/push_vehicle/push_csv/heartbeat), HTML/CSS/JS UI (Add Vehicle, CSV import, history, heartbeat indicator), auto-update
- **Security**: grpc upgraded v1.71.1 → v1.79.3 (GO-2026-4762 auth bypass fix)
- **Makefile**: `make proto`, `make build-edge`
- **Planning doc**: `planning/04_EXTRACTION_PIPELINE/E12_EDGE_PUSH.md`

---

## [Phase 3, Sprint 26] — E13 VLM Screenshot Vision (2026-04-17)

**Branch:** `sprint/26-vlm-e13` | **Commits:** `8bb7f5a` → `1279226`

- **E13** `e13_vlm_vision`: VLM Screenshot Vision extraction strategy (priority 100 — last automated, before E12 manual review).
  - `VLMClient` interface + `OllamaClient` (HTTP POST `/api/generate`, base64 images) + `MockClient` for tests.
  - Prompts Phi-3.5-vision:latest (default) with structured JSON schema; parser handles bare JSON, ````json` fences, and leading prose.
  - Model ladder: `phi3.5-vision:latest` → `moondream2` → `florence-2-base`.
  - AI Act Art.50(2) disclosure: every extracted vehicle tagged `ai_generated=true` with model ID + UTC timestamp.
  - Page scrape → `<img>` harvest (≤10 images, min 4 KB) → VLM inference → vehicle parse cascade.
  - Opt-in via `VLM_ENABLED=true`; `VLM_MODEL`, `VLM_ENDPOINT`, `VLM_TIMEOUT`, `VLM_MAX_RETRIES`, `VLM_BACKEND`.
  - Metrics: `cardex_extraction_e13_requests_total`, `cardex_extraction_e13_latency_seconds`, `cardex_extraction_e13_fields_extracted`.
  - 10 unit tests (all pass, `-race`); 17/17 extraction packages green.
  - Inference benchmarks (CX42 CPU): Phi-3.5-vision Q4_K_M p50 ≈ 45 s/image, ~3 GB RAM.
  - Planning doc: `planning/04_EXTRACTION_PIPELINE/E13_VLM_VISION.md`.
- **Pipeline**: `PriorityE13=100` added to `strategy.go` cascade constants.
- **Config**: 7 new env vars for VLM control in `config.go`.
- **Metrics**: 3 new Prometheus metrics in `metrics.go` (E13-scoped).
- **Extraction strategies: 13/13 (Phase 3 +1 opt-in).**

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
