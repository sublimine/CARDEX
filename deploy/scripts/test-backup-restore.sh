#!/usr/bin/env bash
# test-backup-restore.sh — Validates that the latest backup can be
# successfully restored and the resulting DB passes integrity checks.
# Run monthly (or after each deployment).
# Usage: ./test-backup-restore.sh [backup-file.tar.gz.age]
# If no backup file given, uses the latest from /srv/cardex/backups/
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/srv/cardex/backups}"
AGE_KEY="${AGE_KEY_FILE:-/run/credentials/cardex-discovery.age-identity}"
TEMP_DIR=$(mktemp -d /tmp/cardex-restore-test-XXXXXX)

cleanup() { rm -rf "$TEMP_DIR"; }
trap cleanup EXIT

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

# 1. Find latest backup
if [ $# -ge 1 ]; then
  BACKUP_FILE="$1"
else
  BACKUP_FILE=$(ls -t "$BACKUP_DIR"/*.tar.gz.age 2>/dev/null | head -1)
  if [ -z "$BACKUP_FILE" ]; then
    echo "ERROR: No backup files found in $BACKUP_DIR"
    exit 1
  fi
fi

log "Testing backup: $BACKUP_FILE"

# 2. Decrypt
log "Decrypting..."
age --decrypt -i "$AGE_KEY" -o "$TEMP_DIR/backup.tar.gz" "$BACKUP_FILE"

# 3. Extract
log "Extracting..."
tar -xzf "$TEMP_DIR/backup.tar.gz" -C "$TEMP_DIR"

# 4. Find DB
DB_FILE=$(find "$TEMP_DIR" -name "*.db" | head -1)
if [ -z "$DB_FILE" ]; then
  echo "ERROR: No .db file found in backup"
  exit 1
fi

log "Found DB: $DB_FILE ($(du -sh "$DB_FILE" | cut -f1))"

# 5. Integrity check
log "Running SQLite integrity check..."
RESULT=$(sqlite3 "$DB_FILE" "PRAGMA integrity_check;" 2>&1)
if [ "$RESULT" != "ok" ]; then
  echo "ERROR: integrity_check FAILED:"
  echo "$RESULT"
  exit 1
fi

# 6. Row count sanity
DEALER_COUNT=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM dealer;" 2>&1)
VEHICLE_COUNT=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM vehicle;" 2>&1)

log "Dealers: $DEALER_COUNT | Vehicles: $VEHICLE_COUNT"

if [ "$DEALER_COUNT" -lt 1 ]; then
  echo "ERROR: dealer table is empty — backup may be corrupt"
  exit 1
fi

# 7. Log result
BACKUP_DATE=$(stat -c %y "$BACKUP_FILE" | cut -d' ' -f1)
log "PASS: backup from $BACKUP_DATE restored successfully"
log "      Dealers: $DEALER_COUNT | Vehicles: $VEHICLE_COUNT"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) PASS backup=$BACKUP_FILE dealers=$DEALER_COUNT vehicles=$VEHICLE_COUNT" \
  >> /var/log/cardex/backup-restore-tests.log 2>/dev/null || true
