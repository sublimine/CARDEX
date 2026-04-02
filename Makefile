# =============================================================================
# CARDEX Makefile — levanta todo con 'make dev'
# =============================================================================

.PHONY: all dev up down clean logs build test lint scrape gen-keys help \
        build-api build-scheduler build-gateway build-pipeline

# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------
COMPOSE        = docker compose
GO_SERVICES    = api scheduler gateway pipeline
SCRAPER_TARGET ?= autoscout24_de   # override: make scrape TARGET=mobile_de

# ---------------------------------------------------------------------------
# dev — primer arranque completo (genera claves JWT si no existen, luego up)
# ---------------------------------------------------------------------------
dev: gen-keys
	$(COMPOSE) up -d --build
	@echo ""
	@echo "  ✓ CARDEX dev environment running"
	@echo ""
	@echo "  Web app   →  http://localhost:3001"
	@echo "  API       →  http://localhost:8080"
	@echo "  Gateway   →  http://localhost:8090"
	@echo "  Grafana   →  http://localhost:3000   (admin / cardex_dev_only)"
	@echo "  Prometheus→  http://localhost:9090"
	@echo "  MeiliSearch→ http://localhost:7700"
	@echo "  ClickHouse→  http://localhost:8123"
	@echo "  PostgreSQL→  localhost:5432"
	@echo "  Redis     →  localhost:6379"
	@echo ""
	@echo "  Para scraper: make scrape TARGET=mobile_de"
	@echo "  Para logs:    make logs SERVICE=api"

# ---------------------------------------------------------------------------
# up / down / clean
# ---------------------------------------------------------------------------
up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

clean:
	$(COMPOSE) down -v --remove-orphans
	rm -rf secrets/

restart:
	$(COMPOSE) restart $(SERVICE)

# ---------------------------------------------------------------------------
# logs — make logs SERVICE=api
# ---------------------------------------------------------------------------
logs:
	$(COMPOSE) logs -f $(SERVICE)

logs-all:
	$(COMPOSE) logs -f

# ---------------------------------------------------------------------------
# gen-keys — genera par RSA-4096 para JWT si no existe ya
# ---------------------------------------------------------------------------
gen-keys:
	@if [ ! -f secrets/jwt_private.pem ]; then \
		echo "Generando claves JWT RS256..."; \
		mkdir -p secrets; \
		openssl genrsa -out secrets/jwt_private.pem 4096 2>/dev/null; \
		openssl rsa -in secrets/jwt_private.pem -pubout -out secrets/jwt_public.pem 2>/dev/null; \
		echo "  ✓ secrets/jwt_private.pem"; \
		echo "  ✓ secrets/jwt_public.pem"; \
		echo "  ⚠  Nunca subas estos archivos a git (están en .gitignore)"; \
	else \
		echo "  ✓ Claves JWT ya existen (secrets/)"; \
	fi

# ---------------------------------------------------------------------------
# scrape — lanza un scraper concreto
# Uso: make scrape TARGET=mobile_de
#      make scrape TARGET=coches_net
#      make scrape TARGET=discovery_es
# ---------------------------------------------------------------------------
scrape:
	$(COMPOSE) run --rm \
		-e SCRAPER_TARGET=$(SCRAPER_TARGET) \
		scraper

# scrape-all — lanza todos los scrapers en paralelo (uno por país + portal)
scrape-all:
	@echo "Lanzando todos los scrapers..."
	@for t in autoscout24_de mobile_de kleinanzeigen_de heycar_de pkw_de automobile_de \
	           autoscout24_es coches_net wallapop milanuncios autocasion motor_es coches_com flexicar \
	           autoscout24_fr leboncoin lacentrale paruvendu largus_fr caradisiac_fr \
	           autoscout24_nl marktplaats autotrack gaspedaal \
	           autoscout24_be 2dehands gocar \
	           autoscout24_ch tutti comparis; do \
		$(COMPOSE) run -d --rm -e SCRAPER_TARGET=$$t scraper & \
	done; wait
	@echo "  ✓ Todos los scrapers lanzados"

# ---------------------------------------------------------------------------
# Build (servicios Go)
# ---------------------------------------------------------------------------
build: $(addprefix build-,$(GO_SERVICES))

build-%:
	@echo "Building services/$*..."
	cd services/$* && go build -o ../../bin/$* ./cmd/$*/

# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------
test: $(addprefix test-,$(GO_SERVICES))

test-%:
	@echo "Testing services/$*..."
	cd services/$* && go test -race -count=1 -coverprofile=coverage.out ./...

# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------
lint: $(addprefix lint-,$(GO_SERVICES))

lint-%:
	cd services/$* && golangci-lint run --timeout=5m ./...

# ---------------------------------------------------------------------------
# Integration (requiere 'make dev' previamente)
# ---------------------------------------------------------------------------
integration:
	@echo "Verificando PostgreSQL..."
	@docker exec cardex-pg psql -U cardex -d cardex -c \
		"SELECT count(*) AS tablas FROM pg_tables WHERE schemaname='public';"
	@echo "Verificando ClickHouse..."
	@docker exec cardex-ch clickhouse-client \
		--query "SELECT count() AS tablas FROM system.tables WHERE database='cardex'"
	@echo "Verificando Redis..."
	@docker exec cardex-redis redis-cli PING
	@echo "Verificando API..."
	@curl -sf http://localhost:8080/healthz | python3 -m json.tool
	@echo "  ✓ Todo OK"

# ---------------------------------------------------------------------------
# Load test (datos sintéticos)
# ---------------------------------------------------------------------------
loadtest:
	@echo "Generando 10.000 vehículos sintéticos..."
	cd scripts && go run loadgen.go -count=10000

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
help:
	@echo ""
	@echo "CARDEX — Comandos disponibles:"
	@echo ""
	@echo "  make dev              Arranca todo (genera claves JWT + docker compose up)"
	@echo "  make up               Docker compose up -d"
	@echo "  make down             Docker compose down"
	@echo "  make clean            Destruye volúmenes y secretos"
	@echo "  make restart SERVICE= Reinicia un servicio concreto"
	@echo "  make logs SERVICE=    Logs de un servicio (ej: make logs SERVICE=api)"
	@echo "  make logs-all         Logs de todos los servicios"
	@echo ""
	@echo "  make scrape TARGET=   Lanza un scraper (ej: make scrape TARGET=mobile_de)"
	@echo "  make scrape-all       Lanza todos los scrapers en paralelo"
	@echo ""
	@echo "  make gen-keys         Genera claves RSA-4096 para JWT en secrets/"
	@echo "  make build            Compila todos los servicios Go"
	@echo "  make test             Tests unitarios"
	@echo "  make lint             Linter"
	@echo "  make integration      Tests de integración (requiere dev running)"
	@echo ""
