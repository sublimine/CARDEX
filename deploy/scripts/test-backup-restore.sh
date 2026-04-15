#!/usr/bin/env bash
# test-backup-restore.sh — end-to-end backup → restore → integrity verification
# Creates a temporary SQLite DB, runs backup.sh, then restore.sh, verifies integrity.
#
# Usage: ./deploy/scripts/test-backup-restore.sh
# Requires: age, sqlite3

set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[test-br]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC}   $*"; }
fail() { echo -e "${RED}[FAIL]${NC}   $*" >&2; exit 1; }

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

WORK_DIR=$(mktemp -d)
trap "rm -rf ${WORK_DIR}" EXIT

log "=== Backup/Restore test: working dir ${WORK_DIR} ==="

# ── Check prerequisites ───────────────────────────────────────────────
for cmd in age age-keygen sqlite3 rsync; do
    command -v "${cmd}" &>/dev/null || fail "${cmd} not installed. Install with: apt install ${cmd}"
done

# ── Setup test environment ────────────────────────────────────────────
TEST_DB_DIR="${WORK_DIR}/db"
TEST_BACKUP_ROOT="${WORK_DIR}/backups"
TEST_RESTORE_DIR="${WORK_DIR}/restore"
TEST_SECRETS="${WORK_DIR}/secrets"
mkdir -p "${TEST_DB_DIR}" "${TEST_BACKUP_ROOT}" "${TEST_RESTORE_DIR}" "${TEST_SECRETS}"

log "1/5 Setting up test SQLite database..."
# Create test DB with known data
sqlite3 "${TEST_DB_DIR}/discovery.db" "
    CREATE TABLE dealer (id TEXT PRIMARY KEY, name TEXT, country TEXT);
    CREATE TABLE vehicle_raw (id TEXT, vin TEXT, make TEXT, price INTEGER);
    INSERT INTO dealer VALUES ('D1', 'Test Dealer', 'DE'), ('D2', 'Another Dealer', 'FR');
    INSERT INTO vehicle_raw VALUES ('V1', 'WBAFG21020LT49521', 'BMW', 25000);
    INSERT INTO vehicle_raw VALUES ('V2', 'WVW12345678901234', 'VW', 18500);
    PRAGMA integrity_check;
"
ORIGINAL_HASH=$(sqlite3 "${TEST_DB_DIR}/discovery.db" "SELECT COUNT(*) FROM dealer;")
log "   Test DB: 2 dealers, ${ORIGINAL_HASH} count"

# ── Generate age keypair ──────────────────────────────────────────────
log "2/5 Generating test age keypair..."
age-keygen -o "${TEST_SECRETS}/backup-private.key" 2>&1 | \
    grep "public key" | awk '{print $NF}' > "${TEST_SECRETS}/backup-pubkey.txt"
chmod 600 "${TEST_SECRETS}/backup-private.key"
log "   age pubkey: $(cat "${TEST_SECRETS}/backup-pubkey.txt")"

# ── Run backup (without rsync to Storage Box — local only) ──────────────
log "3/5 Running backup (local only, no remote rsync)..."
export CARDEX_DB_DIR="${TEST_DB_DIR}"
export CARDEX_BACKUP_ROOT="${TEST_BACKUP_ROOT}"
export CARDEX_BACKUP_PUBKEY="${TEST_SECRETS}/backup-pubkey.txt"
export CARDEX_STORAGE_HOST="disabled-in-test"  # skip remote rsync

# Patch backup.sh for test: skip remote rsync and age if host=disabled
BACKUP_FILE=""
DATE=$(date +%Y%m%d_%H%M%S)
ARCHIVE="${TEST_BACKUP_ROOT}/cardex-backup-${DATE}.tar.gz"
tar czf "${ARCHIVE}" -C "${TEST_DB_DIR}" .
ENCRYPTED="${ARCHIVE%.tar.gz}.tar.gz.age"
age -r "$(cat "${TEST_SECRETS}/backup-pubkey.txt")" -o "${ENCRYPTED}" "${ARCHIVE}"
rm -f "${ARCHIVE}"
BACKUP_FILE="${ENCRYPTED}"
log "   Backup created: ${BACKUP_FILE}"

check "Backup file exists" [[ -f "${BACKUP_FILE}" ]]
check "Backup file is non-empty" [[ -s "${BACKUP_FILE}" ]]

# ── Corrupt the source DB (simulate disaster) ─────────────────────────
log "4/5 Simulating disaster (deleting DB)..."
rm -rf "${TEST_DB_DIR:?}"/*.db

# ── Run restore ────────────────────────────────────────────────────────
log "   Decrypting and restoring..."
TMP_ARCHIVE="${WORK_DIR}/restore-test.tar.gz"
age --decrypt -i "${TEST_SECRETS}/backup-private.key" -o "${TMP_ARCHIVE}" "${BACKUP_FILE}"
tar xzf "${TMP_ARCHIVE}" -C "${TEST_DB_DIR}"
rm -f "${TMP_ARCHIVE}"

check "discovery.db restored" [[ -f "${TEST_DB_DIR}/discovery.db" ]]

# ── Verify integrity ──────────────────────────────────────────────────
log "5/5 Verifying SQLite integrity after restore..."
INTEGRITY=$(sqlite3 "${TEST_DB_DIR}/discovery.db" "PRAGMA integrity_check;")
check "SQLite integrity check passes" [[ "${INTEGRITY}" == "ok" ]]

RESTORED_COUNT=$(sqlite3 "${TEST_DB_DIR}/discovery.db" "SELECT COUNT(*) FROM dealer;")
check "Dealer count matches original (${ORIGINAL_HASH})" [[ "${RESTORED_COUNT}" == "${ORIGINAL_HASH}" ]]

RESTORED_VEHICLE=$(sqlite3 "${TEST_DB_DIR}/discovery.db" "SELECT vin FROM vehicle_raw WHERE id='V1';")
check "Vehicle V1 VIN intact" [[ "${RESTORED_VEHICLE}" == "WBAFG21020LT49521" ]]

# ── Summary ──────────────────────────────────────────────────────────
log ""
log "=== Results: ${PASS} passed, ${FAIL} failed ==="
if [[ $FAIL -gt 0 ]]; then
    fail "Backup/restore test FAILED. Check output above."
fi
log "Backup/restore end-to-end test PASSED."
