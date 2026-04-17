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
        lint-discovery lint-extraction lint-quality \
        gnn-setup gnn-train gnn-serve gnn-test \
        layoutlm-setup layoutlm-fixtures layoutlm-test \
        forecast-pipeline forecast-serve forecast-test

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
# gnn-setup — install GNN Python dependencies (CPU-only)
# ---------------------------------------------------------------------------
gnn-setup:
	@echo "Installing GNN CPU-only dependencies..."
	pip install torch --index-url https://download.pytorch.org/whl/cpu
	pip install torch_geometric flask scikit-learn numpy
	@echo "Attempting optional torch_scatter/torch_sparse (may fail on some platforms):"
	pip install pyg_lib torch_scatter torch_sparse \
	    -f https://data.pyg.org/whl/torch-$$(python -c "import torch; v=torch.__version__; print(v.split('+')[0])")+cpu.html \
	    || echo "WARNING: torch_scatter/torch_sparse not installed — DGL fallback available"
	@echo "GNN setup complete."

# ---------------------------------------------------------------------------
# gnn-train — train the GraphSAGE dealer link prediction model
# ---------------------------------------------------------------------------
gnn-train:
	cd innovation/gnn_dealer_inference && \
	    python train.py --db ../../data/discovery.db --output model.pt \
	    --epochs 100 --lr 0.005

# ---------------------------------------------------------------------------
# gnn-serve — start the GNN inference server (port 8501)
# ---------------------------------------------------------------------------
gnn-serve:
	cd innovation/gnn_dealer_inference && \
	    GNN_DB_PATH=../../data/discovery.db \
	    GNN_MODEL_PATH=model.pt \
	    python serve.py

# ---------------------------------------------------------------------------
# gnn-test — run GNN pytest suite
# ---------------------------------------------------------------------------
gnn-test:
	cd innovation/gnn_dealer_inference && python -m pytest tests/ -v

# ---------------------------------------------------------------------------
# layoutlm-setup — install LayoutLMv3 dependencies (CPU-only)
# ---------------------------------------------------------------------------
layoutlm-setup:
	@echo "Installing LayoutLMv3 CPU-only dependencies..."
	pip install torch --index-url https://download.pytorch.org/whl/cpu
	pip install transformers Pillow pdf2image pytesseract
	@echo "NOTE: also install system packages:"
	@echo "  apt-get install poppler-utils tesseract-ocr tesseract-ocr-deu tesseract-ocr-fra tesseract-ocr-spa"

# ---------------------------------------------------------------------------
# layoutlm-fixtures — generate test PDF fixtures
# ---------------------------------------------------------------------------
layoutlm-fixtures:
	cd innovation/layoutlm_pdf && python fixtures/generate_fixtures.py

# ---------------------------------------------------------------------------
# layoutlm-test — run LayoutLMv3 pytest suite
# ---------------------------------------------------------------------------
layoutlm-test:
	cd innovation/layoutlm_pdf && python -m pytest tests/ -v

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
	@echo "  make gnn-setup       Install GNN CPU-only dependencies (PyG/DGL)"
	@echo "  make gnn-train       Train GraphSAGE dealer link model"
	@echo "  make gnn-serve       Start GNN inference server (port 8501)"
	@echo "  make gnn-test        Run GNN pytest suite"
	@echo ""
	@echo "  make layoutlm-setup    Install LayoutLMv3 CPU-only dependencies"
	@echo "  make layoutlm-fixtures Generate test PDF fixtures (DE/FR/ES)"
	@echo "  make layoutlm-test     Run LayoutLMv3 pytest suite"
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
