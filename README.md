# CARDEX

Pan-European used-car intelligence index. The mission: discover **every platform and
every dealer with a website** across **ES, FR, DE, NL, BE, CH**, mirror their **live**
inventory (every listing added and removed, continuously), and encapsulate it behind
**per-entity APIs** — individually manageable and sellable.

The thesis is the ~30% long-tail: dealers with a website and a handful of relevant
cars who never publish on the big platforms. Tier-1 giants are covered too, but the
reason to exist is covering 100% of the terrain.

## System reality — two layers, do not confuse them

### LIVE — Python harvest fleet (the production path)

| Component | What it is |
|---|---|
| `scrapers/` | Python scraper fleet: portal + dealer scrapers, sitemap/listing indexers, coordinator, anti-OOM supervisor, enrichment seam (`enrich_worker` → `rich_consumer`), fingerprint engines |
| PostgreSQL 16 (Docker `cardex-pg`) | System of record. **INSERT-new + DELETE-stale only** — never UPDATE non-mutated rows (MVCC doctrine). Schema: `migrations/0001`–`0007` |
| Redis (Streams) | **Transport only.** Holding inventory state in Redis is prohibited |
| `services/entity_api/` | FastAPI (`127.0.0.1:8088`) — per-entity live inventory, SEEN/GONE delta, alerts. Every platform and dealer is a `source_entity` exposing its own endpoint |
| `services/api/` | Go REST API (`cardex.eu/api`) — price intelligence; runs on demand |
| `dashboard/` | Local control panel; live numbers straight from PG, scheduled refresh |
| Ollama `qwen2.5:3b` (`127.0.0.1:11434`) | Fuzzy-decision layer (classification/normalization), fail-open |
| `scrapers/engine.db` | SQLite engine state — stays SQLite **by design**; do not migrate it to PG |

### DORMANT — Go scaffold (compiles, produces nothing today)

`discovery/`, `extraction/`, `quality/`, `frontend/terminal/`, `innovation/`,
`internal/shared/`, `workspace/`, `tests/e2e/` — the original Go engine
(15 discovery families, 13 extraction strategies, 20 quality validators, terminal
buyer CLI, CRM workspace). It builds and tests with `GOWORK=off`, writes to its own
SQLite (`discovery.db`), and is governed by the master plan. It is **not** the
production path. Do not "reactivate" it assuming it is prod.

### Removed

Earlier-era components (`gateway/`, `alpha/`, `forensics/`, `vision/`, `corporate/`,
`b2b-dashboard/`, the `services/pipeline` stub, …) were purged with git history
preserved. See [`docs/GRAVEYARD.md`](docs/GRAVEYARD.md) and `git log`.

## Truth hierarchy

1. **Code in `main`** — always wins over any document.
2. [`docs/master-plan/`](docs/master-plan/) — `MASTER_PLAN_AZ.md` (subsystems S1–S7,
   phases A→Z with gates) + `HANDOFF.md`.
3. Sealed reports (root `*_REPORT.md`, `docs/audits/`) — historical records of closed
   fronts; they describe their moment, not the present.

`SPEC.md` is the original vision document — superseded, kept for the record.
Live operational state lives in the operator's command post, outside this repo.

## Quick start

Prerequisites: Python 3.11+, Docker. Go 1.26+ only for the dormant scaffold.

```bash
# Infrastructure (PostgreSQL 16 + Redis Streams)
docker compose up -d postgres redis
# NOTE: docker-compose.yml still carries legacy service definitions
# (pipeline, meili-sync, gateway, …) that are NOT buildable — pending pruning.

# Python fleet test suite (1813 tests)
GOWORK=off python -m pytest scrapers/ -q

# Per-entity inventory API
python -m uvicorn services.entity_api.app:app --host 127.0.0.1 --port 8088

# Dormant Go scaffold (each module independent)
cd discovery && GOWORK=off go test ./...
```

## Scraping policy — Strategy B (approved 2026-05-16)

- **Approved stack only:** `curl_cffi>=0.15.1` (TLS impersonation at **session**
  level — same JA3 from page 1 to N, never per-request), `camoufox[geoip]`,
  Playwright (strategy E07). Impersonation always targets a **current** Chrome;
  TLS fingerprints rot in ~6 weeks and stale ones are themselves a bot signal.
- **Two UA layers by design:** Go modules identify as
  `CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)`; the Python fleet's
  UA is managed by the fingerprint engine (a literal UA string would contradict the
  TLS fingerprint).
- **Source survival:** jittered rate limits (~1.2s/page), per-domain budgets,
  exponential backoff on 429/503; robots.txt checker wired in the Go crawling layer.
- **Blocked patterns:** playwright-stealth, undetected-chromedriver, fake-useragent,
  scrapingbee/scraperapi/brightdata. Enforcement definition:
  [`.forgejo/workflows/illegal-pattern-scan.yml`](.forgejo/workflows/illegal-pattern-scan.yml)
  (Forgejo CI definition; not wired to GitHub Actions).

## Build rules

1. **Never compile `.exe`** on the Windows host (Application Control):
   `go run ./cmd/<module>/`.
2. **`GOWORK=off`** for every Go module build/test — modules stay independent.
3. **PG doctrine:** INSERT new + DELETE stale; never UPDATE non-mutated rows.
4. **Redis = Streams transport only;** no inventory state.
5. Geo + identity are institutional: country → province → city hierarchy
   (`migrations/0004`) and immutable `cdx_code` per entity (`migrations/0005`,
   generator `scrapers/intelligence/cdx_code.py`).

## Repository layout (top level)

```
scrapers/        LIVE Python fleet (engines, portals, discovery, intelligence, llm)
services/        entity_api (FastAPI, LIVE) · api (Go price intelligence)
configs/         Versioned extraction recipes: portals/ · dealers/ · families/
migrations/      PostgreSQL schema 0001–0007
dashboard/       Local live control panel
scripts/         Harnesses (giant/dealer scraping, sealers, verifiers, scheduler)
supervisor/      Anti-OOM process supervisor
recipes/ reports/ state/  Working evidence of the harvest fronts
dealers/         Institutional dealer records (country/province/city/CDX-code)
discovery/ extraction/ quality/  DORMANT Go engine
frontend/ workspace/ innovation/ internal/  DORMANT Go scaffold + R&D
docs/            Master plan, ADRs, audits, research, GRAVEYARD
deploy/ monitoring/  VPS + observability infra (not currently deployed)
.agents/ workflows/ goal/  Orchestration governance & institutional memory
```

## Documentation index

| Document | Purpose |
|----------|---------|
| [`docs/master-plan/MASTER_PLAN_AZ.md`](docs/master-plan/MASTER_PLAN_AZ.md) | Governing plan (phases, gates) |
| [`docs/master-plan/HANDOFF.md`](docs/master-plan/HANDOFF.md) | Operational handoff |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | System architecture |
| [`STATUS.md`](STATUS.md) | Verified system snapshot |
| [`SECURITY.md`](SECURITY.md) | Security & crawling policy |
| [`docs/GRAVEYARD.md`](docs/GRAVEYARD.md) | What was removed, and why |
| [`docs/SCRAPING_ENGINE.md`](docs/SCRAPING_ENGINE.md) | Fleet internals |
| [`CHANGELOG.md`](CHANGELOG.md) | Implementation history |
