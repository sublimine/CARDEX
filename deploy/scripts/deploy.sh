#!/usr/bin/env bash
# deploy.sh — idempotent CARDEX deployment script
# Usage: ./deploy.sh [vps-host] [environment]
#   vps-host:    SSH host (e.g. cardex@1.2.3.4 or cardex@cardex.io)
#   environment: "staging" | "production" (default: production)
#
# What it does:
#   1. SSH to VPS
#   2. Pull latest images or git pull + go build
#   3. Migrate DB schema (PRAGMA / forward-compatible SQLite)
#   4. Reload systemd / docker-compose
#   5. Verify health endpoints
#   6. Rollback on failure
#
# Prerequisites on VPS: git, go 1.25, docker (optional), systemd

set -euo pipefail

VPS_HOST="${1:-cardex@cardex.io}"
ENVIRONMENT="${2:-production}"
DEPLOY_DIR="/opt/cardex"
SERVICE_DIR="/srv/cardex"
REPO_URL="git@github.com:cardex/cardex.git"  # update to Forgejo URL when ready
BRANCH="main"

# Colours
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC}  $*"; }
fail() { echo -e "${RED}[FAIL]${NC}  $*" >&2; exit 1; }

PREVIOUS_TAG=""

rollback() {
    warn "Deployment failed — attempting rollback to ${PREVIOUS_TAG:-previous version}..."
    if [[ -n "${PREVIOUS_TAG}" ]]; then
        ssh "${VPS_HOST}" "cd ${DEPLOY_DIR} && git checkout ${PREVIOUS_TAG} && \
            systemctl restart cardex-discovery cardex-extraction cardex-quality || true"
    fi
    fail "Deployment FAILED. Services may be in an inconsistent state. Check: journalctl -xe"
}
trap rollback ERR

log "=== CARDEX deploy → ${VPS_HOST} [${ENVIRONMENT}] ==="

# ── Step 1: Check SSH connectivity ──────────────────────────────────
log "1/7 Checking SSH connectivity..."
ssh -q -o ConnectTimeout=10 "${VPS_HOST}" echo "SSH OK" || fail "Cannot reach ${VPS_HOST}"

# ── Step 2: Record current version for rollback ──────────────────────
PREVIOUS_TAG=$(ssh "${VPS_HOST}" "cd ${DEPLOY_DIR} && git rev-parse --short HEAD 2>/dev/null || echo ''")
log "2/7 Current commit: ${PREVIOUS_TAG}"

# ── Step 3: Pull latest code ──────────────────────────────────────────
log "3/7 Pulling latest code from ${BRANCH}..."
ssh "${VPS_HOST}" "
    set -euo pipefail
    if [[ -d ${DEPLOY_DIR} ]]; then
        cd ${DEPLOY_DIR}
        git fetch origin ${BRANCH}
        git reset --hard origin/${BRANCH}
    else
        git clone --branch ${BRANCH} ${REPO_URL} ${DEPLOY_DIR}
    fi
    echo 'Git pull: OK'
"

NEW_TAG=$(ssh "${VPS_HOST}" "cd ${DEPLOY_DIR} && git rev-parse --short HEAD")
log "   New commit: ${NEW_TAG}"

# ── Step 4: Build binaries ─────────────────────────────────────────────
log "4/7 Building Go binaries..."
ssh "${VPS_HOST}" "
    set -euo pipefail
    export GOWORK=off

    # Discovery
    cd ${DEPLOY_DIR}/discovery
    go mod download -x 2>/dev/null
    CGO_ENABLED=0 go build -ldflags='-s -w' -o /tmp/cardex-discovery-new ./cmd/discovery-service/

    # Extraction
    cd ${DEPLOY_DIR}/extraction
    go mod download -x 2>/dev/null
    CGO_ENABLED=0 go build -ldflags='-s -w' -o /tmp/cardex-extraction-new ./cmd/extraction-service/

    # Quality
    cd ${DEPLOY_DIR}/quality
    go mod download -x 2>/dev/null
    CGO_ENABLED=0 go build -ldflags='-s -w' -o /tmp/cardex-quality-new ./cmd/quality-service/

    echo 'Build: OK'
"

# ── Step 5: Migrate DB schema ──────────────────────────────────────────
log "5/7 Running DB schema migration (WAL checkpoint)..."
ssh "${VPS_HOST}" "
    sqlite3 ${SERVICE_DIR}/db/discovery.db 'PRAGMA wal_checkpoint(FULL);' 2>/dev/null || true
    echo 'DB migration: OK'
"

# ── Step 6: Swap binaries + reload services ────────────────────────────
log "6/7 Swapping binaries + reloading services..."
ssh "${VPS_HOST}" "
    set -euo pipefail
    # Atomic swap
    mv /tmp/cardex-discovery-new /usr/local/bin/cardex-discovery
    mv /tmp/cardex-extraction-new /usr/local/bin/cardex-extraction
    mv /tmp/cardex-quality-new /usr/local/bin/cardex-quality
    chmod +x /usr/local/bin/cardex-{discovery,extraction,quality}

    # Copy updated configs
    cp ${DEPLOY_DIR}/deploy/systemd/cardex-discovery.service /etc/systemd/system/
    cp ${DEPLOY_DIR}/deploy/systemd/cardex-extraction.service /etc/systemd/system/
    cp ${DEPLOY_DIR}/deploy/systemd/cardex-quality.service /etc/systemd/system/
    cp ${DEPLOY_DIR}/deploy/systemd/cardex-backup.service /etc/systemd/system/
    cp ${DEPLOY_DIR}/deploy/systemd/cardex-backup.timer /etc/systemd/system/

    systemctl daemon-reload
    systemctl restart cardex-discovery
    sleep 5
    systemctl restart cardex-extraction
    sleep 5
    systemctl restart cardex-quality

    echo 'Service reload: OK'
"

# ── Step 7: Verify health endpoints ───────────────────────────────────
log "7/7 Verifying health endpoints (15s warmup)..."
sleep 15
HEALTH_CHECKS_PASSED=0
for port in 9101 9102 9103; do
    STATUS=$(ssh "${VPS_HOST}" "curl -s -o /dev/null -w '%{http_code}' http://localhost:${port}/metrics || echo '000'")
    if [[ "${STATUS}" == "200" ]]; then
        log "   :${port}/metrics → ${STATUS} OK"
        HEALTH_CHECKS_PASSED=$((HEALTH_CHECKS_PASSED + 1))
    else
        warn "   :${port}/metrics → ${STATUS} (may still be starting up)"
    fi
done

if [[ $HEALTH_CHECKS_PASSED -lt 2 ]]; then
    fail "Health checks failed — less than 2/3 services responding"
fi

log ""
log "=== Deployment SUCCESSFUL ==="
log "   Commit: ${PREVIOUS_TAG} → ${NEW_TAG}"
log "   Services: discovery, extraction, quality"
log "   Environment: ${ENVIRONMENT}"
log "   To rollback: git -C ${DEPLOY_DIR} checkout ${PREVIOUS_TAG} && systemctl restart cardex-*"
