#!/usr/bin/env bash
# restore.sh — CARDEX backup restore procedure
# Usage: ./restore.sh [backup-file.tar.gz.age]
#
# If no backup file is provided, lists available backups from Storage Box
# and prompts for selection.
#
# Restore procedure:
#   1. Stop services (to prevent DB write conflicts)
#   2. Decrypt backup with age private key
#   3. Extract to DB directory
#   4. Verify SQLite integrity
#   5. Restart services

set -euo pipefail

TARGET_FILE="${1:-}"
DB_DIR="${CARDEX_DB_DIR:-/srv/cardex/db}"
BACKUP_ROOT="${CARDEX_BACKUP_ROOT:-/srv/cardex/backups}"
AGE_KEY_FILE="${CARDEX_AGE_PRIVATE_KEY:-${HOME}/.age/cardex-backup.key}"
STORAGE_HOST="${CARDEX_STORAGE_HOST:-}"
STORAGE_USER="${CARDEX_STORAGE_USER:-}"
REMOTE_DIR="/cardex-backups"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()    { echo -e "${GREEN}[restore]${NC} $*"; }
warn()   { echo -e "${YELLOW}[warn]${NC}   $*"; }
fail()   { echo -e "${RED}[FAIL]${NC}   $*" >&2; exit 1; }
confirm() {
    read -r -p "$1 [yes/NO] " REPLY
    [[ "${REPLY}" == "yes" ]] || fail "Aborted by user."
}

log "=== CARDEX Restore ==="
[[ -f "${AGE_KEY_FILE}" ]] || fail "age private key not found: ${AGE_KEY_FILE}
Generate/restore it from KeePassXC backup before proceeding."

# ── If no file specified: list available backups ─────────────────────
if [[ -z "${TARGET_FILE}" ]]; then
    log "Available local backups:"
    ls -lh "${BACKUP_ROOT}"/cardex-backup-*.tar.gz.age 2>/dev/null || warn "No local backups found."

    if [[ -n "${STORAGE_HOST}" && -n "${STORAGE_USER}" ]]; then
        log "Available remote backups (Storage Box):"
        ssh -o BatchMode=yes "${STORAGE_USER}@${STORAGE_HOST}" \
            "ls -lh ${REMOTE_DIR}/cardex-backup-*.tar.gz.age 2>/dev/null || echo '(none)'"

        read -r -p "Enter filename to restore (from remote, just the name): " REMOTE_FILE
        if [[ -n "${REMOTE_FILE}" ]]; then
            log "Downloading ${REMOTE_FILE} from Storage Box..."
            rsync -az -e "ssh -o BatchMode=yes" \
                "${STORAGE_USER}@${STORAGE_HOST}:${REMOTE_DIR}/${REMOTE_FILE}" \
                "/tmp/${REMOTE_FILE}"
            TARGET_FILE="/tmp/${REMOTE_FILE}"
        fi
    fi
fi

[[ -n "${TARGET_FILE}" && -f "${TARGET_FILE}" ]] || fail "No backup file specified or found."
log "Restoring from: ${TARGET_FILE}"

# ── Safety check ──────────────────────────────────────────────────────
warn "This will OVERWRITE all databases in ${DB_DIR}!"
warn "Current DB contents will be LOST unless already backed up."
confirm "Are you absolutely sure you want to restore?"

# ── Step 1: Stop services ─────────────────────────────────────────────
log "1/5 Stopping CARDEX services..."
systemctl stop cardex-quality   || true
systemctl stop cardex-extraction || true
systemctl stop cardex-discovery  || true
log "   Services stopped."

# ── Step 2: Backup current DB (safety net) ────────────────────────────
log "2/5 Creating safety snapshot of current DB..."
SAFETY_DIR="/tmp/cardex-pre-restore-$(date +%Y%m%d_%H%M%S)"
mkdir -p "${SAFETY_DIR}"
cp -r "${DB_DIR}" "${SAFETY_DIR}/" 2>/dev/null || warn "No existing DB to snapshot."
log "   Safety snapshot: ${SAFETY_DIR}"

# ── Step 3: Decrypt ───────────────────────────────────────────────────
log "3/5 Decrypting backup..."
TMP_ARCHIVE="/tmp/cardex-restore-$$.tar.gz"
age --decrypt -i "${AGE_KEY_FILE}" -o "${TMP_ARCHIVE}" "${TARGET_FILE}"
log "   Decrypted: OK"

# ── Step 4: Extract ───────────────────────────────────────────────────
log "4/5 Extracting to ${DB_DIR}..."
rm -rf "${DB_DIR:?}"/*
tar xzf "${TMP_ARCHIVE}" --strip-components=1 -C "${DB_DIR}"
rm -f "${TMP_ARCHIVE}"
log "   Extracted: OK"

# ── Step 5: Integrity check ───────────────────────────────────────────
log "5/5 Verifying SQLite integrity..."
ALL_OK=true
for db in "${DB_DIR}"/*.db; do
    if [[ -f "${db}" ]]; then
        RESULT=$(sqlite3 "${db}" "PRAGMA integrity_check;" 2>&1)
        if [[ "${RESULT}" == "ok" ]]; then
            log "   $(basename "${db}"): integrity OK"
        else
            warn "   $(basename "${db}"): INTEGRITY CHECK FAILED: ${RESULT}"
            ALL_OK=false
        fi
    fi
done

if ! $ALL_OK; then
    warn "Integrity check failed! Restoring safety snapshot..."
    rm -rf "${DB_DIR:?}"/*
    cp -r "${SAFETY_DIR}/db/"* "${DB_DIR}/"
    fail "Restore aborted — safety snapshot restored. Original data preserved."
fi

# ── Restart services ──────────────────────────────────────────────────
log "Restarting CARDEX services..."
systemctl start cardex-discovery
sleep 10
systemctl start cardex-extraction
sleep 5
systemctl start cardex-quality
log ""
log "=== Restore COMPLETE ==="
log "   Source: ${TARGET_FILE}"
log "   Safety snapshot: ${SAFETY_DIR} (delete manually when confident)"
log "   Verify: curl http://localhost:9101/metrics"
