# Getting Started

## Prerequisites

- **Go 1.25+** (`go version` must show ≥1.25)
- **Git**
- **Docker + Docker Compose** (optional, for full local stack)

## 1. Clone

```bash
git clone https://github.com/cardex/cardex.git
cd cardex
```

## 2. Build and test the three core modules

Each module builds and tests independently with `GOWORK=off`:

```bash
# Discovery (15 families)
cd discovery && GOWORK=off go build ./cmd/discovery-service/ && GOWORK=off go test ./...

# Extraction (12 strategies)
cd extraction && GOWORK=off go build ./cmd/extraction-service/ && GOWORK=off go test ./...

# Quality (20 validators)
cd quality && GOWORK=off go build ./cmd/quality-service/ && GOWORK=off go test ./...
```

All three should build and test cleanly with no errors.

## 3. Configuration (env vars)

Each service reads configuration from environment variables. Sensible defaults exist for local dev. Key vars:

```bash
# Discovery
DISCOVERY_DB_PATH=/srv/cardex/db/discovery.db
DISCOVERY_HTTP_PORT=8080
DISCOVERY_METRICS_PORT=9101
DISCOVERY_SKIP_FAMILIA_K=true   # disable SearXNG family (requires running SearXNG instance)

# Extraction
EXTRACTION_DB_PATH=/srv/cardex/db/discovery.db
EXTRACTION_HTTP_PORT=8081
EXTRACTION_METRICS_PORT=9102
EXTRACTION_SKIP_E07=true        # disable Playwright (requires Playwright/Chromium)

# Quality
QUALITY_DB_PATH=/srv/cardex/db/discovery.db
QUALITY_HTTP_PORT=8082
QUALITY_METRICS_PORT=9103
QUALITY_SKIP_V02=true           # disable NHTSA lookup (external API)
```

Full list: see `discovery/internal/config/config.go`, `extraction/internal/config/config.go`, `quality/internal/config/config.go`.

## 4. Local full-stack (Docker Compose)

```bash
# Start all services + observability
docker compose -f deploy/docker/docker-compose.yml up -d

# Run smoke tests
./deploy/scripts/test-deploy-local.sh

# Check health
curl http://localhost:8080/health   # discovery
curl http://localhost:8081/health   # extraction
curl http://localhost:8082/health   # quality

# Access Grafana (user: admin, password from secrets/.env)
open http://localhost:3001
```

## 5. Run a discovery job

```bash
# Start discovery service
cd discovery
DISCOVERY_DB_PATH=./dev.db DISCOVERY_HTTP_PORT=8080 \
    GOWORK=off ./discovery-service

# Queue a discovery task (example: discover dealers in France via INSEE)
curl -X POST http://localhost:8080/api/discover \
    -H "Content-Type: application/json" \
    -d '{"country": "FR", "families": ["A"]}'
```

## 6. Key files to read first

When starting work on a module, read these in order:

1. `CONTEXT_FOR_AI.md` — ground truth about what is implemented
2. `{module}/cmd/{module}-service/main.go` — service entrypoint, wiring, config
3. `{module}/internal/config/config.go` — all env var configuration
4. `{module}/internal/pipeline/pipeline.go` — core data structures and interfaces
5. The specific family/strategy/validator you are working on

## 7. Known limitations

- **E07 (Playwright)** requires Playwright and Chromium installed. Skip with `EXTRACTION_SKIP_E07=true` for dev.
- **V02 (NHTSA)** makes external HTTP calls to api.nhtsa.dot.gov. Skip with `QUALITY_SKIP_V02=true` in offline environments.
- **V03 (DAT)** requires DAT credentials. Skip with `QUALITY_SKIP_V03=true`.
- **Family K (SearXNG)** requires a running SearXNG instance. Skip with `DISCOVERY_SKIP_FAMILIA_K=true`.
