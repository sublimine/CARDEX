# CARDEX Entity Inventory API

Per-entity inventory encapsulation: **every platform and every dealer is a `source_entity`
that exposes its OWN live inventory endpoint, sellable in isolation**, plus a global index.

This is the supply-side counterpart to the customer/tenant `entities` table. It does **not**
touch that table (see migration design note); it adds a separate catalog `source_entities`.

## Why a separate table (not `entities`)
`entities` is the **customer/tenant** model (`entity_type` DEALER/FLEET/INSTITUTION/INDIVIDUAL,
`vault_dek_id NOT NULL`, Stripe/KYC, referenced by 18 commercial tables). A scraped platform
(`mobile.de`) or a scraped dealer is **not** a CARDEX customer. Overloading `entities` would
break the commercial model and violate its constraints. So the inventory catalog lives in
`source_entities`, and a source MAY later link to a customer `entities` row on onboarding.

## Schema (migration `scripts/migrations/0001_source_entities.*.sql`)
- `source_entities(entity_ulid PK, source_key UNIQUE, kind, domain, country, defense_tier, waf, config_ref)`
  - `entity_ulid` is deterministic: `'se_' || md5(source_key)` (idempotent backfill).
  - `kind ∈ {platform, dealer}`; `defense_tier ∈ {T1,T2,T3}`.
- `vehicle_index.entity_ulid` and `vehicles.entity_ulid` — nullable FK `ON DELETE SET NULL`
  (dropping a source never deletes inventory).
- `entity_inventory` — a **VIEW** (no data copy) unifying pointer rows (vehicle_index) and
  rich rows (vehicles) under one shape with a `detail_level` field.

Apply / roll back:
```bash
docker exec -i cardex-pg psql -U cardex -d cardex -v ON_ERROR_STOP=1 < scripts/migrations/0001_source_entities.up.sql
docker exec -i cardex-pg psql -U cardex -d cardex -v ON_ERROR_STOP=1 < scripts/migrations/0001_source_entities.backfill.sql
# rollback (non-destructive to inventory):
docker exec -i cardex-pg psql -U cardex -d cardex -v ON_ERROR_STOP=1 < scripts/migrations/0001_source_entities.down.sql
```

## Run
```bash
DATABASE_URL=postgresql://cardex:cardex_dev_only@localhost:5432/cardex \
  python -m uvicorn services.entity_api.app:app \
  --app-dir <repo-root> --host 127.0.0.1 --port 8088
```
RAM-light: asyncpg pool `max_size=4`; safe on the constrained host (~780 MB free).

## Endpoints (`/v1`)
| Method · Path | Returns |
|---|---|
| `GET /v1/health` | liveness + entity count |
| `GET /v1/entities?country=&kind=&tier=&limit=&cursor=` | catalog with live `inventory_count` |
| `GET /v1/entities/{ulid}` | entity fiche: metadata + `inventory_count` + `delta_24h` |
| `GET /v1/entities/{ulid}/inventory?limit=&cursor=` | **the sellable live inventory of ONE entity** |
| `GET /v1/entities/{ulid}/delta?since=&limit=` | altas/bajas (SEEN/GONE) of one entity |
| `GET /v1/inventory?country=&make=&limit=&cursor=` | global platform index across all entities |

Pagination is keyset (cursor = last `source_url` / `source_key`); no OFFSET scans.

## "Sellable per entity" — how
Each entity is a self-contained product:
1. **Isolated endpoint** — `/v1/entities/{ulid}/inventory` returns ONLY that platform/dealer's
   live cars. A buyer of "mobile.de inventory" or "dealer X inventory" hits one URL; nothing
   else leaks in.
2. **Its own config** — `source_entities.config_ref` points to the versioned recipe
   (`configs/portals/<domain>.json` or `configs/dealers/<domain>.json`) that produced it. The
   config is the entity's extraction contract: what strategy works, its drift baseline, version.
3. **Its own defense profile** — `defense_tier` + `waf` describe how the entity is harvested
   (T1 Camoufox vs T2 curl_cffi), so the product carries its own SLA/cost characteristics.
4. **Its own freshness** — `delta_24h` and `/delta` expose how live the inventory is, per entity.

The **global index** (`/v1/inventory`) is the aggregate product; the per-entity endpoints are
the unbundled ones.

## How it stays updated (hook to the delta — no rebuild)
The API is a **live view**; it never holds a copy. Freshness comes from the existing pipeline:
- The indexer (`scrapers/common/indexer.py`, `StreamingDeltaSink`) writes `vehicle_index`
  (+ `vehicle_events` SEEN/GONE) on every harvest cycle. New `entity_ulid` is set automatically
  by re-running the backfill's idempotent link step, or — preferred — by having the indexer set
  `entity_ulid = 'se_'||md5(source_domain)` at insert time (one-line addition to `insert_batch`).
- Because `entity_ulid` is deterministic from `source_key`, **any** new listing for an existing
  entity links with zero lookups; a brand-new source auto-creates its `source_entities` row via
  the same `ON CONFLICT DO NOTHING` insert.
- The seam (A6/A7) upserts `vehicles`; those rows carry `entity_ulid` the same way.
- Therefore `/entities/{ulid}/inventory` reflects the delta within one harvest cycle, and
  `/delta` surfaces the exact SEEN/GONE events — the "altas/bajas" the blueprint's always-on
  delta (BLUEPRINT §5) will drive to seconds-latency.

**Wiring TODO (one line, out of scope here):** add to `indexer.insert_batch`
`entity_ulid := 'se_'||md5(source_domain)` so new pointers self-link without a backfill pass.
