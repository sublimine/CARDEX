# CARDEX — STATUS

<!-- Verified snapshot. Volatile by nature: trust the code and the live DB over this file. -->
<!-- Snapshot 2026-06-12 — every claim below was verified against the repo, the running -->
<!-- containers and the process table on that date. Previous snapshot (2026-04-27) is -->
<!-- preserved in git history. -->

## System state (verified 2026-06-12)

- **Harvest is ACTIVE.** The Python fleet is sealing platform giants (AS24 per-country)
  and dealer families; `configs/dealers/` receives new recipes continuously.
- **PostgreSQL 16** (`cardex-pg`, Docker): up, healthy — system of record.
- **Redis** (`cardex-redis-dev`, redis-stack 7.4): up — Streams transport.
- **entity_api** (FastAPI `127.0.0.1:8088`): running (uvicorn) from the main worktree.
- **Anti-OOM supervisor**: running — currently from the `cardex-stealth` worktree
  (see Debt #1).
- **Go scaffold** (`discovery/`, `extraction/`, `quality/`, …): dormant, compiles,
  produces nothing. Not the production path.
- **Python suite**: 1813 passed (54s) on 2026-06-12.

## Legacy bug ledger — resolution (was: snapshot 2026-04-27)

| ID | Verdict 2026-06-12 |
|---|---|
| BUG-001 (`e2e/go.mod` ambiguous `../alpha` replace) | **RESOLVED** — `tests/e2e/go.mod` now requires only `discovery`/`extraction`/`quality`; no `alpha` replace exists |
| BUG-002 (unused `fmt` import in `services/pipeline`) | **VOID** — `services/pipeline` deleted (dead stub: no go.mod, imports to non-existent pkgs); history preserved |
| BUG-003 (silent OEM payload drop in Go pipeline) | **VOID** — that Go pipeline never ran and is deleted; the live ingestion path is the Python fleet |
| BUG-004 ("Reaper" hangs) | **VOID** — component never existed as code; purge duties live in the fleet's slice-then-purge harnesses |

## Known debt (verified, prioritized)

1. **Supervisor runs from the `cardex-stealth` worktree with 9 uncommitted modified
   files** (`scrapers/discovery/domain_resolution/*.py`, `supervisor/*.py`). Production
   behavior is ahead of `main`. Owner front must commit/merge that delta, then retire
   the worktree.
2. **~900 untracked harvest artifacts in main** (`configs/dealers/*.json`, `recipes/`,
   `reports/`, `logs/`) — live front working set, pending commit by the harvest front
   when sealed.
3. **`docker-compose.yml` defines non-buildable legacy services** (`pipeline`,
   `meili-sync`, `gateway`, `frontier`, `census`, `thumbgen`, `scheduler`,
   `search-indexer` — their Dockerfiles/sources do not exist). Only `postgres`/`redis`
   (+ observability) are real. Pending surgical prune.
4. **`docs/master-plan/HANDOFF.md` §8 is stale** — it instructs writing
   `migrations/0005`; migrations 0005–0007 are already applied.

## Operating constraints (in force)

- **Windows + Application Control**: never compile `.exe`. Run with `go run ./cmd/<module>/`.
- **Go modules**: build/test with `GOWORK=off`, always.
- **PG MVCC doctrine**: INSERT new + DELETE stale only. UPDATE of non-mutated rows is prohibited.
- **Redis**: Streams transport only. Inventory state in Redis is prohibited.
- **TLS fingerprint**: session-level impersonation, same JA3 page 1→N, always a
  current Chrome build (stale fingerprints are a bot signal).
- **Verification = VAM**: a number is TRUSTWORTHY only with ≥2 orthogonal
  derivations; content beats count.

## External dependencies

- PostgreSQL 16 + Redis Streams via Docker.
- Ollama `qwen2.5:3b` at `127.0.0.1:11434` — fuzzy micro-decisions, fail-open
  (`OLLAMA_URL` / `OLLAMA_MODEL`, see `scrapers/llm/ollama_client.py`).
- MeiliSearch: optional search mirror (`scrapers/discovery/meili_bridge.py`);
  container currently stopped.

## Where the live log lives

Day-to-day operational state (what is sealing right now, verified counts, next
moves) is maintained in the operator's command post outside this repo, and lands
here as sealed reports + commits. This file is a snapshot, not the diary.
