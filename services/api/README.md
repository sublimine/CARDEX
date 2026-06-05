# CARDEX Cross-Border Price Intelligence API

REST API exposing CARDEX's pan-European used-vehicle data as cross-border price
intelligence across **DE, FR, ES, NL, BE, CH**. Module path: `cardex.eu/api`.

> The highest-impact service validated by three independent market studies
> (`docs/strategic/`): no competitor offers real-time cross-border arbitrage for
> the same vehicle across 6 markets. See `PLAN.md` for the design rationale.

## Endpoints

All `/api/v1/*` endpoints require an `X-API-Key` header and are rate-limited per
tier (free 100 req/min, paid 1000 req/min). Prices are EUR.

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/api/v1/market-price` | Per-country price distribution P10/P25/P50/P75/P90 for a vehicle cohort. |
| `GET`  | `/api/v1/arbitrage` | Ranked cross-border opportunities with **net margin after landed cost** and a link to a concrete listing. |
| `GET`  | `/api/v1/landed-cost` | Itemized landed cost (transport + VAT + registration tax + fees) between any country pair. |
| `POST` | `/api/v1/alerts` | Create an arbitrage alert (notify by webhook or email when margin > X%). |
| `GET`  | `/api/v1/alerts` | List your alerts. |
| `GET`  | `/api/v1/alerts/{id}` | Fetch one alert. |
| `DELETE` | `/api/v1/alerts/{id}` | Delete an alert. |
| `GET`  | `/healthz` | Liveness/readiness (PostgreSQL reachable). |
| `GET`  | `/metrics` | Prometheus metrics (`cardex_api_*`). |
| `GET`  | `/openapi.yaml`, `/docs` | OpenAPI 3.1 spec + Swagger UI. |

### Filter parameters (market-price & arbitrage)

`make` (required), `model` (required), `year` **or** `year_min`/`year_max`,
`fuel`, `mileage_min`, `mileage_max`, `countries` (CSV subset of DE,FR,ES,NL,BE,CH).
Arbitrage additionally accepts `min_margin_pct`, `max_results`, `buy_country`,
`sell_country`, `be_region` (FLANDERS|WALLONIA|BRUSSELS).

## Architecture

- **PostgreSQL** (`vehicles` table) is the data source — read via `pgx`. EUR
  prices use `last_price_eur`, falling back to `price_raw` converted from CHF.
- **Redis** holds API keys (`apikey:<key>`), rate-limit counters, the response
  cache, and alert notification state.
- **Landed cost** (`internal/landedcost`) reuses the VAT model of
  `cardex.eu/tax` (margin scheme / intra-EU / EU↔CH) and adds the registration
  tax layer that did not exist before — **ES IEDMT, NL BPM, FR malus, BE BIV/TMC,
  CH automobile tax** — plus the transport corridor matrix ported from
  `cardex.eu/routes`. Indicative rate tables (NL/FR/BE) are clearly marked and
  must be reviewed annually; ES/DE/CH are precise.
- **Alerts** definitions are immutable in PostgreSQL (INSERT/DELETE only,
  ADR-0006); a background evaluator scans active alerts each
  `ALERT_EVAL_INTERVAL` and notifies via webhook/SMTP, deduping on a signature
  stored in Redis.

## Configuration (environment)

| Var | Default | Notes |
|-----|---------|-------|
| `PORT` | `8080` | Listen port. |
| `DATABASE_URL` | `postgres://cardex:cardex_dev_only@localhost:5432/cardex` | PostgreSQL DSN. |
| `REDIS_ADDR` / `REDIS_PASSWORD` | `localhost:6379` / — | Redis. |
| `API_BOOTSTRAP_KEY` | — | Optional admin key granted enterprise tier without a Redis entry. |
| `RATE_LIMIT_FREE` / `RATE_LIMIT_PAID` / `RATE_LIMIT_ENTERPRISE` | `100` / `1000` / `0` | Per-minute ceilings (0 = unlimited). |
| `CACHE_TTL` | `5m` | Response cache TTL. |
| `CHF_EUR_RATE` | `1.04` | CHF→EUR conversion for Swiss prices. |
| `ALERTS_ENABLED` | `true` | Toggle the background evaluator. |
| `ALERT_EVAL_INTERVAL` | `15m` | Evaluator cadence. |
| `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASS`/`SMTP_FROM` | — / `587` / — / — / `alerts@cardex.eu` | Email delivery (empty host disables email). |
| `LOG_LEVEL` | `info` | debug\|info\|warn\|error. |
| `CORS_ORIGINS` | `http://localhost:3001,http://localhost:3000` | Allowed browser origins. |

## Run & test

```bash
# Run (Windows + Application Control: never build .exe — use go run)
GOWORK=off go run ./cmd/api-service/

# Unit tests
GOWORK=off go test ./...

# Integration tests against a real PostgreSQL
TEST_DATABASE_URL="postgres://cardex:pass@localhost:5432/cardex" \
  GOWORK=off go test -tags integration ./internal/store/
```

In Docker Compose the service is wired as `api` (postgres + redis dependencies,
fronted by Caddy at `/api/v1/*`).

## Examples

```bash
# Market price for a BMW 320d (2020) per country
curl -H "X-API-Key: $KEY" \
  "http://localhost:8080/api/v1/market-price?make=BMW&model=320d&year=2020"

# Cross-border arbitrage, minimum 5% net margin
curl -H "X-API-Key: $KEY" \
  "http://localhost:8080/api/v1/arbitrage?make=BMW&model=320d&min_margin_pct=5"

# Landed cost DE → ES for an 18 000 EUR diesel, CO2 130, 2 years old
curl -H "X-API-Key: $KEY" \
  "http://localhost:8080/api/v1/landed-cost?from=DE&to=ES&price=18000&co2=130&fuel=diesel&age_months=24"

# Create an alert
curl -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -X POST http://localhost:8080/api/v1/alerts \
  -d '{"make":"BMW","model":"320d","min_margin_pct":10,"sell_countries":["NL"],"webhook_url":"https://example.com/hook"}'
```
