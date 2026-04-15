# CARDEX

Pan-European vehicle intelligence platform. Discovers, extracts, and validates used-car listings from individual dealer websites across DE, ES, FR, NL, BE, and CH.

## What is implemented (Phases 2–5)

| Module | Phase | What it does | Status |
|--------|-------|-------------|--------|
| `discovery/` | P2 | Finds dealer URLs via 15 intelligence families (registries, OSM, OEM locators, social, etc.) | **Complete** |
| `extraction/` | P3 | Extracts vehicle listings using 12 strategies (JSON-LD, CMS REST, Playwright, PDF, RSS, etc.) | **Complete** |
| `quality/` | P4 | Validates listings against 20 rules (VIN, NHTSA, price, photo hash, sold-check, composite score) | **Complete** |
| `deploy/` | P5 | Single-VPS deploy infra: systemd units, Caddy, Prometheus, Grafana, encrypted backups | **Complete** |

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
extraction/          Go module — 12-strategy vehicle listing extractor
quality/             Go module — 20-validator listing quality pipeline
deploy/              VPS infrastructure (Docker + systemd + Caddy + Prometheus + scripts)
planning/            All specs and architecture docs (primary reference)
internal/shared/     Shared Go utilities
SPEC.md              Original 924-page consolidated specification (vision doc)
CONTEXT_FOR_AI.md    AI onboarding: what is real, what is planned
```

## Build rules

1. **GOWORK=off** for all production builds — each module builds independently.
2. **CardexBot/1.0 UA only** — no spoofing, no stealth, no curl_cffi. CI enforces this.
3. **robots.txt compliance** — `RobotsChecker` is wired in all HTTP crawl paths.
4. **SQLite + WAL** — no external database for the MVP. Backups are age-encrypted to Hetzner Storage Box.

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
