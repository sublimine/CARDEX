# Contributing

## Module boundaries

Each of the three core modules (`discovery/`, `extraction/`, `quality/`) is independently deployable. Keep them that way:

- Do NOT add cross-module imports.
- Do NOT rely on `go.work` for production builds. Always use `GOWORK=off`.
- Shared code goes in `internal/shared/` (module: `github.com/cardex/shared`).

## Adding a new discovery family

1. Create `discovery/internal/familia/familia_{X}/familia_{X}.go` implementing the `Familia` interface.
2. Add `NewFamilia{X}()` constructor with injectable `*http.Client`.
3. Write at least 4 tests in `familia_{X}_test.go` using `httptest.NewServer`.
4. Register in `discovery/cmd/discovery-service/main.go` with a `DISCOVERY_SKIP_FAMILIA_{X}` guard.
5. Add `SkipFamilia{X}` field to `discovery/internal/config/config.go`.
6. Document in `planning/03_DISCOVERY_SYSTEM/families/`.

## Adding a new extraction strategy

Follow the same pattern as families but in `extraction/internal/extractor/e{NN}_{name}/`.

## Adding a new quality validator

1. Create `quality/internal/validator/v{NN}_{name}/v{NN}.go` implementing the `Validator` interface:
   ```go
   type Validator interface {
       ID() string
       Severity() pipeline.Severity
       Validate(ctx context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error)
   }
   ```
2. Write at least 4 tests. Use `httptest.NewServer` for validators that make HTTP calls.
3. Register in `quality/cmd/quality-service/main.go` with a `QUALITY_SKIP_V{NN}` guard.
4. V20 composite scorer must always be registered LAST (it reads results of all other validators).

## Code style

- Run `go vet ./...` and `golangci-lint run` before committing.
- No `panic()` in library code — return errors.
- Graceful degradation: if an external API call fails, return a WARNING not a fatal error.
- All HTTP clients must use `CardexBot/1.0` UA. CI blocks any other UA.

## Pre-commit checks

The repo uses gitleaks for secret scanning:

```bash
# Install pre-commit
pip install pre-commit
pre-commit install

# Run manually
pre-commit run --all-files
```

The Forgejo CI also runs `illegal-pattern-scan.yml` which blocks:
- Browser UA strings (Mozilla, Chrome, Safari, Googlebot)
- `curl_cffi`, `playwright-stealth`, proxy pool patterns
- Hardcoded IP addresses in source files

## Commit format

```
type(scope): short description

Where type is: feat, fix, refactor, docs, test, ci, cleanup
Where scope is: P{phase}-sprint{N}, or module name (discovery, extraction, quality, deploy)
```

Examples:
- `feat(P2-sprint5): Familia F — mobile.de + La Centrale Pro`
- `fix(quality): V07 price range edge case for CH dealers`
- `docs: update CONTEXT_FOR_AI with V20 composite decision logic`

## Innovation services (Python)

Services in `innovation/` follow these conventions:
- Each service has its own `requirements.txt` and `Dockerfile` (Python 3.11-slim, CPU-only)
- Tests use `pytest` with zero network/GPU dependencies (mocked models, `httptest`-style fixtures)
- Run with `make {service}-setup / {service}-test` (see `make help` for all targets)
- Flask/FastAPI servers expose `/health` and Prometheus `/metrics` endpoints

## gRPC / protobuf

The edge push contract lives in `extraction/api/proto/edge_push.proto`. Regenerate Go bindings:
```bash
make proto  # requires protoc + protoc-gen-go + protoc-gen-go-grpc
```
Hand-written wire-compatible Go types in `extraction/api/edgepb/` are the source of truth until proto codegen is available in CI.

## Tauri (Rust) client

The dealer edge-push desktop client lives in `clients/edge-tauri/`. It is a standard Tauri 1.x app:
```bash
cd clients/edge-tauri
npm install
npm run tauri dev
```
The Rust backend calls the gRPC edge server on `:50051`. Keep the Rust side free of business logic — all decisions belong in the server.

## Secrets

- Never commit `.env`, `*.key`, `*.pem`, `*.age`, credentials of any kind.
- The `deploy/secrets/` directory is gitignored. See `deploy/secrets/README.md`.
- Generate secrets locally: `./deploy/scripts/secrets-generate.sh`.
