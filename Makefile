# =============================================================================
# CARDEX Makefile — Phase 2-5 MVP (discovery / extraction / quality)
# =============================================================================
#
# Core commands:
#   make build        Build all three Go services
#   make test         Run all tests (GOWORK=off per module)
#   make dev          Start full local stack via Docker Compose
#   make smoke        Run local smoke tests
#   make deploy       Deploy to VPS (requires HOST env var)
#
# =============================================================================

.PHONY: all build test lint dev smoke deploy secrets help \
        build-discovery build-extraction build-quality \
        test-discovery test-extraction test-quality \
        lint-discovery lint-extraction lint-quality

# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------
COMPOSE     = docker compose
COMPOSE_DEV = $(COMPOSE) -f deploy/docker/docker-compose.yml
HOST        ?= cardex@cardex.io

# ---------------------------------------------------------------------------
# build — compile all three services (GOWORK=off per module)
# ---------------------------------------------------------------------------
build: build-discovery build-extraction build-quality

build-discovery:
	@echo "Building discovery..."
	cd discovery && GOWORK=off go build -ldflags="-s -w" -o ../bin/discovery-service ./cmd/discovery-service/
	@echo "  -> bin/discovery-service"

build-extraction:
	@echo "Building extraction..."
	cd extraction && GOWORK=off go build -ldflags="-s -w" -o ../bin/extraction-service ./cmd/extraction-service/
	@echo "  -> bin/extraction-service"

build-quality:
	@echo "Building quality..."
	cd quality && GOWORK=off go build -ldflags="-s -w" -o ../bin/quality-service ./cmd/quality-service/
	@echo "  -> bin/quality-service"

# ---------------------------------------------------------------------------
# test — run tests for all three modules (GOWORK=off per module)
# ---------------------------------------------------------------------------
test: test-discovery test-extraction test-quality

test-discovery:
	@echo "Testing discovery..."
	cd discovery && GOWORK=off go test -race -count=1 ./...

test-extraction:
	@echo "Testing extraction..."
	cd extraction && GOWORK=off go test -race -count=1 ./...

test-quality:
	@echo "Testing quality..."
	cd quality && GOWORK=off go test -race -count=1 ./...

# ---------------------------------------------------------------------------
# lint — run golangci-lint on all three modules
# ---------------------------------------------------------------------------
lint: lint-discovery lint-extraction lint-quality

lint-discovery:
	cd discovery && GOWORK=off golangci-lint run --timeout=5m ./...

lint-extraction:
	cd extraction && GOWORK=off golangci-lint run --timeout=5m ./...

lint-quality:
	cd quality && GOWORK=off golangci-lint run --timeout=5m ./...

# ---------------------------------------------------------------------------
# dev — local Docker Compose stack (all 3 services + observability)
# ---------------------------------------------------------------------------
dev:
	$(COMPOSE_DEV) up -d --build
	@echo ""
	@echo "  Discovery  ->  http://localhost:8080"
	@echo "  Extraction ->  http://localhost:8081"
	@echo "  Quality    ->  http://localhost:8082"
	@echo "  Prometheus ->  http://localhost:9090"
	@echo "  Grafana    ->  http://localhost:3001"
	@echo ""
	@echo "  Run: make smoke  (smoke tests)"

down:
	$(COMPOSE_DEV) down

clean:
	$(COMPOSE_DEV) down -v --remove-orphans

logs:
	$(COMPOSE_DEV) logs -f $(SERVICE)

# ---------------------------------------------------------------------------
# smoke — run local smoke tests
# ---------------------------------------------------------------------------
smoke:
	./deploy/scripts/test-deploy-local.sh

# ---------------------------------------------------------------------------
# secrets — generate age + TLS + SSH secrets for local dev
# ---------------------------------------------------------------------------
secrets:
	./deploy/scripts/secrets-generate.sh

# ---------------------------------------------------------------------------
# deploy — idempotent deploy to VPS
# Usage: make deploy HOST=cardex@1.2.3.4
# ---------------------------------------------------------------------------
deploy:
	./deploy/scripts/deploy.sh $(HOST) production

# ---------------------------------------------------------------------------
# backup — trigger manual backup on VPS
# ---------------------------------------------------------------------------
backup:
	./deploy/scripts/test-backup-restore.sh

# ---------------------------------------------------------------------------
# forecast-pipeline — run the Chronos-2 data pipeline (SQLite → time-series CSVs)
# ---------------------------------------------------------------------------
forecast-pipeline:
	cd innovation/chronos_forecasting && \
	    python data_pipeline.py \
	    --db ../../data/discovery.db \
	    --out timeseries

# ---------------------------------------------------------------------------
# forecast-serve — start the Chronos-2 forecast API server (port 8503)
# ---------------------------------------------------------------------------
forecast-serve:
	cd innovation/chronos_forecasting && \
	    TIMESERIES_DIR=timeseries \
	    uvicorn serve:app --host 0.0.0.0 --port 8503 --reload

# ---------------------------------------------------------------------------
# forecast-test — run Chronos-2 pytest suite
# ---------------------------------------------------------------------------
forecast-test:
	cd innovation/chronos_forecasting && python -m pytest tests/ -v

# ---------------------------------------------------------------------------
# help
# ---------------------------------------------------------------------------
help:
	@echo ""
	@echo "CARDEX — Phase 2-5 MVP"
	@echo ""
	@echo "  make build           Build discovery + extraction + quality binaries"
	@echo "  make test            Run all tests (GOWORK=off per module)"
	@echo "  make lint            Run golangci-lint on all three modules"
	@echo ""
	@echo "  make forecast-pipeline Run Chronos-2 data pipeline (SQLite → CSVs)"
	@echo "  make forecast-serve    Start Chronos-2 forecast API (port 8503)"
	@echo "  make forecast-test     Run Chronos-2 pytest suite"
	@echo ""
	@echo "  make dev             Start local Docker Compose stack"
	@echo "  make down            Stop local stack"
	@echo "  make clean           Stop + remove volumes"
	@echo "  make logs SERVICE=   Follow logs for a service"
	@echo "  make smoke           Run smoke tests against local stack"
	@echo ""
	@echo "  make secrets         Generate age + TLS + SSH secrets"
	@echo "  make deploy          Deploy to VPS (HOST=cardex@ip)"
	@echo ""
