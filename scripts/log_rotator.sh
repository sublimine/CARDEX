#!/usr/bin/env bash
# Log rotator — runs every hour, truncates logs > 50 MB and keeps tail 1000 lines.
# Prevents disk exhaustion during 20h+ runs.
#
# Usage: nohup bash scripts/log_rotator.sh &
while true; do
  for f in /tmp/cardex-logs/*.log; do
    [[ -f "$f" ]] || continue
    size=$(stat -c %s "$f" 2>/dev/null || echo 0)
    if [[ $size -gt 52428800 ]]; then
      # Keep last 1000 lines
      tail -n 1000 "$f" > "${f}.tmp" && mv "${f}.tmp" "$f"
      echo "$(date -u +%FT%TZ) rotated $f ($size bytes -> $(stat -c %s "$f"))" >> /tmp/cardex-logs/log_rotator.log
    fi
  done
  sleep 3600
done
