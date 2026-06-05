# PLAN — Cross-Border Price Intelligence API (`services/api`)

> Working plan + progress for a multi-block autonomous build. Source of truth for
> resumption if context is lost. Module path: `cardex.eu/api`. Go 1.26.2.

## Verified reconnaissance (evidence-backed)

- **Storage**: PostgreSQL is wired in `docker-compose.yml` (`postgres:16`, db/user `cardex`,
  pass `${POSTGRES_PASSWORD:-cardex_dev_only}`, `127.0.0.1:5432`). The rich table
  **`vehicles`** exists in `scripts/init-pg.sql` with: `make, model, year, fuel_type,
  mileage_km, co2_gkm, price_raw, currency_raw, last_price_eur, source_country, source_url,
  listing_status, first_seen_at, last_updated_at, sold_at`. Indexes:
  `idx_vehicles_make_model`, `idx_vehicles_source_country`, `idx_vehicles_listing_status`.
  → This is the primary data source. (CONTEXT_FOR_AI.md from 2026-04-15 predates Strategy B
  PG scraper fleet; PG is real now. Discrepancy noted in delivery report.)
- **Redis**: `redis/redis-stack-server`, `requirepass ${REDIS_PASSWORD:-cardex_dev_only}`,
  `REDIS_ADDR redis:6379`.
- **compose `api` service already declared**: builds `services/api/Dockerfile`, port `8080`,
  env `DATABASE_URL`, `REDIS_ADDR`, `REDIS_PASSWORD`, `PORT=8080`, `LOG_LEVEL`, `CORS_ORIGINS`,
  healthcheck `GET /healthz`. We honor this contract exactly.
- **Existing tax engine**: `innovation/tax_engine` (`cardex.eu/tax`) computes VAT only
  (margin scheme, intra-community, export/import, VIES; 6 countries). **No registration tax.**
  Repo pattern = independent modules that duplicate fiscal tables (`innovation/routes` mirrors
  the VAT map). → We build a self-contained `landedcost` package (VAT consistent w/ tax_engine
  + the missing registration-tax layer), and document tax_engine for future consolidation.
- **Transport corridor matrix** exists in `innovation/routes/transport.go` (30 pairs, EUR cents).
  → Port the table (cite source).
- **House style**: stdlib `net/http` (Go 1.22+ method+pattern ServeMux), `log/slog` JSON,
  prometheus `promauto` (`cardex_api_*`), hand-rolled `config` package, bearer-style auth with
  `subtle.ConstantTimeCompare`. No router framework. `writeJSON` helper. Module `cardex.eu/api`.
- **Price forecasting** (`innovation/chronos_forecasting`, :8503) callable but CSV-backed; out of
  core scope — optional enrichment, not a hard dependency.

## Architecture decision

New standalone Go module `services/api` (`cardex.eu/api`), PostgreSQL (`pgx/v5`) + Redis
(`go-redis/v9`), built `GOWORK=off`. Data source: PG `vehicles`. Auth: `X-API-Key` (keys in
Redis + env bootstrap). Rate limit: Redis fixed-window per tier (free 100/min, paid 1000/min).
OpenAPI 3.1 hand-authored + `go:embed`, served at `/openapi.yaml` + Swagger UI at `/docs`.

## Layout

```
services/api/
  go.mod / go.sum / README.md / openapi.yaml / Dockerfile / .dockerignore
  cmd/api-service/main.go
  migrations/001_arbitrage_alerts.sql
  internal/
    config/        env loader (PORT, DATABASE_URL, REDIS_ADDR, REDIS_PASSWORD, CORS_ORIGINS,
                   API_BOOTSTRAP_KEY, rate limits, SMTP_*, ALERT_EVAL_INTERVAL, CHF_EUR_RATE)
    metrics/       prometheus cardex_api_* (requests, latency, ratelimit, alerts)
    httpx/         writeJSON, error envelope, middleware (recover, reqID, log, CORS, apikey, ratelimit)
    apikeys/       APIKey model + tiers; Redis lookup + env bootstrap seeding
    redisx/        client wrapper (apikey, ratelimit, cache GET/SET helpers)
    store/         Store interface + pgxStore (market stats, listings) — interface => fakeable
    landedcost/    vat.go, registration.go, transport.go, landedcost.go + tests  [PROMPT FOCUS]
    marketprice/   service (P10/25/50/75/90 per country) + handler + tests
    arbitrage/     service (cross-border opportunities, net margin via landedcost) + handler + tests
    alerts/        schema, store (PG), handler (CRUD), evaluator (goroutine), notify (webhook+SMTP) + tests
```

## Endpoints

- `GET  /api/v1/market-price`  — make/model/year[/fuel/mileage]: per-country P10/25/50/75/90 + count + sample.
- `GET  /api/v1/arbitrage`     — same filters: ranked cross-border opportunities w/ net margin + listing link.
- `GET  /api/v1/landed-cost`   — from/to/price[/co2/fuel/age/km]: VAT + registration + transport breakdown.
- `POST /api/v1/alerts` `GET /api/v1/alerts` `GET /api/v1/alerts/{id}` `DELETE /api/v1/alerts/{id}`.
- `GET  /healthz` (compose) + `/metrics` + `/openapi.yaml` + `/docs`.

## Build blocks & status

- [x] B1 scaffold: go.mod, config, metrics, httpx, redisx, apikeys, store interface+pgx
- [x] B2 landedcost (+tests)  ← known-value tests pass (ES IEDMT, DE=0, CH 4%, VAT, Compute)
- [x] B3 marketprice + arbitrage (+pure-logic + handler tests, fake store)
- [x] B4 alerts (schema, store, handler, evaluator, notify, +tests)
- [x] B5 main wiring + OpenAPI 3.1 + Swagger UI + README
- [x] B6 Dockerfile + migration; compose `api` service already wired; Caddy `/api/v1/*`,
      `/openapi.yaml`, `/docs` routes added (verified present on disk).
- [x] B7 build/vet/test/gofmt green; `-race` green; real-PostgreSQL integration green;
      full live smoke test passed; go-reviewer + security-reviewer run; findings hardened.

## Post-review hardening (applied)
SSRF guard on webhooks (block private/loopback/link-local incl. 169.254.169.254, no redirects)
+ per-call timeout; reject CRLF in make/model/fuel/email + sanitize email headers; make/model/fuel
length cap (64); sha256-hashed cache keys; `errors.Is`; rate-limiter-degraded metric;
CORS Allow-Credentials:false; bootstrap-key min length 16; QueryTimeout wired; shutdown error
logged; dead code removed.

## Quality gates

`GOWORK=off go build ./...`, `GOWORK=off go vet ./...`, `GOWORK=off go test ./...` all green.
Landed-cost tests assert known values (DE=0 reg, ES IEDMT CO2 brackets, CH 4%+8.1%, margin VAT).
Handlers tested via fake Store (no live PG). Structured logging + Prometheus + OpenAPI present.
