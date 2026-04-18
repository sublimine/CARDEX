# CARDEX

Pan-European vehicle intelligence platform. Discovers, extracts, and validates used-car listings from individual dealer websites across DE, ES, FR, NL, BE, and CH.

## What is implemented (Phases 2–5)

| Module | Phase | What it does | Status |
|--------|-------|-------------|--------|
| `discovery/` | P2 | Finds dealer URLs via 15 intelligence families (registries, OSM, OEM locators, social, etc.) | **Complete** |
| `extraction/` | P3 | Extracts vehicle listings using 13 strategies (JSON-LD, CMS REST, Playwright, PDF, RSS, VLM Vision, etc.) | **Complete** |
| `quality/` | P4 | Validates listings against 20 rules (VIN, NHTSA, price, photo hash, sold-check, composite score) | **Complete** |
| `deploy/` | P5 | Single-VPS deploy infra: systemd units, Caddy, Prometheus, Grafana, encrypted backups | **Complete** |
| `frontend/terminal/` | P5+ | Terminal buyer CLI (`cardex search/show/stats/review/search-natural/forecast/trust`) reading from the shared SQLite | **Complete** |
| `innovation/` | R&D | GNN dealer inference (:8501), local RAG search (:8502), Chronos-2 price forecasting (:8503), Routes disposition (:8504), Trust KYB (:8505) | **Experimental** |

## Quick start

**Prerequisites:** Go 1.25+

```bash
# Test each module independently
cd discovery  && GOWORK=off go test ./...
cd extraction && GOWORK=off go test ./...
cd quality    && GOWORK=off go test ./...

# Build binaries
cd discovery  && GOWORK=off go build -o discovery-service  ./cmd/discovery-service/
cd extraction && GOWORK=off go build -o extraction-service ./cmd/extraction-service/
cd quality    && GOWORK=off go build -o quality-service    ./cmd/quality-service/

# Local dev (Docker Compose — all three + observability):
docker compose -f deploy/docker/docker-compose.yml up -d
./deploy/scripts/test-deploy-local.sh
```

## Terminal CLI

```bash
# Build
cd frontend/terminal && GOWORK=off go build -o ../../bin/cardex-cli ./cmd/cardex/
# or: make cli

# Search listings (9 filters)
./bin/cardex-cli search --make BMW --model 320d --year-min 2018 --price-max 30000
./bin/cardex-cli search --country DE --score 80 --limit 20

# Show listing detail + validator breakdown
./bin/cardex-cli show <listing-id>

# Aggregate stats
./bin/cardex-cli stats

# AI Act Art.50(1) disclosure (review queue)
./bin/cardex-cli review list
./bin/cardex-cli review approve <id>

# Natural-language search via local RAG (requires innovation/rag_search running)
./bin/cardex-cli search-natural "BMW 3er diesel unter 30000 EUR"

# Price forecast via Chronos-2 (requires innovation/chronos_forecasting running)
./bin/cardex-cli forecast --make BMW --model "3er" --country DE --horizon 30 --spark

# CARDEX Routes — Fleet Disposition Intelligence (requires innovation/routes running)
./bin/cardex-cli routes spread --make BMW --model 320d --year 2021 --km 45000
./bin/cardex-cli routes optimize --make BMW --model 320d --year 2021 --km 45000 --country FR
./bin/cardex-cli routes batch --input fleet.csv --output plan.json
```

Set `CARDEX_DB_PATH` to point to the SQLite database (default: `./data/discovery.db`).

## Deploy to production (Hetzner CX42, ~€22/month)

```bash
./deploy/scripts/secrets-generate.sh        # generate age + SSH + TLS keys
./deploy/scripts/deploy.sh cardex@<VPS-IP>  # idempotent build + deploy
```

Full provisioning runbook: [`deploy/runbook.md`](deploy/runbook.md)

## Architecture

```
Internet ─→ Caddy (TLS 1.3, auto Let's Encrypt) ─→ discovery-service  :8080
                                                  ─→ extraction-service :8081
                                                  ─→ quality-service    :8082
                                                          │
                                              /srv/cardex/db/discovery.db (SQLite WAL)

Observability (loopback only):
  Prometheus  :9090 ← scrapes :9101, :9102, :9103
  Grafana     :3001 ← access via SSH tunnel
  Alertmanager:9093 ← receives alerts from Prometheus
```

## Repository layout

```
discovery/           Go module — 15-family dealer discovery engine
extraction/          Go module — 13-strategy vehicle listing extractor (E01–E12 + E13 VLM opt-in)
quality/             Go module — 20-validator listing quality pipeline
deploy/              VPS infrastructure (Docker + systemd + Caddy + Prometheus + scripts)
frontend/terminal/   Terminal buyer CLI (Go) — search, show, stats, review, forecast
innovation/          Research services — GNN :8501, RAG :8502, Chronos :8503, Routes :8504
clients/edge-tauri/  Rust+Tauri dealer desktop client (edge push gRPC)
planning/            All specs and architecture docs (primary reference)
internal/shared/     Shared Go utilities
SPEC.md              Original 924-page consolidated specification (vision doc)
CONTEXT_FOR_AI.md    AI onboarding: what is real, what is planned
```

## Build rules

1. **GOWORK=off** for all production builds — each module builds independently.
2. **CardexBot/1.0 UA only** — no spoofing, no stealth, no curl_cffi. CI enforces this.
3. **E13 VLM opt-in** — `VLM_ENABLED=true` required; requires ollama running with a vision model (default: `phi3.5-vision:latest`). Disabled by default due to CPU cost (~45 s/image on CX42).
4. **robots.txt compliance** — `extraction/internal/robots.Checker` is wired in HTML-crawling strategies (E01, E03, E04); non-web strategies skip it by design.
5. **SQLite + WAL** — no external database for the MVP. Backups are age-encrypted to Hetzner Storage Box.

## Documentation index

| Document | Purpose |
|----------|---------|
| [`CONTEXT_FOR_AI.md`](CONTEXT_FOR_AI.md) | What any AI/developer must read first |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Current system architecture |
| [`GETTING_STARTED.md`](GETTING_STARTED.md) | Developer onboarding |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Contribution guidelines |
| [`CHANGELOG.md`](CHANGELOG.md) | Phase-by-phase implementation history |
| [`SECURITY.md`](SECURITY.md) | Security policy and reporting |
| [`deploy/runbook.md`](deploy/runbook.md) | Step-by-step VPS provisioning |
| [`planning/`](planning/README.md) | Full specifications and architecture |
