#!/usr/bin/env bash
# CARDEX dashboard — one-shot status report of the entire pipeline.
#
# Usage: bash scripts/dashboard.sh

set -u

echo "╔══════════════════════════════════════════════════════════╗"
echo "║           CARDEX PIPELINE DASHBOARD                      ║"
echo "║           $(date -u +%Y-%m-%dT%H:%M:%SZ)                      ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo

echo "── Running processes ──────────────────────────────────────"
for pid_file in /tmp/cardex-pids/*.pid; do
  [[ -f "$pid_file" ]] || continue
  name=$(basename "$pid_file" .pid)
  pid=$(cat "$pid_file")
  if ps -p "$pid" > /dev/null 2>&1; then
    printf "  %-20s UP   (pid=%s)\n" "$name" "$pid"
  else
    printf "  %-20s DOWN (pid=%s)\n" "$name" "$pid"
  fi
done
echo

echo "── Postgres: discovery_candidates ─────────────────────────"
docker exec cardex-pg psql -U cardex -d cardex -c "
SELECT source,
       COUNT(*) FILTER (WHERE domain IS NOT NULL) AS with_domain,
       COUNT(*) FILTER (WHERE domain IS NULL) AS identity,
       COUNT(*) FILTER (WHERE sitemap_status='found') AS sitemap_found
FROM discovery_candidates
GROUP BY source
ORDER BY 2 DESC, 3 DESC;
" 2>&1
echo

echo "── Postgres: vehicle_index ────────────────────────────────"
docker exec cardex-pg psql -U cardex -d cardex -c "
SELECT country, COUNT(*) AS listings
FROM vehicle_index
GROUP BY country
ORDER BY 2 DESC;
" 2>&1
echo

echo "── Meilisearch: completeness ──────────────────────────────"
curl -s -H "Authorization: Bearer cardex_meili_dev_only" \
  "http://localhost:7700/indexes/vehicles/stats" | \
  python -c "import sys,json; d=json.load(sys.stdin); print(f'  total docs: {d.get(\"numberOfDocuments\"):,}')"

for field in make model price_eur year mileage_km fuel_type transmission; do
  n=$(curl -s -H "Authorization: Bearer cardex_meili_dev_only" \
    "http://localhost:7700/indexes/vehicles/search" \
    -H "Content-Type: application/json" \
    -d "{\"q\":\"\",\"limit\":0,\"filter\":\"$field EXISTS\"}" | \
    python -c "import sys,json; print(json.load(sys.stdin)['estimatedTotalHits'])")
  printf "  %-12s %10d\n" "$field" "$n"
done

complete=$(curl -s -H "Authorization: Bearer cardex_meili_dev_only" \
  "http://localhost:7700/indexes/vehicles/search" \
  -H "Content-Type: application/json" \
  -d '{"q":"","limit":0,"filter":"make EXISTS AND model EXISTS AND price_eur EXISTS AND year EXISTS AND mileage_km EXISTS"}' | \
  python -c "import sys,json; print(json.load(sys.stdin)['estimatedTotalHits'])")
printf "  %-12s %10d  (all 5 critical fields)\n" "COMPLETE" "$complete"
echo

echo "── Enricher shards progress ───────────────────────────────"
for s in 0 1 2 3 4 5 6 7; do
  line=$(grep "progress:" /tmp/cardex-logs/enrich-s$s.log 2>/dev/null | tail -1 | awk -F'progress: ' '{print $2}')
  printf "  s%d: %s\n" "$s" "$line"
done
echo

echo "── Recent log entries ─────────────────────────────────────"
for f in repair-1 sirene-v311 osm-exp trustpilot ct-logs n2d resolver-v2; do
  [[ -f /tmp/cardex-logs/$f.log ]] || continue
  last=$(tail -1 /tmp/cardex-logs/$f.log 2>/dev/null | cut -c1-100)
  printf "  %-18s %s\n" "$f" "$last"
done
