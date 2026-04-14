# discovery — Phase 2 Sprint 1

Go module `cardex.eu/discovery`.

Implements the Knowledge Graph scaffolding and Family A sub-technique A.FR.1
(INSEE Sirene API — French commercial registry).

## Directory structure

```
discovery/
├── cmd/
│   └── discovery-service/   main entry point
├── internal/
│   ├── config/              environment variable loader
│   ├── db/                  SQLite open + WAL migrate + query helpers
│   ├── kg/                  Knowledge Graph types, interface, SQLiteGraph implementation
│   ├── metrics/             Prometheus counters/histograms/gauges
│   ├── runner/              FamilyRunner + SubTechnique interfaces
│   └── families/
│       └── familia_a/
│           ├── family.go    FamilyA orchestrator
│           └── fr_sirene/   A.FR.1 — INSEE Sirene implementation + tests
├── testdata/
│   └── sirene_response.json fixture for unit tests
└── go.mod
```

## Running

```bash
export INSEE_TOKEN=<your-insee-bearer-token>
export DISCOVERY_DB_PATH=./data/discovery.db
export DISCOVERY_ONE_SHOT=true
mkdir -p data
go run ./cmd/discovery-service
```

The Prometheus `/metrics` endpoint is available at `:9090/metrics` by default.
Set `METRICS_ADDR=:PORT` to change it.

## Testing

```bash
GOWORK=off go test ./...
```

All tests run without network access (httptest.Server mock).

## Environment variables

| Variable              | Default                  | Description                              |
|-----------------------|--------------------------|------------------------------------------|
| `DISCOVERY_DB_PATH`   | `./data/discovery.db`    | SQLite KG file path                      |
| `METRICS_ADDR`        | `:9090`                  | Prometheus HTTP bind address             |
| `INSEE_TOKEN`         | *(empty)*                | INSEE Sirene OAuth2 Bearer token         |
| `INSEE_RATE_PER_MIN`  | `25`                     | Max req/min against INSEE API            |
| `DISCOVERY_ONE_SHOT`  | `false`                  | `true` = run once and exit               |

## Prometheus metrics

| Metric                                         | Type      | Labels                    |
|------------------------------------------------|-----------|---------------------------|
| `cardex_discovery_dealers_total`               | counter   | `family`, `country`       |
| `cardex_discovery_cycle_duration_seconds`      | histogram | `family`, `country`       |
| `cardex_discovery_health_check_status`         | gauge     | `family`                  |
| `cardex_discovery_subtechnique_requests_total` | counter   | `sub_technique`, `status` |

## Sprint roadmap

- **Sprint 1 (current):** KG schema, A.FR.1 INSEE Sirene.
- **Sprint 2:** A.DE.1/2, A.ES.1, A.NL.1, A.BE.1, A.CH.1; Orchestrator + parallel family execution.
- **Sprint 3:** Families B–O; Bayesian confidence formula; DuckDB OLAP layer.
