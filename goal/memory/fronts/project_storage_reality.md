---
name: project-storage-reality
description: "CARDEX storage reality — PostgreSQL `vehicles` is the real rich store; CONTEXT_FOR_AI.md is stale on this"
metadata: 
  node_type: memory
  type: project
  originSessionId: 766b74fa-a4f4-4d15-8406-ab68aa1fa804
---

`CONTEXT_FOR_AI.md` (dated 2026-04-15) says "PostgreSQL/Redis NOT implemented, storage is SQLite". This is **stale**. The Python scraper fleet (Strategy B, adopted 2026-05-16 — *after* that doc) writes to **PostgreSQL** via asyncpg. Verified ground truth:

- `scripts/init-pg.sql` defines the rich **`vehicles`** table (make, model, year, fuel_type, mileage_km, co2_gkm, price_raw, currency_raw, **last_price_eur**, source_country, source_url, listing_status, ...) plus a thin `vehicle_index` URL-pointer table.
- `docker-compose.yml` wires real services: `postgres:16` (db/user `cardex`, pass `${POSTGRES_PASSWORD:-<REDACTED-dev-password>}`, :5432), `redis/redis-stack-server` (requirepass, :6379), clickhouse, meilisearch, and an `api` service building `services/api/Dockerfile` on :8080.
- The **Go core pipeline** (discovery/extraction/quality) is separate: it uses **SQLite** `./data/discovery.db` table `vehicle_record` (make_canonical/model_canonical). Three independent vehicle stores exist; not kept in sync by any committed code.

For market/price/EUR work, query PG `vehicles` and prefer `last_price_eur`, else convert CHF.

Existing fiscal code: `innovation/tax_engine` (module `cardex.eu/tax`) computes **VAT only** (margin scheme / intra-EU / EU↔CH, VIES, 6 countries) — no registration tax. `innovation/routes` (`cardex.eu/routes`) has a 30-pair transport cost matrix. The Cross-Border Price Intelligence API (`services/api`, `cardex.eu/api`) added the registration-tax layer (ES IEDMT, NL BPM, FR malus, BE BIV/TMC, CH auto tax). See [[project-services-api]] when it exists.

A PreToolUse hook (`cardex_enforcer.py`, ADR-0006) hard-blocks `UPDATE ... SET` in any `.go` file: use INSERT-new + DELETE-stale, keep mutable runtime state in Redis.
