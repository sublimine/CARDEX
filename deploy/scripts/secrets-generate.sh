#!/usr/bin/env bash
# secrets-generate.sh — generate CARDEX development secrets
# For PRODUCTION: Let's Encrypt handles TLS; use this for local dev + edge mTLS.
#
# Generated:
#   1. age keypair for backup encryption
#   2. Self-signed TLS CA + server cert (edge mTLS, local dev Caddy)
#   3. Random secrets (Grafana admin password, SearXNG secret key)
#
# Output: ./secrets/ directory (gitignored — NEVER commit actual keys)

set -euo pipefail

SECRETS_DIR="${1:-$(dirname "$0")/../secrets}"
mkdir -p "${SECRETS_DIR}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[secrets]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC}   $*"; }

log "=== CARDEX secrets generation ==="
log "Output directory: ${SECRETS_DIR}"

# ── 1. age keypair for backup encryption ────────────────────────────
if command -v age-keygen &>/dev/null; then
    if [[ ! -f "${SECRETS_DIR}/backup-private.key" ]]; then
        log "1/4 Generating age keypair for backup encryption..."
        age-keygen -o "${SECRETS_DIR}/backup-private.key" 2>&1 | \
            grep "public key" | awk '{print $NF}' > "${SECRETS_DIR}/backup-pubkey.txt"
        chmod 600 "${SECRETS_DIR}/backup-private.key"
        log "   Private key: ${SECRETS_DIR}/backup-private.key (KEEP OFFLINE)"
        log "   Public key:  $(cat "${SECRETS_DIR}/backup-pubkey.txt")"
        warn "   COPY backup-private.key to KeePassXC + offline USB NOW"
    else
        log "1/4 age keypair already exists — skipping."
    fi
else
    warn "1/4 age not installed — skipping keypair generation."
    warn "   Install: apt install age"
fi

# ── 2. Self-signed TLS CA for edge mTLS ─────────────────────────────
if command -v openssl &>/dev/null; then
    log "2/4 Generating edge mTLS CA + server certificate..."
    TLS_DIR="${SECRETS_DIR}/tls"
    mkdir -p "${TLS_DIR}"

    if [[ ! -f "${TLS_DIR}/ca.key" ]]; then
        # CA keypair
        openssl ecparam -name prime256v1 -genkey -noout -out "${TLS_DIR}/ca.key"
        openssl req -new -x509 -key "${TLS_DIR}/ca.key" \
            -out "${TLS_DIR}/ca.crt" \
            -days 3650 \
            -subj "/CN=CARDEX Edge CA/O=Cardex/C=EU"
        chmod 600 "${TLS_DIR}/ca.key"

        # Server keypair signed by CA
        openssl ecparam -name prime256v1 -genkey -noout -out "${TLS_DIR}/server.key"
        openssl req -new -key "${TLS_DIR}/server.key" \
            -out "${TLS_DIR}/server.csr" \
            -subj "/CN=cardex.io/O=Cardex/C=EU"
        openssl x509 -req \
            -in "${TLS_DIR}/server.csr" \
            -CA "${TLS_DIR}/ca.crt" -CAkey "${TLS_DIR}/ca.key" \
            -CAcreateserial \
            -out "${TLS_DIR}/server.crt" \
            -days 365 \
            -extfile <(printf "subjectAltName=DNS:cardex.io,DNS:localhost,IP:127.0.0.1")
        rm -f "${TLS_DIR}/server.csr"
        chmod 600 "${TLS_DIR}/server.key"
        log "   CA: ${TLS_DIR}/ca.crt"
        log "   Server: ${TLS_DIR}/server.crt + server.key"
    else
        log "2/4 TLS certs already exist — skipping."
    fi
else
    warn "2/4 openssl not installed — skipping TLS generation."
fi

# ── 3. Random application secrets ────────────────────────────────────
log "3/4 Generating random application secrets..."
ENV_FILE="${SECRETS_DIR}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
    cat > "${ENV_FILE}" <<EOF
# CARDEX application secrets — DO NOT COMMIT
# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)

GRAFANA_ADMIN_PASSWORD=$(openssl rand -base64 24 | tr -d '=+/' | head -c 32)
SEARXNG_SECRET_KEY=$(openssl rand -hex 32)
CARDEX_API_KEY_SALT=$(openssl rand -hex 32)
CARDEX_DOMAIN=localhost
EOF
    chmod 600 "${ENV_FILE}"
    log "   Generated .env with random secrets"
else
    log "3/4 .env already exists — skipping."
fi

# ── 4. SSH key for VPS access ────────────────────────────────────────
log "4/4 SSH key for VPS access..."
if [[ ! -f "${SECRETS_DIR}/id_ed25519" ]]; then
    ssh-keygen -t ed25519 -C "cardex-vps-$(date +%Y%m%d)" \
        -f "${SECRETS_DIR}/id_ed25519" -N ""
    log "   SSH keypair: ${SECRETS_DIR}/id_ed25519"
    log "   Public key:"
    cat "${SECRETS_DIR}/id_ed25519.pub"
    warn "   Add the public key to Hetzner Cloud → SSH Keys before provisioning VPS"
else
    log "4/4 SSH keypair already exists — skipping."
fi

log ""
log "=== Secrets generation COMPLETE ==="
log "Files created in: ${SECRETS_DIR}"
warn ""
warn "CRITICAL SECURITY REMINDERS:"
warn "  1. NEVER commit the secrets/ directory to git (it's in .gitignore)"
warn "  2. Copy backup-private.key to KeePassXC + offline USB backup"
warn "  3. Copy secrets/.env to /etc/cardex/.env on VPS"
warn "  4. For production TLS: Caddy uses Let's Encrypt automatically"
warn "     (self-signed certs above are for local dev + edge mTLS only)"
warn "  5. Rotate secrets every 90 days (see deploy/runbook.md §1)"
