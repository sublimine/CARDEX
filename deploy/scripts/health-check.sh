#!/usr/bin/env bash
# health-check.sh — external CARDEX health monitor
# Run from a separate machine (e.g. Oracle Cloud Free Tier VM) via cron every 5 min.
#
# Crontab entry:
#   */5 * * * * /opt/cardex-monitor/health-check.sh >> /var/log/cardex-health.log 2>&1
#
# On failure: sends alert email via sendmail/msmtp. Configure ALERT_EMAIL below.

set -euo pipefail

CARDEX_URL="${CARDEX_URL:-https://cardex.io}"
ALERT_EMAIL="${ALERT_EMAIL:-operator@example.com}"
TIMEOUT_SECS="${HEALTH_TIMEOUT:-10}"
STATE_FILE="/tmp/cardex-health-state"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

# ── Check /health endpoint ────────────────────────────────────────────
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    --max-time "${TIMEOUT_SECS}" \
    --connect-timeout 5 \
    "${CARDEX_URL}/health" 2>/dev/null || echo "000")

if [[ "${HTTP_STATUS}" == "200" ]]; then
    log "UP: ${CARDEX_URL}/health → ${HTTP_STATUS}"
    # Clear failure state if previously flagged
    if [[ -f "${STATE_FILE}" ]]; then
        rm -f "${STATE_FILE}"
        # Send recovery notification
        send_alert "RECOVERY" "CARDEX is back UP at ${CARDEX_URL}" || true
    fi
    exit 0
fi

# ── DOWN detected ─────────────────────────────────────────────────────
log "DOWN: ${CARDEX_URL}/health → ${HTTP_STATUS}"

# Debounce: only alert if down for 2+ consecutive checks (10 min)
if [[ -f "${STATE_FILE}" ]]; then
    PREVIOUS_STATUS=$(cat "${STATE_FILE}")
    FAILURE_COUNT=$((PREVIOUS_STATUS + 1))
    echo "${FAILURE_COUNT}" > "${STATE_FILE}"
    log "Consecutive failures: ${FAILURE_COUNT}"
    if [[ ${FAILURE_COUNT} -ge 2 ]]; then
        send_alert "DOWN" "CARDEX has been DOWN for ${FAILURE_COUNT} checks (${CARDEX_URL}). HTTP: ${HTTP_STATUS}"
    fi
else
    echo "1" > "${STATE_FILE}"
    log "First failure detected — will alert on next check if still down."
fi

exit 1

# ── Alert function ────────────────────────────────────────────────────
send_alert() {
    local level="$1"
    local message="$2"
    local subject="[CARDEX ${level}] ${message}"

    log "Sending alert: ${subject}"
    # Uses sendmail/msmtp — configure /etc/msmtprc for SMTP relay
    echo -e "Subject: ${subject}\n\n${message}\n\nTimestamp: $(date -u)" \
        | sendmail "${ALERT_EMAIL}" 2>/dev/null || \
        log "Alert email failed — check sendmail/msmtp config"
}
