-- 0003: Verification verdicts — el ledger append-only de la Verificación Adversarial Multi-Vía (VAM)
-- Purpose: "CARDEX no vende mentiras". Todo dato (conteo de discovery, inventario de entidad,
--   cobertura de slice, etc.) que se publique debe tener un veredicto TRAZABLE, producido por una
--   vía y CORROBORADO por >=2 vías ORTOGONALES (distintas de la productora). Esta tabla es la
--   fuente de verdad de esos veredictos; el publish_gate (FASE G) lee de aquí.
-- Regla institucional forzada en DB: un veredicto TRUSTWORTHY EXIGE >=2 verifier_paths (quórum
--   ortogonal). El CHECK lo garantiza: imposible marcar TRUSTWORTHY sin corroboración independiente.
-- Diseño: APPEND-ONLY (cada verificación es un hecho histórico inmutable; no se actualiza).
-- Rollback: ver bloque final comentado.

CREATE TABLE IF NOT EXISTS verification_verdicts (
    id                bigserial PRIMARY KEY,
    subject_type      text NOT NULL,        -- discovery_slice | entity_inventory | platform | dealer_count | ...
    subject_key       text NOT NULL,        -- p.ej. 'FR/75/45.11Z', cdx_code, 'autoscout24.fr'
    claim             text NOT NULL,        -- qué se afirma (p.ej. 'count' , 'coverage', 'inventory_total')
    primary_value     numeric,              -- valor afirmado por la vía productora
    primary_path      text NOT NULL,        -- método/agente que PRODUJO la cifra (la vía a desconfiar)
    verifier_paths    text[] NOT NULL DEFAULT '{}',  -- vías INDEPENDIENTES que corroboraron (ortogonales a primary_path)
    independent_values jsonb NOT NULL DEFAULT '{}'::jsonb,  -- {via: valor} de cada verificador
    divergence        numeric,              -- peor divergencia relativa vs primary entre verificadores usables
    verdict           text NOT NULL,        -- ver CHECK
    evidence          jsonb NOT NULL DEFAULT '{}'::jsonb,   -- muestras/gap_sample/URLs que sostienen el veredicto
    created_at        timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_verdict_enum CHECK (verdict IN
        ('PENDING','TRUSTWORTHY','NEAR','PARTIAL','GAP','REFUTED','UNVERIFIED','ERROR')),
    -- Quórum ortogonal: NADA es TRUSTWORTHY/NEAR sin >=2 vías independientes que lo corroboren.
    CONSTRAINT chk_quorum CHECK (
        verdict NOT IN ('TRUSTWORTHY','NEAR')
        OR coalesce(array_length(verifier_paths, 1), 0) >= 2
    )
);
CREATE INDEX IF NOT EXISTS idx_vv_subject ON verification_verdicts (subject_type, subject_key, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_vv_verdict ON verification_verdicts (verdict);

-- Rollback:
--   DROP INDEX IF EXISTS idx_vv_verdict;
--   DROP INDEX IF EXISTS idx_vv_subject;
--   DROP TABLE IF EXISTS verification_verdicts;
