# CARDEX

Pan-European B2B vehicle arbitrage platform. Bare-metal, event-driven, legally compliant.

## Architecture

```
B2B Webhooks ──→ Gateway (Go) ──→ stream:ingestion_raw
Edge Fleets  ──→              ──→     │
                                      ▼
                               Pipeline (Go) ──→ stream:db_write
                               Bloom + H3 + FX       │
                                                      ▼
                                               Forensics (Go) ──→ stream:market_ready
                                               Tax + OCR + VIES       │
                                                                      ▼
                                                               Alpha Engine (Go)
                                                               NLC + Quotes + SDI + SSE
                                                                      │
                                                         ┌────────────┴────────────┐
                                                         ▼                         ▼
                                                  B2B Terminal              Legal Hub (Go)
                                                  (Rust WASM)              CARFAX + IDEAUTO
```

## Quick Start

```bash
# Start development environment
make dev

# Verify all services
make integration

# Build all Go services
make build

# Run tests
make test
```

## Project Structure

```
.cursorrules          ← Cursor AI development rules (READ FIRST)
SPEC.md               ← Full 2,840-line canonical specification
.cursor/prompts/      ← Phase-specific implementation guides for Cursor
scripts/              ← SQL and shell init scripts
gateway/              ← Phase 3: B2B Acquisition Gateway (Go)
pipeline/             ← Phase 4: HFT Pipeline (Go)
forensics/            ← Phase 5: Tax Classification (Go)
alpha/                ← Phase 6: Financial Engine (Go)
legal/                ← Phase 7: Legal Hub (Go)
ai/                   ← Phase 2: Sovereign AI Worker (Python)
terminal/             ← Phase 8: B2B Terminal (Rust WASM)
edge/                 ← Phase 9: Edge DMS Client (Rust Tauri)
monitoring/           ← Prometheus + Grafana configs
docker-compose.yml    ← Dev environment
Makefile              ← Build orchestration
```

## Development with Cursor

1. Open this project in Cursor
2. Cursor will automatically load `.cursorrules` as its system prompt
3. When working on a specific phase, tell Cursor to read `.cursor/prompts/phase-NN-*.md`
4. For architectural questions, reference `SPEC.md`

### Phase execution order
Build each phase sequentially. Each depends on the previous.

| Phase | Module | Status |
|-------|--------|--------|
| 0-1 | `scripts/init-*.sql` | ✅ DDL ready |
| 3 | `gateway/` | 🔨 Stub + canonical patterns |
| 4 | `pipeline/` | 📋 Stub |
| 5 | `forensics/` | 📋 Stub |
| 2 | `ai/` | 🔨 Worker + GBNF grammar |
| 6 | `alpha/` | 📋 Stub |
| 7 | `legal/` | 📋 Stub |
| 8 | `terminal/` | 📋 Stub |
| 9 | `edge/` | 📋 Stub |

## Non-Negotiable Rules

1. **Fail-closed**: Unknown state → block, never pass silently
2. **Zero cloud**: All compute on Hetzner bare-metal
3. **Zero PII in OLAP**: ClickHouse never receives personal data
4. **No scraping**: All data from licensed B2B feeds or EU Data Act delegation
5. **HMAC everything**: Every quote, every webhook, every signature verified
