-- 0006: Taxonomia institucional de 2 ejes ortogonales — defensa D0-D3 x naturaleza E-* x CMS (FASE C)
-- Purpose: el plan A->Z pide clasificar cada entidad por DOS ejes independientes (el repo hoy los colapsa
--   en un solo simbolo 'Tier T0-T3' con significados incompatibles en domain_map.py vs inventory_probe.py):
--     * Eje DEFENSA (D0-D3): cuanto cuesta acceder. D0 abierto/SSR limpio · D1 pasivo · D2 challenge activo
--       · D3 behavioral. Es el output de engine/router/classifier.classify_signals.
--     * Eje NATURALEZA (E-*): que es la entidad y como se cierra. E-PLATFORM (portal) · E-FAMILY (dealer
--       sobre CMS conocido = 1 receta cierra N dealers, el multiplicador) · E-INDEP · E-GARAGE · E-SCRAP
--       · E-DMS (inventario embebido de proveedor DMS = 1 conector cierra N dealers).
--     * Descriptor CMS: fingerprint (izmocars|dealer_com|dealerk|wordpress|next_dealer|modix|...) que
--       habilita la receta de familia. dms_provider cuando nature=E-DMS.
--   El despacho del orquestador es funcion de (naturaleza x defensa x valor); un solo eje no lo expresa.
-- Diseño: ADITIVO + IDEMPOTENTE (IF NOT EXISTS / constraints guardados). No toca datos. source_entities
--   esta VACIA (0 filas) -> el cambio de CHECK de defense_tier no requiere backfill; se conservan T1-T3
--   como legacy en transicion (mapean a D2/D3) para no romper a ningun escritor existente.
-- BUG LATENTE CORREGIDO (hallado en el grounding, no estaba en ningun spec): inventory_probe.py:242
--   hace UPDATE discovery_candidates SET inventory_tier/inventory_signals/inventory_probed_at, pero esas
--   columnas NO existian en el esquema vivo -> el clasificador a escala fallaria en runtime. Se declaran
--   aqui (la migracion es la duena del esquema, no un ALTER ad-hoc en codigo). Las clasificaciones a
--   escala (defensa + senales + CMS verdict) viven en discovery_candidates.inventory_signals (jsonb)
--   hasta la promocion a source_entities (consolidacion, FASE E), donde aterriza la taxonomia canonica.
-- Rollback: ver bloque final comentado.

-- (a) source_entities: taxonomia canonica de la entidad de suministro (post-promocion).
ALTER TABLE source_entities ADD COLUMN IF NOT EXISTS nature text
    CHECK (nature IS NULL OR nature IN ('E-PLATFORM','E-FAMILY','E-INDEP','E-GARAGE','E-SCRAP','E-DMS'));
ALTER TABLE source_entities ADD COLUMN IF NOT EXISTS cms text;            -- fingerprint de CMS/plataforma
ALTER TABLE source_entities ADD COLUMN IF NOT EXISTS dms_provider text;   -- cuando nature=E-DMS
CREATE INDEX IF NOT EXISTS idx_se_nature ON source_entities (nature);
CREATE INDEX IF NOT EXISTS idx_se_cms    ON source_entities (cms);
CREATE INDEX IF NOT EXISTS idx_se_dms    ON source_entities (dms_provider) WHERE dms_provider IS NOT NULL;

-- Ampliar defense_tier {T1,T2,T3} -> {D0,D1,D2,D3} (eje defensa). Vacia hoy => sin backfill; T1-T3 se
-- toleran como legacy en transicion. Guardado e idempotente.
DO $mig$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'source_entities_defense_tier_check') THEN
        ALTER TABLE source_entities DROP CONSTRAINT source_entities_defense_tier_check;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_se_defense_tier') THEN
        ALTER TABLE source_entities ADD CONSTRAINT chk_se_defense_tier
            CHECK (defense_tier IS NULL OR defense_tier IN ('D0','D1','D2','D3','T1','T2','T3'));
    END IF;
END
$mig$;

-- (b) discovery_candidates: columnas de clasificacion a escala que inventory_probe.py escribe pero que
--     faltaban en el esquema vivo (bug latente corregido). inventory_signals jsonb = defensa + senales
--     + CMS verdict de la pasada de clasificacion.
ALTER TABLE discovery_candidates ADD COLUMN IF NOT EXISTS inventory_tier text;
ALTER TABLE discovery_candidates ADD COLUMN IF NOT EXISTS inventory_signals jsonb;
ALTER TABLE discovery_candidates ADD COLUMN IF NOT EXISTS inventory_probed_at timestamptz;
CREATE INDEX IF NOT EXISTS idx_dc_inventory_tier ON discovery_candidates (inventory_tier) WHERE inventory_tier IS NOT NULL;

-- Rollback:
--   DROP INDEX IF EXISTS idx_dc_inventory_tier;
--   ALTER TABLE discovery_candidates DROP COLUMN IF EXISTS inventory_probed_at;
--   ALTER TABLE discovery_candidates DROP COLUMN IF EXISTS inventory_signals;
--   ALTER TABLE discovery_candidates DROP COLUMN IF EXISTS inventory_tier;
--   ALTER TABLE source_entities DROP CONSTRAINT IF EXISTS chk_se_defense_tier;
--   ALTER TABLE source_entities ADD CONSTRAINT source_entities_defense_tier_check
--       CHECK (defense_tier IS NULL OR defense_tier IN ('T1','T2','T3'));   -- restaura el CHECK original
--   DROP INDEX IF EXISTS idx_se_dms;
--   DROP INDEX IF EXISTS idx_se_cms;
--   DROP INDEX IF EXISTS idx_se_nature;
--   ALTER TABLE source_entities DROP COLUMN IF EXISTS dms_provider;
--   ALTER TABLE source_entities DROP COLUMN IF EXISTS cms;
--   ALTER TABLE source_entities DROP COLUMN IF EXISTS nature;
