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

.PHONY: all build test lint dev smoke deploy secrets help cli e2e proto \
        build-discovery build-extraction build-quality build-edge \
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
# cli — build the terminal buyer CLI (cardex-cli)
# ---------------------------------------------------------------------------
cli:
	cd frontend/terminal && GOWORK=off go build -o ../../bin/cardex-cli ./cmd/cardex/
	@echo "Built: bin/cardex-cli"

# ---------------------------------------------------------------------------
# e2e — run end-to-end pipeline integration tests (no external network)
# ---------------------------------------------------------------------------
e2e:
	go test ./tests/e2e/... -tags=e2e -v -timeout=5m

# ---------------------------------------------------------------------------
# proto — compile protobuf definitions to Go (+ Rust via cargo build)
#
# Prerequisites (one-time install):
#   go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
#   go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
#   brew install protobuf   (or: apt install protobuf-compiler)
# ---------------------------------------------------------------------------
proto:
	@echo "Compiling edge_push.proto -> Go (extraction/api/edgepb)..."
	protoc \
		--proto_path=extraction/api/proto \
		--go_out=extraction/api/edgepb \
		--go_opt=paths=source_relative \
		--go-grpc_out=extraction/api/edgepb \
		--go-grpc_opt=paths=source_relative \
		extraction/api/proto/edge_push.proto
	@echo "Done. Run 'cargo build' in clients/edge-tauri/ for Rust client."

# ---------------------------------------------------------------------------
# build-edge — build edge-push-server + cardex-dealer CLI
# ---------------------------------------------------------------------------
build-edge:
	@echo "Building edge-push-server..."
	cd extraction && GOWORK=off go build -ldflags="-s -w" \
		-o ../bin/edge-push-server ./cmd/edge-push-server/
	@echo "  -> bin/edge-push-server"
	@echo "Building cardex-dealer..."
	cd extraction && GOWORK=off go build -ldflags="-s -w" \
		-o ../bin/cardex-dealer ./cmd/cardex-dealer/
	@echo "  -> bin/cardex-dealer"

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
	@echo "  make dev             Start local Docker Compose stack"
	@echo "  make down            Stop local stack"
	@echo "  make clean           Stop + remove volumes"
	@echo "  make logs SERVICE=   Follow logs for a service"
	@echo "  make smoke           Run smoke tests against local stack"
	@echo ""
	@echo "  make secrets         Generate age + TLS + SSH secrets"
	@echo "  make deploy          Deploy to VPS (HOST=cardex@ip)"
	@echo ""
