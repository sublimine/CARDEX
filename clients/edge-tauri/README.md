# CARDEX Edge — Tauri Desktop Client

The dealer-side desktop client for the E12 Edge Push strategy.  Dealers install
this app on the same machine as their DMS and push vehicle inventory directly
to CARDEX via gRPC (priority 1500 — highest trust).

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Rust | ≥ 1.77 | `rustup update stable` |
| Node | ≥ 20 LTS | `nvm install 20` |
| Tauri CLI | 2.x | `cargo install tauri-cli` |
| protoc | any | `brew install protobuf` / `apt install protobuf-compiler` |
| tonic-build | auto | added as `[build-dependencies]` in Cargo.toml |

Platform-specific prerequisites:
- **Linux**: `libwebkit2gtk-4.1-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev`
- **macOS**: Xcode Command Line Tools
- **Windows**: Microsoft C++ Build Tools (Visual Studio 2022)

## Build

```bash
# 1. Compile the proto (happens automatically in build.rs)
#    Requires protoc on PATH.
cargo build   # inside clients/edge-tauri/

# 2. Development mode (hot reload)
cargo tauri dev

# 3. Production bundle
cargo tauri build
# Output: src-tauri/target/release/bundle/
```

If `protoc` is not installed, the app still compiles but gRPC calls will return
an error at runtime.  The proto_gen feature is gated behind a cargo feature flag.

## Quick start (no Rust / for testing the server)

Use the gRPC CLI tool to send a test push:

```bash
# Install grpcurl
go install github.com/fullstorydev/grpcurl/cmd/grpcurl@latest

# Heartbeat
grpcurl -plaintext \
  -d '{"dealer_id": "YOUR_DEALER_ID"}' \
  localhost:50051 cardex.edge.EdgePush/Heartbeat

# PushListings (single batch)
grpcurl -plaintext \
  -d '{"dealer_id":"YOUR_ID","api_key":"YOUR_KEY","timestamp_unix":1745000000,
       "listings":[{"vin":"WVW12345678901234","make":"BMW","model":"320d",
       "year":2022,"price_cents":2500000,"currency":"EUR","mileage_km":45000,
       "fuel_type":"diesel","source_url":"https://autohaus.de/1"}]}' \
  localhost:50051 cardex.edge.EdgePush/PushListings
```

## Dealer onboarding

Register a dealer using the CLI (Go binary, compiled separately):

```bash
# Build
cd extraction
GOWORK=off go build -o ../bin/cardex-dealer ./cmd/cardex-dealer/

# Register
EDGE_DB_PATH=./data/discovery.db \
../bin/cardex-dealer register \
  --name "AutoHaus Berlin" \
  --country DE \
  --vat DE123456789

# Output:
#   dealer_id  : 01JFXYZABCDE1234567
#   api_key    : <64-char hex>  ← shown only once, store securely
```

Provide the `dealer_id` and `api_key` to the dealer for entry in the login screen.

## Environment variables (Edge Push server)

| Variable | Default | Description |
|----------|---------|-------------|
| `EDGE_DB_PATH` | `./data/discovery.db` | Shared SQLite path |
| `EDGE_GRPC_PORT` | `50051` | gRPC listen port |
| `EDGE_TLS_CERT` | — | TLS certificate (required in prod) |
| `EDGE_TLS_KEY` | — | TLS private key (required in prod) |
| `EDGE_INSECURE` | `false` | Disable TLS (dev only) |
| `EDGE_METRICS_ADDR` | `:9102` | Prometheus /metrics endpoint |

## CSV bulk import format

```
vin,make,model,year,price_cents,currency,mileage_km,fuel_type,transmission,color,source_url
WVW12345678901234,BMW,320d,2022,2500000,EUR,45000,diesel,manual,black,https://dealer.de/1
```

All columns required; `image_urls` and `description` are optional (omit or leave empty).

## Auto-update

The Tauri updater checks `https://update.cardex.eu/edge-tauri/{{target}}/{{arch}}/{{current_version}}`
on startup.  Updates are signed with the pubkey in `tauri.conf.json`.
Replace `REPLACE_WITH_TAURI_UPDATE_PUBKEY` with the output of `tauri signer generate`.
