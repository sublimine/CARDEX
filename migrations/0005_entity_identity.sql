-- 0005: Identidad institucional de entidad — cdx_code + crosswalk entity_xref (FASE B del master plan)
-- Purpose: dar a cada entidad (dealer/plataforma) su CÓDIGO ÚNICO E INMUTABLE (CDX-<ISO2>-<8>) y el
--   crosswalk que reconcilia las múltiples representaciones de la MISMA entidad física descubierta por
--   fuentes distintas (discovery_candidates, dealers, source_entities, vehicles) bajo un solo cdx_code.
--   Es la columna vertebral de "código único por dealer" + "API por entidad" + orden geográfico.
--   Generador del código: scrapers/intelligence/cdx_code.py (puro, determinista, probado): identidad
--   estable = dominio > país+registro > país+nombre+ciudad → blake2b(5)→base32 → CDX-<ISO2>-<8 [A-Z2-7]>.
--   Misma entidad física ⇒ mismo código siempre, aunque se redescubra por otra fuente. Aquí NO se genera
--   ni se rellena nada: solo el esquema que lo aloja. El backfill (asignar códigos + poblar xref) es
--   consolidación (FASE E), previa verificación adversarial, fuera de esta migración de esquema.
-- Diseño: ADITIVO + IDEMPOTENTE (IF NOT EXISTS / índice único parcial / constraints guardados). No toca
--   ninguna tabla legacy ni sus datos; dealers sigue VACÍA hoy. Sin FK a dealers a propósito: el crosswalk
--   debe poder existir ANTES de consolidar dealers, y desacoplado evita acoplar el ciclo de vida de ambas.
-- Decisión de diseño (mejora sobre el spec de HANDOFF, que proponía UNIQUE(cdx_code,ref_table,ref_key)):
--   la clave natural correcta es PRIMARY KEY (ref_table, ref_key) — una referencia de origen concreta
--   resuelve a EXACTAMENTE UN cdx_code. El UNIQUE compuesto habría permitido que la misma fila de origen
--   apuntara a dos entidades distintas (bug de identidad). Validado por revisión adversarial DB.
-- Integridad en DB (revisión adversarial 2026-06-10): se fuerzan en el esquema, NO en código, para que
--   ningún backfill de FASE E cuele basura que luego exija un UPDATE masivo (prohibido por doctrina MVCC):
--     * formato del cdx_code (CDX-<2 may>-<8 base32>),
--     * identity_basis ∈ {domain, registry, name_city},
--     * country ∈ los 6 países CARDEX (ES/FR/BE/NL/DE/CH) o NULL si aún no resuelto.
--   Índice de consulta (cdx_code, ref_table) cubre "todos los refs [de tipo X] de una entidad" y subsume
--   el índice sobre cdx_code solo; (country) cubre el slicing geográfico.
-- Rollback: ver bloque final comentado.

-- (a) Código único inmutable en la tabla canónica de entidad consolidada.
ALTER TABLE dealers ADD COLUMN IF NOT EXISTS cdx_code text;

-- Formato del código en DB (idempotente vía guarda en pg_constraint; tabla vacía hoy ⇒ sin validación costosa).
DO $mig$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_dealers_cdx_code_format') THEN
        ALTER TABLE dealers
            ADD CONSTRAINT chk_dealers_cdx_code_format
            CHECK (cdx_code ~ '^CDX-[A-Z]{2}-[A-Z2-7]{8}$');
    END IF;
END
$mig$;

-- Unicidad solo sobre códigos asignados: dealers se puebla en FASE E y muchas filas tendrán cdx_code NULL
-- transitoriamente; el índice único PARCIAL permite múltiples NULL y garantiza unicidad del código asignado.
CREATE UNIQUE INDEX IF NOT EXISTS ux_dealers_cdx_code ON dealers (cdx_code) WHERE cdx_code IS NOT NULL;

-- (b) Crosswalk canónico: cdx_code ↔ cada representación de origen de la misma entidad física.
CREATE TABLE IF NOT EXISTS entity_xref (
    cdx_code       text NOT NULL CHECK (cdx_code ~ '^CDX-[A-Z]{2}-[A-Z2-7]{8}$'),
    ref_table      text NOT NULL,                       -- discovery_candidates | dealers | source_entities | vehicles
    ref_key        text NOT NULL,                       -- identidad en esa tabla (id::text, domain, entity_ulid, url_hash...)
    country        char(2) CHECK (country IN ('ES','FR','BE','NL','DE','CH')),   -- país de la entidad; NULL si aún no resuelto
    identity_basis text   CHECK (identity_basis IN ('domain','registry','name_city')),  -- regla que produjo el código (auditoría/confianza)
    created_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (ref_table, ref_key)                    -- cada ref de origen → exactamente UN cdx_code
);
CREATE INDEX IF NOT EXISTS idx_entity_xref_cdx_ref_table ON entity_xref (cdx_code, ref_table);  -- refs [tipo X] de una entidad
CREATE INDEX IF NOT EXISTS idx_entity_xref_country       ON entity_xref (country);              -- slicing geográfico

-- Rollback:
--   DROP INDEX IF EXISTS idx_entity_xref_country;
--   DROP INDEX IF EXISTS idx_entity_xref_cdx_ref_table;
--   DROP TABLE IF EXISTS entity_xref;
--   DROP INDEX IF EXISTS ux_dealers_cdx_code;
--   ALTER TABLE dealers DROP CONSTRAINT IF EXISTS chk_dealers_cdx_code_format;
--   ALTER TABLE dealers DROP COLUMN IF EXISTS cdx_code;
