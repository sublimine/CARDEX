# Docker Hardening — CARDEX (2026-06)

**Date:** 2026-06-05
**Scope:** Full audit + hardening of every Docker artifact in the repo.
**Author:** infra hardening pass (CARDEX Bot)

This document records what was audited, the root-cause defects found, the changes
applied per file, and the residual gaps that are **out of Docker's reach** (missing
application code / scripts). Nothing here is cosmetic: every change is verifiable.

---

## 0. Inventory — what Docker actually exists

| Artifact | Role | Real / Aspirational |
|----------|------|---------------------|
| `deploy/docker/docker-compose.yml` (+ `.prod.yml`) | **Deployed** Phase-5 stack: discovery + extraction + quality (SQLite) + observability + Caddy | **REAL** (this is what runs on the Hetzner CX42) |
| `deploy/docker/Dockerfile.{discovery,extraction,quality}` | Multi-stage Go → distroless | **REAL** |
| `docker-compose.yml` (repo root) | "Vision" stack: PostgreSQL + ClickHouse + Redis + MeiliSearch + `services/*` + scraper fleet | **PARTLY ASPIRATIONAL** — see §5 |
| `scrapers/` Python fleet | Strategy-B marketplace scrapers (curl_cffi + Camoufox) | **REAL code, had no Dockerfile** |
| `innovation/{rag_search,gnn_dealer_inference,chronos_forecasting}/Dockerfile` | Experimental CPU-only ML services | **REAL (experimental)** |

Ground truth: `CONTEXT_FOR_AI.md` states PostgreSQL/ClickHouse/Redis/MeiliSearch are
**not** part of the MVP (storage is SQLite) and `services/*` are stubs. The root
compose wires the *real* scraper fleet to those not-yet-built services.

---

## 1. Root-cause defects found (pre-existing bugs)

### 1.1 — Health checks never worked on the deployed stack (CRITICAL)
The `deploy/docker` compose probed `wget http://localhost:8080/healthz` for all three
core services. Three independent reasons it could never pass:

1. **Wrong port.** `/healthz` (discovery) and `/health` (extraction, quality) are
   served on the **metrics** address (`cfg.MetricsAddr` = `:9101` / `:9102` / `:9103`),
   verified in `discovery/cmd/discovery-service/main.go:130`,
   `extraction/cmd/extraction-service/main.go:181`, `quality/cmd/quality-service/main.go:210`.
   There is **no** server on `:8080` — `EXPOSE 8080` was vestigial.
2. **Wrong path.** extraction/quality expose `/health`, not `/healthz`.
3. **No tool.** The runtime image is `gcr.io/distroless/static-debian12` — **no shell,
   no `wget`, no `curl`**. `CMD-SHELL "wget …"` cannot execute at all.

Net effect: `depends_on: condition: service_healthy` could never fire; the dependency
chain (extraction waits for discovery, quality waits for extraction) was inert.

**Fix:** a tiny dependency-free Go probe (`deploy/docker/healthcheck/`) is compiled in
the builder stage and baked into each distroless image, targeting the **correct**
per-service port+path. See §2.

### 1.2 — `:latest` everywhere (supply-chain risk)
Root compose pinned `clickhouse`, `redis-stack-server`, `meilisearch`, `prometheus`,
`grafana`, `alpine/curl` to `:latest` — non-reproducible builds, silent breaking
upgrades. **Fix:** all pinned to explicit versions (§4).

### 1.3 — Redis `--protected-mode no` + published on all interfaces
The instance disabled protected mode **and** published `6379:6379` on `0.0.0.0`,
i.e. an unauthenticated Redis reachable from the host network. **Fix:** `requirepass`,
`noeviction` (Streams-safety), no host port, internal `data` network only (§3.6).

### 1.4 — Hardcoded secrets inline
`cardex_dev_only` passwords, HMAC secret and JWT secret were literals in the compose.
**Fix:** every secret is now `${VAR:-dev_default}` so real values come from `.env` in
any non-local environment, while local `docker compose up` still works.

### 1.5 — No `.dockerignore` anywhere
Zero `.dockerignore` files in the repo → full build context (incl. `.git`, `secrets/`,
`*.db`, `apps/`, `node_modules/`) shipped to the daemon on every build. **Fix:** added
root + `scrapers/` + 3× `innovation/` ignore files.

### 1.6 — Scraper entrypoint wrong / image missing
Root compose called `python -m run_all`, but no `run_all` module exists. The verified
orchestrator is `python -m scrapers.coordinator` (`scrapers/coordinator.py:27`). The
fleet had **no Dockerfile at all** despite being referenced 8×. **Fix:** created
`scrapers/Dockerfile` and corrected the per-territory `command:` (§6).

---

## 2. `deploy/docker/` — the deployed stack (REAL)

### New: `deploy/docker/healthcheck/{main.go,go.mod}`
A 40-line stdlib-only HTTP probe (`module cardex/healthcheck`, no external deps).
Resolves its target from arg → `HEALTHCHECK_URL` env → compile-time default; exit 0 on
2xx within a 3 s timeout. Verified: `go vet` clean, cross-compiles to a static
linux/amd64 ELF (the distroless target).

### `Dockerfile.{discovery,extraction,quality}`
| Change | Detail |
|--------|--------|
| Baked health probe | Builder compiles `/healthcheck`; `HEALTHCHECK` instruction added |
| Correct endpoint | `ENV HEALTHCHECK_URL` = `:9101/healthz`, `:9102/health`, `:9103/health` |
| Removed vestigial `EXPOSE 8080` | Only the real metrics port is exposed now |
| Explicit non-root | `USER 65532:65532` (defense-in-depth on top of distroless `:nonroot`) |
| OCI provenance | `org.opencontainers.image.{source,version,revision,created}` via `ARG` |
| Faster builds | BuildKit `--mount=type=cache` for `/go/pkg/mod` + `/root/.cache/go-build` |
| `ENV CGO_ENABLED=0 …` | Hoisted to a single builder `ENV` |

The static-link flags (`-s -w -extldflags=-static`), `-trimpath`, and distroless base
were already correct and were preserved.

### `docker-compose.yml` (base)
- **Network segmentation (least privilege):** `cardex-edge` (Caddy), `cardex-core`
  (services + Caddy + Prometheus, bridge → NAT egress for crawling), `cardex-monitoring`
  (Prometheus + Grafana + Alertmanager). Grafana/Alertmanager cannot reach the crawling
  services; services cannot reach the dashboards.
- **Working health checks:** core services use `["CMD", "/healthcheck"]`; Prometheus,
  Alertmanager, Grafana use their busybox `wget` + documented endpoints
  (`/-/healthy`, `/api/health`); Caddy probes its admin API (`:2019/config/`).
- **Resource limits + reservations** on **every** service (CPU + memory) to prevent OOM
  kills on the 16 GB node.
- **Security:** `security_opt: [no-new-privileges:true]` + `cap_drop: [ALL]` on all
  (via a `*hardening` YAML anchor); Caddy gets back only `NET_BIND_SERVICE` for ports
  80/443. `read_only: true` + sized `tmpfs /tmp` on the distroless Go services,
  Prometheus and Alertmanager. `init: true` on the Go services for clean signal/zombie
  handling.
- **Logging:** `json-file` with `max-size=10m`, `max-file=3` (anchor) — bounded disk.

### `docker-compose.prod.yml` (overlay)
Rewritten to **inherit** all base hardening (networks, security, read-only, health,
reservations) and only override the prod deltas: registry images (`build: !reset null`),
`restart: always`, `journald` logging, host-NVMe bind mounts, tighter memory limits,
Grafana port removed (SSH-tunnel only). Validated as a base+overlay merge.

### New: root `.dockerignore`
Keeps exactly what the Go builds copy (`go.work*`, `discovery/`, `extraction/`,
`quality/`, `internal/`, `services/`, `deploy/docker/healthcheck/`) and drops `.git`,
secrets, `*.db`, `apps/`, `extensions/`, `workspace/`, `scrapers/`, `innovation/`,
caches and docs.

---

## 3. Root `docker-compose.yml` — the vision stack

Hardened as infrastructure-as-code. A prominent header now documents that this stack
**does not boot as-is** (§5). Per-service hardening applied uniformly via the
`*hardening` anchor (`no-new-privileges`, `cap_drop ALL`, log rotation) plus resource
limits/reservations, health checks, restart policy, and 3-network segmentation
(`frontend` / `backend` / `data`). Datastore-specific tuning:

### 3.5 — PostgreSQL (point 5)
SSD/OLTP tuning for the 2 GB container: `shared_buffers=512MB`,
`effective_cache_size=1536MB`, `work_mem=32MB` (lowered from 64 MB to bound
per-connection memory × `max_connections=100`), `maintenance_work_mem=256MB`,
`random_page_cost=1.1`, `effective_io_concurrency=200`, `wal_compression=on`,
`max_wal_size=2GB`/`min_wal_size=512MB`, `checkpoint_completion_target=0.9`,
`wal_level=logical` (kept), `jit=off`, `timezone=UTC`. Port bound to `127.0.0.1` only.

### 3.6 — Redis (point 6)
`--requirepass` (parametrized), **removed `--protected-mode no`**, `maxmemory` lowered
to `1536mb` (headroom under the 2 GB limit), **`maxmemory-policy noeviction`** — because
STATUS.md mandates "Redis: solo Streams" and LRU eviction would silently drop stream
entries; `noeviction` fails writes loudly (backpressure) and trimming is done via
`XADD … MAXLEN`. AOF (`everysec`) + RDB snapshots + RedisBloom module preserved. No host
port; auth-aware health check (`redis-cli -a … ping`).

### 3.7 — MeiliSearch (point 7)
`MEILI_NO_ANALYTICS=true`, `MEILI_HTTP_PAYLOAD_SIZE_LIMIT` (default 100 MB),
`MEILI_MAX_INDEXING_MEMORY=512Mb` (under the 1 GB limit), `MEILI_MAX_INDEXING_THREADS=2`,
parametrized master key, `MEILI_ENV`/log level parametrized. No host port.

### ClickHouse
Pinned `:24.8`, `ulimits.nofile=262144`, no host ports, auth-aware health check,
limits + reservations.

---

## 4. Image pins (point 10)

| Service | Before | After |
|---------|--------|-------|
| clickhouse | `:latest` | `:24.8` |
| redis-stack-server | `:latest` | `:7.4.0-v1` |
| meilisearch | `:latest` | `:v1.12` |
| prometheus | `:latest` (root) | `:v3.0.1` |
| grafana | `:latest` (root) | `:11.5.0` |
| alpine/curl | `:latest` | `:8.11.1` |
| postgres | `:16-bookworm` / `:16-alpine` | unchanged (already pinned) |

> Further hardening (recommended, not yet applied): pin by `@sha256:` digest for full
> supply-chain immutability. The 3 distroless Go images already carry an in-file note on
> how to pin the runtime base digest.

---

## 5. Residual gaps — out of Docker's reach (honest)

The root `docker-compose.yml` will **not** `docker compose up` until application
artifacts exist. These are **not** Docker defects:

1. **`services/*/Dockerfile` (7) + code missing** — only `services/pipeline/cmd/pipeline/main.go`
   exists (a stub). `pipeline`, `api`, `scheduler`, `census`, `imgproxy`, `frontier`,
   `gateway` have no Dockerfile and no service code. Their `build:` targets fail.
2. **Missing bootstrap files** referenced by the compose: `scripts/init-redis.sh`,
   `scripts/init-meili.sh`, `scripts/seed-demo.sql` (verified missing 2026-06-05;
   `monitoring/prometheus.yml`, also referenced, does exist).
3. **Worker entrypoints** `python -m enrich_worker` / `python -m search_indexer`: those
   modules do not exist in `scrapers/` (only `scrapers.coordinator` is verified). The
   scraper containers themselves are corrected to `scrapers.coordinator`.
4. **Caddy → service API**: the Caddyfile routes to a `:8080` service API that the
   core services do not serve (they bind only the metrics port). Pre-existing; outside
   this pass.
5. **Redis auth threading**: `REDIS_PASSWORD` is now provided to every consumer, but the
   (unbuilt) Go services must actually read it for auth to take effect.

`read_only` was intentionally **not** applied to the datastore containers (writable data
dirs) or the scraper fleet (browsers need a writable cache).

---

## 6. Scrapers (`scrapers/`)

### New: `scrapers/Dockerfile`
Multi-stage: a builder venv (`build-essential` only here) → a lean
`python:3.11-slim-bookworm` runtime. Installs the **real** `requirements.txt` (curl_cffi,
Camoufox, capsolver, markitdown, …), Chromium via `playwright install --with-deps`, and
Camoufox's patched Firefox via `python -m camoufox fetch` (as the non-root user, so it
lands in that user's cache). Runs as `appuser` (uid 10001) under `tini` (PID 1). Code is
copied to `/app/scrapers` with `PYTHONPATH=/app` so `import scrapers.*` resolves.
**Health check** = `python -c "import scrapers.coordinator"` — an honest liveness smoke
test (the module contract guarantees no network/heavy imports), because the Prometheus
metrics server is optional (`prometheus_client` is not a hard dependency) and would give
a false signal.

### New: `scrapers/.dockerignore`
Drops tests, caches, `*.db`, `.env`, docs from the build context.

### Compose fix
All six `scraper-*` services now run `command: ["-m", "scrapers.coordinator"]`.

---

## 7. Innovation services (`innovation/`)

`rag_search`, `gnn_dealer_inference`, `chronos_forecasting` Dockerfiles rebuilt as
multi-stage venv images:

| Hardening | Applied |
|-----------|---------|
| Pinned base | `python:3.11-slim-bookworm` |
| Build tools out of runtime | builder venv → runtime copies `/opt/venv` |
| Non-root | `appuser` uid 10001 |
| CPU-only torch | explicit `--index-url …/whl/cpu` (gnn, chronos) — avoids multi-GB CUDA wheels |
| Health checks | `python urllib` GET on the **verified** `/health` route (`:8501/:8502/:8503`) |
| gnn refactor | now uses its `requirements.txt` instead of inline installs |
| `.dockerignore` | per service — drops `data/`, `models/`, caches, tests |

> These services are experimental/not production-deployed and have no compose file, so
> resource limits should be supplied at `docker run` time (`--memory`, `--cpus`).

---

## 8. Verification evidence

| Check | Command | Result |
|-------|---------|--------|
| Root compose schema | `docker compose -f docker-compose.yml config` | **OK** |
| Deploy base schema | `docker compose -f deploy/docker/docker-compose.yml config` | **OK** |
| Deploy base+prod merge | `… -f docker-compose.prod.yml config` | **OK** |
| Dockerfile lint ×7 | `docker build --check` | **0 warnings each** |
| Health probe | `go vet` + `GOOS=linux go build` | **OK, static ELF** |

Environment: Docker 29.2.1, Compose v5.0.2, Go 1.26.2.

> Full image builds were **not** executed here (heavy ML/browser layers require network
> and significant disk). The Dockerfiles are statically validated; CI should run the
> actual builds.

---

## 9. The 10 requested dimensions — status

| # | Dimension | Status |
|---|-----------|--------|
| 1 | Health checks for all services | ✅ deployed stack fixed at the root; root stack + scrapers + innovation covered |
| 2 | Resource limits (mem + CPU) | ✅ limits **and** reservations on every service |
| 3 | Network isolation | ✅ edge/core/monitoring (deploy) + frontend/backend/data (root) |
| 4 | Security (non-root, cap_drop, read-only) | ✅ `cap_drop ALL` + `no-new-privileges` everywhere; non-root images; `read_only` where safe |
| 5 | PostgreSQL tuning | ✅ SSD/OLTP profile |
| 6 | Redis tuning | ✅ noeviction + requirepass + bounded maxmemory |
| 7 | MeiliSearch | ✅ key + payload/indexing limits + analytics off |
| 8 | Logging rotation | ✅ json-file max-size/max-file (journald in prod) |
| 9 | Restart policies | ✅ per service type (unless-stopped / always / "no" for one-shots) |
| 10 | Build optimization | ✅ multi-stage everywhere + complete `.dockerignore` set + BuildKit caches |

---

## 10. Recommended follow-ups (not in this pass)

- Pin runtime base images by `@sha256:` digest (supply-chain immutability).
- Build the missing `services/*` Dockerfiles + bootstrap scripts so the root stack boots.
- Add a CI job that runs the real `docker build` for all images on PRs.
- Add seccomp/AppArmor profiles for the scraper fleet's browser containers.
