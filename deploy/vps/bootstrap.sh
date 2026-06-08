#!/usr/bin/env bash
# =============================================================================
# CARDEX VPS — one-command bootstrap. Idempotent: safe to re-run.
#
#   curl -fsSL .../bootstrap.sh | bash      # or, inside the repo:
#   bash deploy/vps/bootstrap.sh
#
# Brings up the full pipeline (Postgres + Redis + entity API + seam workers +
# T1 harvesters + discovery), applies migrations, and waits until the API is live.
# Fill deploy/vps/.env (proxies, secrets) BEFORE or AFTER — re-run to apply proxies.
# =============================================================================
set -euo pipefail

REPO_URL="${CARDEX_REPO_URL:-https://github.com/cardex/cardex.git}"
REPO_REF="${CARDEX_REPO_REF:-feature/vps-deploy}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log(){ printf '\033[1;36m[bootstrap]\033[0m %s\n' "$*"; }
die(){ printf '\033[1;31m[bootstrap] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# 1) Dependencies ------------------------------------------------------------
command -v docker >/dev/null 2>&1 || die "docker not installed (https://docs.docker.com/engine/install/)"
docker compose version >/dev/null 2>&1 || die "docker compose v2 not installed"

# 2) Repo (clone only if we are not already inside it) -----------------------
if [ ! -f "$HERE/docker-compose.vps.yml" ]; then
  log "cloning $REPO_URL ($REPO_REF)"
  git clone --branch "$REPO_REF" --depth 1 "$REPO_URL" cardex
  cd cardex/deploy/vps
  HERE="$(pwd)"
fi
cd "$HERE"
COMPOSE="docker compose -f $HERE/docker-compose.vps.yml --env-file $HERE/.env"

# 3) .env --------------------------------------------------------------------
if [ ! -f "$HERE/.env" ]; then
  cp "$HERE/.env.template" "$HERE/.env"
  log ".env created from template — EDIT IT (secrets + RESIDENTIAL_PROXY_* slots), then re-run."
fi

# 4) Build + up (depends_on conditions order migrations → provision → workers) -
log "building images (cached on re-run)…"
$COMPOSE build
log "starting stack…"
$COMPOSE up -d

# 5) Wait for the entity API to report healthy -------------------------------
PORT="$(grep -E '^ENTITY_API_PORT=' "$HERE/.env" | cut -d= -f2 || true)"; PORT="${PORT:-8088}"
BIND="$(grep -E '^ENTITY_API_BIND=' "$HERE/.env" | cut -d= -f2 || true)"; BIND="${BIND:-127.0.0.1}"
log "waiting for entity API on http://$BIND:$PORT/v1/health …"
for i in $(seq 1 60); do
  if curl -fsS -m 4 "http://$BIND:$PORT/v1/health" >/dev/null 2>&1; then
    log "entity API is LIVE."
    break
  fi
  [ "$i" = 60 ] && die "entity API did not come up — check: $COMPOSE logs entity-api"
  sleep 3
done

# 6) Report ------------------------------------------------------------------
log "service states:"; $COMPOSE ps
cat <<EOF

  ✅ CARDEX is up.  Entity API:  http://$BIND:$PORT
     • health     : curl http://$BIND:$PORT/v1/health
     • entities   : curl 'http://$BIND:$PORT/v1/entities?limit=10'
     • inventory  : curl 'http://$BIND:$PORT/v1/inventory?country=DE&limit=5'
     • alerts     : curl http://$BIND:$PORT/v1/alerts

  To unblock the defended giants: fill RESIDENTIAL_PROXY_<CC> in $HERE/.env and re-run:
     bash deploy/vps/bootstrap.sh      # re-provisions identities, restarts harvesters

  Stop:   $COMPOSE down          Logs:  $COMPOSE logs -f <service>
EOF
