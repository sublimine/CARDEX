#!/usr/bin/env bash
# test-deploy-local.sh — smoke-test the full stack via Docker Compose
# Prerequisites: Docker Desktop running, ~4 GB RAM available
#
# Usage: ./deploy/scripts/test-deploy-local.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_DIR="${SCRIPT_DIR}/../docker"
COMPOSE_FILE="${DOCKER_DIR}/docker-compose.yml"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[test]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*" >&2; exit 1; }

PASS=0; FAIL=0
check() {
    local desc="$1"; shift
    if "$@" &>/dev/null; then
        log "  PASS: ${desc}"
        PASS=$((PASS + 1))
    else
        warn "  FAIL: ${desc}"
        FAIL=$((FAIL + 1))
    fi
}

cleanup() {
    log "Cleaning up..."
    docker compose -f "${COMPOSE_FILE}" down --volumes 2>/dev/null || true
}
trap cleanup EXIT

log "=== CARDEX local stack smoke test ==="

# ── Build + start ──────────────────────────────────────────────────────
log "Building images..."
docker compose -f "${COMPOSE_FILE}" build --quiet 2>&1 | tail -5

log "Starting stack..."
docker compose -f "${COMPOSE_FILE}" up -d 2>&1

log "Waiting 30s for services to start..."
sleep 30

# ── Health checks ──────────────────────────────────────────────────────
log "Running health checks..."

# Prometheus
check "Prometheus responds on :9090" \
    curl -sf --max-time 5 http://localhost:9090/-/healthy

# Grafana
check "Grafana responds on :3001" \
    curl -sf --max-time 5 http://localhost:3001/api/health

# Check containers are running
check "cardex-discovery container running" \
    docker compose -f "${COMPOSE_FILE}" ps discovery | grep -q "Up"

check "cardex-extraction container running" \
    docker compose -f "${COMPOSE_FILE}" ps extraction | grep -q "Up"

check "cardex-quality container running" \
    docker compose -f "${COMPOSE_FILE}" ps quality | grep -q "Up"

# Discovery metrics endpoint
check "Discovery metrics endpoint (:9101)" \
    curl -sf --max-time 5 http://localhost:9101/metrics

# Extraction metrics endpoint
check "Extraction metrics endpoint (:9102)" \
    curl -sf --max-time 5 http://localhost:9102/metrics

# Quality metrics endpoint
check "Quality metrics endpoint (:9103)" \
    curl -sf --max-time 5 http://localhost:9103/metrics

# ── Prometheus scrape verification ────────────────────────────────────
log "Verifying Prometheus scrape targets..."
sleep 15  # give Prometheus time to scrape
TARGETS_UP=$(curl -sf http://localhost:9090/api/v1/targets 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(1 for t in d['data']['activeTargets'] if t['health']=='up'))" 2>/dev/null || echo "0")
check "Prometheus scraped ≥3 targets" [[ "${TARGETS_UP}" -ge 3 ]]

# ── Summary ───────────────────────────────────────────────────────────
log ""
log "=== Test results: ${PASS} passed, ${FAIL} failed ==="
if [[ $FAIL -gt 0 ]]; then
    warn "Some checks failed. Check logs with:"
    warn "  docker compose -f ${COMPOSE_FILE} logs --tail=50"
    exit 1
fi
log "All checks passed!"
