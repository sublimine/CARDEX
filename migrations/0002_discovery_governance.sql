-- 0002: Discovery governance — run-ledger + additive tier/geo columns (FASE A del master plan)
-- Purpose: dar GOBIERNO al discovery. (1) ledger append-only de cada barrido del orquestador y
--   de cada (fuente x país) para trazabilidad y reanudación; (2) columnas aditivas en
--   discovery_candidates para la taxonomía de tiers y la jerarquía geográfica (provincia + H3).
-- Diseño: 100% ADITIVO e IDEMPOTENTE (IF NOT EXISTS) — cero riesgo sobre las ~112k filas
--   existentes; no toca ninguna columna ni dato actual. Append-only: las tablas ledger no se
--   actualizan en caliente salvo el cierre del run (finished_at/status).
-- Rollback: ver bloque final comentado (-- Rollback:).

-- ── Run ledger: un registro por invocación del orquestador de discovery ──────────────────
CREATE TABLE IF NOT EXISTS discovery_runs (
    id                bigserial PRIMARY KEY,
    started_at        timestamptz NOT NULL DEFAULT now(),
    finished_at       timestamptz,
    countries         text[]      NOT NULL DEFAULT '{}',
    candidates_written integer    NOT NULL DEFAULT 0,
    status            text        NOT NULL DEFAULT 'running',  -- running | done | error
    notes             text
);

-- ── Per-source-per-country ledger: trazabilidad fina (qué fuente rindió qué, por país) ───
CREATE TABLE IF NOT EXISTS discovery_source_runs (
    id          bigserial PRIMARY KEY,
    run_id      bigint      NOT NULL REFERENCES discovery_runs(id) ON DELETE CASCADE,
    source      text        NOT NULL,
    country     text        NOT NULL,
    seen        integer     NOT NULL DEFAULT 0,
    written     integer     NOT NULL DEFAULT 0,
    ok          boolean     NOT NULL DEFAULT true,
    error       text,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_discovery_source_runs_run ON discovery_source_runs (run_id);
CREATE INDEX IF NOT EXISTS idx_discovery_source_runs_src ON discovery_source_runs (source, country);

-- ── Additive taxonomy/geo columns on discovery_candidates (no backfill aquí; FASE B/C) ───
ALTER TABLE discovery_candidates ADD COLUMN IF NOT EXISTS source_tier smallint;   -- L1-L5 fuente
ALTER TABLE discovery_candidates ADD COLUMN IF NOT EXISTS entity_tier text;        -- taxonomía comercial
ALTER TABLE discovery_candidates ADD COLUMN IF NOT EXISTS province    text;        -- provincia/región (FASE B)
ALTER TABLE discovery_candidates ADD COLUMN IF NOT EXISTS h3_res7     text;        -- celda H3 res7 (dedup/geo)
CREATE INDEX IF NOT EXISTS idx_discovery_candidates_province ON discovery_candidates (country, province);
CREATE INDEX IF NOT EXISTS idx_discovery_candidates_h3 ON discovery_candidates (h3_res7);

-- Rollback:
--   DROP INDEX IF EXISTS idx_discovery_candidates_h3;
--   DROP INDEX IF EXISTS idx_discovery_candidates_province;
--   ALTER TABLE discovery_candidates DROP COLUMN IF EXISTS h3_res7;
--   ALTER TABLE discovery_candidates DROP COLUMN IF EXISTS province;
--   ALTER TABLE discovery_candidates DROP COLUMN IF EXISTS entity_tier;
--   ALTER TABLE discovery_candidates DROP COLUMN IF EXISTS source_tier;
--   DROP TABLE IF EXISTS discovery_source_runs;
--   DROP TABLE IF EXISTS discovery_runs;
