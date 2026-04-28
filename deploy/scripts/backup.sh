#!/usr/bin/env bash
# backup.sh — daily CARDEX backup to Hetzner Storage Box
# Triggered by: systemd cardex-backup.timer (03:00 UTC)
# Manual run:   sudo -u cardex /opt/cardex/scripts/backup.sh
#
# Procedure:
#   1. WAL checkpoint on SQLite DBs (no service stop needed)
#   2. Snapshot files to local backup dir
#   3. Encrypt with age (public key on VPS, private key offline)
#   4. rsync differential to Hetzner Storage Box
#   5. Prune local + remote backups older than 30 days
#   6. Report backup size + duration to stdout (captured by journald)

set -euo pipefail

# ── Config (overridable via environment) ─────────────────────────────
DB_DIR="${CARDEX_DB_DIR:-/srv/cardex/db}"
BACKUP_ROOT="${CARDEX_BACKUP_ROOT:-/srv/cardex/backups}"
PUBKEY_FILE="${CARDEX_BACKUP_PUBKEY:-/etc/cardex/backup-pubkey.txt}"
RETENTION_DAYS="${CARDEX_BACKUP_RETENTION:-30}"

# Storage Box credentials (loaded via systemd-creds or env)
STORAGE_HOST="${CARDEX_STORAGE_HOST:-$(cat /run/credentials/cardex-backup.service/storage-box-host 2>/dev/null || echo '')}"
STORAGE_USER="${CARDEX_STORAGE_USER:-$(cat /run/credentials/cardex-backup.service/storage-box-user 2>/dev/null || echo '')}"
REMOTE_DIR="/cardex-backups"

# ── Colours / logging ────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo "[$(date -u +%H:%M:%S)] $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*" >&2; exit 1; }

START_TS=$(date -u +%s)
DATE=$(date -u +%Y%m%d_%H%M%S)
BACKUP_NAME="cardex-backup-${DATE}"
LOCAL_PATH="${BACKUP_ROOT}/${BACKUP_NAME}.tar.gz.age"

log "=== CARDEX backup started: ${DATE} ==="

# ── Validate pre-conditions ──────────────────────────────────────────
[[ -d "${DB_DIR}" ]]       || fail "DB_DIR not found: ${DB_DIR}"
[[ -f "${PUBKEY_FILE}" ]]  || fail "age public key not found: ${PUBKEY_FILE}"
[[ -n "${STORAGE_HOST}" ]] || fail "STORAGE_HOST not set — check systemd-creds or environment"
[[ -n "${STORAGE_USER}" ]] || fail "STORAGE_USER not set"

mkdir -p "${BACKUP_ROOT}"

# ── Step 1: WAL checkpoint ────────────────────────────────────────────
log "1/5 WAL checkpoint..."
for db in "${DB_DIR}"/*.db; do
    if [[ -f "${db}" ]]; then
        sqlite3 "${db}" "PRAGMA wal_checkpoint(FULL);" && log "   Checkpoint: $(basename "${db}") OK"
    fi
done

# ── Step 2: Create archive ────────────────────────────────────────────
log "2/5 Creating archive from ${DB_DIR}..."
TMP_ARCHIVE="/tmp/${BACKUP_NAME}.tar.gz"
tar czf "${TMP_ARCHIVE}" -C "$(dirname "${DB_DIR}")" "$(basename "${DB_DIR}")"
UNENCRYPTED_SIZE=$(du -sh "${TMP_ARCHIVE}" | cut -f1)
log "   Archive size: ${UNENCRYPTED_SIZE}"

# ── Step 3: Encrypt with age ──────────────────────────────────────────
log "3/5 Encrypting with age..."
age -r "$(cat "${PUBKEY_FILE}")" -o "${LOCAL_PATH}" "${TMP_ARCHIVE}"
rm -f "${TMP_ARCHIVE}"
ENCRYPTED_SIZE=$(du -sh "${LOCAL_PATH}" | cut -f1)
log "   Encrypted: ${ENCRYPTED_SIZE} → ${LOCAL_PATH}"

# ── Step 4: rsync to Hetzner Storage Box ──────────────────────────────
log "4/5 Syncing to ${STORAGE_USER}@${STORAGE_HOST}:${REMOTE_DIR}/"
rsync -az --progress \
    -e "ssh -o StrictHostKeyChecking=yes -o BatchMode=yes" \
    "${LOCAL_PATH}" \
    "${STORAGE_USER}@${STORAGE_HOST}:${REMOTE_DIR}/"
log "   rsync: OK"

# ── Step 5: Prune old backups ──────────────────────────────────────────
log "5/5 Pruning backups older than ${RETENTION_DAYS} days..."

# Prune local
find "${BACKUP_ROOT}" -name "cardex-backup-*.tar.gz.age" -mtime "+${RETENTION_DAYS}" -delete
LOCAL_COUNT=$(ls "${BACKUP_ROOT}"/cardex-backup-*.tar.gz.age 2>/dev/null | wc -l)
log "   Local backups retained: ${LOCAL_COUNT}"

# Prune remote (SSH)
ssh -o BatchMode=yes "${STORAGE_USER}@${STORAGE_HOST}" \
    "find ${REMOTE_DIR}/ -name 'cardex-backup-*.tar.gz.age' -mtime +${RETENTION_DAYS} -delete; \
     echo 'Remote prune: OK'"

# ── Summary ───────────────────────────────────────────────────────────
END_TS=$(date -u +%s)
DURATION=$((END_TS - START_TS))
log "=== Backup COMPLETE in ${DURATION}s ==="
log "   File: ${LOCAL_PATH}"
log "   Encrypted size: ${ENCRYPTED_SIZE}"
log "   Remote: ${STORAGE_USER}@${STORAGE_HOST}:${REMOTE_DIR}/${BACKUP_NAME}.tar.gz.age"
