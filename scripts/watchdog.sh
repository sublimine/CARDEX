#!/usr/bin/env bash
# CARDEX pipeline watchdog — monitors all critical workers and restarts
# them if they die. Writes status to /tmp/cardex-logs/watchdog.log.
#
# Usage: nohup bash scripts/watchdog.sh &
#
# Workers:
#   - 8 enricher shards
#   - bridge (sitemap_bridge)
#   - repair_pass
#   - sitemap_image_harvester
set -uo pipefail

cd "$(dirname "$0")/.."
LOG=/tmp/cardex-logs/watchdog.log
PID_DIR=/tmp/cardex-pids
mkdir -p "$PID_DIR" /tmp/cardex-logs

log(){ echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG" >&2; }

is_up() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] || return 1
  local pid; pid=$(cat "$pid_file")
  [[ -n "$pid" ]] && ps -p "$pid" > /dev/null 2>&1
}

start_shard() {
  local s=$1
  local log_file=/tmp/cardex-logs/enrich-s$s.log
  local pid_file=$PID_DIR/enrich-s$s.pid
  if ! is_up "$pid_file"; then
    log "starting shard $s"
    MEILI_ENRICHER_SHARD=$s MEILI_ENRICHER_SHARDS=8 \
      MEILI_ENRICHER_CONC=50 MEILI_ENRICHER_TIMEOUT=6 \
      nohup python -u -m scrapers.discovery.meili_enricher > "$log_file" 2>&1 &
    echo $! > "$pid_file"
  fi
}

start_repair() {
  local pid_file=$PID_DIR/repair.pid
  if ! is_up "$pid_file"; then
    log "starting repair"
    REPAIR_CONC=10 REPAIR_BATCH=300 \
      nohup python -u -m scrapers.discovery.repair_pass > /tmp/cardex-logs/repair.log 2>&1 &
    echo $! > "$pid_file"
  fi
}

start_bridge() {
  local pid_file=$PID_DIR/bridge.pid
  if ! is_up "$pid_file"; then
    log "starting bridge"
    nohup python -u -m scrapers.discovery.sitemap_bridge > /tmp/cardex-logs/bridge.log 2>&1 &
    echo $! > "$pid_file"
  fi
}

start_resolver() {
  local pid_file=$PID_DIR/resolver.pid
  if ! is_up "$pid_file"; then
    log "starting sitemap_resolver"
    SITEMAP_RESOLVER_CONCURRENCY=30 \
      nohup python -u -m scrapers.discovery.sitemap_resolver > /tmp/cardex-logs/resolver.log 2>&1 &
    echo $! > "$pid_file"
  fi
}

while true; do
  for s in 0 1 2 3 4 5 6 7; do start_shard "$s"; done
  start_repair
  start_bridge
  start_resolver
  sleep 120
done
