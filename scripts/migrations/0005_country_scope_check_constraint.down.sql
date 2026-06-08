-- 0005_country_scope_check_constraint.down.sql
-- Reverse of 0005: drop the CHECK constraints + set triggers back to origin-default ENABLE.
-- Leaves the restored strict function in place (it is the correct version). Non-destructive to data.
BEGIN;
ALTER TABLE discovery_candidates DROP CONSTRAINT IF EXISTS chk_country_scope;
ALTER TABLE source_entities      DROP CONSTRAINT IF EXISTS chk_country_scope;
ALTER TABLE vehicle_index        DROP CONSTRAINT IF EXISTS chk_country_scope;
ALTER TABLE discovery_candidates ENABLE TRIGGER trg_scope_guard;
ALTER TABLE source_entities      ENABLE TRIGGER trg_scope_guard;
ALTER TABLE vehicle_index        ENABLE TRIGGER trg_scope_guard;
COMMIT;
