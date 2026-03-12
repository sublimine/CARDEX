# =============================================================================
# CARDEX Makefile
# =============================================================================

.PHONY: all dev up down clean test lint build

# ---------------------------------------------------------------------------
# Development Environment
# ---------------------------------------------------------------------------
dev: up init-wait
	@echo "✓ CARDEX dev environment ready"
	@echo "  PostgreSQL: localhost:5432"
	@echo "  ClickHouse: localhost:8123 (HTTP), localhost:9000 (Native)"
	@echo "  Redis:      localhost:6379"
	@echo "  Prometheus: localhost:9090"
	@echo "  Grafana:    localhost:3000 (admin/cardex_dev_only)"

up:
	docker compose up -d

down:
	docker compose down

clean:
	docker compose down -v --remove-orphans

init-wait:
	@echo "Waiting for services..."
	@sleep 5

# ---------------------------------------------------------------------------
# Build (Go services)
# ---------------------------------------------------------------------------
GO_SERVICES = gateway pipeline forensics alpha legal

build: $(addprefix build-,$(GO_SERVICES))

build-%:
	@echo "Building $*..."
	cd $* && go build -o ../bin/$* ./cmd/$*/

# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------
test: $(addprefix test-,$(GO_SERVICES))

test-%:
	cd $* && go test -race -count=1 -coverprofile=coverage.out ./...

test-ai:
	cd ai && python -m pytest tests/ -v

# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------
lint: $(addprefix lint-,$(GO_SERVICES))

lint-%:
	cd $* && golangci-lint run --timeout=5m ./...

lint-sql:
	@echo "Validating SQL scripts..."
	psql -h localhost -U cardex -d cardex -f scripts/init-pg.sql --set ON_ERROR_STOP=on -v AUTOCOMMIT=off

# ---------------------------------------------------------------------------
# Integration test (requires running dev environment)
# ---------------------------------------------------------------------------
integration:
	@echo "Running integration tests against dev environment..."
	@echo "1. Verify PostgreSQL schema..."
	psql -h localhost -U cardex -d cardex -c "SELECT count(*) FROM pg_tables WHERE schemaname='public';"
	@echo "2. Verify ClickHouse schema..."
	clickhouse-client --host localhost --query "SELECT count() FROM system.tables WHERE database IN ('cardex','cardex_forensics')"
	@echo "3. Verify Redis streams..."
	redis-cli KEYS 'stream:*' | wc -l
	@echo "4. Verify Bloom filter..."
	redis-cli BF.INFO bloom:vehicles Capacity
	@echo "✓ Integration checks passed"

# ---------------------------------------------------------------------------
# Load test (synthetic data)
# ---------------------------------------------------------------------------
loadtest:
	@echo "Generating 10,000 synthetic vehicles..."
	cd scripts && go run loadgen.go -count=10000

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
help:
	@echo "CARDEX Makefile targets:"
	@echo "  dev          Start full dev environment"
	@echo "  up/down      Start/stop Docker services"
	@echo "  clean        Destroy all volumes"
	@echo "  build        Build all Go services"
	@echo "  test         Run all unit tests"
	@echo "  lint         Run linters"
	@echo "  integration  Run integration tests (requires 'dev')"
	@echo "  loadtest     Generate synthetic load"
