-- 0004_country_scope_guard.down.sql
-- Reverse of 0004_country_scope_guard.up.sql. Drops the scope-guard triggers + function.
-- Non-destructive to data (only removes the enforcement).
BEGIN;
DROP TRIGGER IF EXISTS trg_scope_guard ON discovery_candidates;
DROP TRIGGER IF EXISTS trg_scope_guard ON source_entities;
DROP TRIGGER IF EXISTS trg_scope_guard ON vehicle_index;
DROP FUNCTION IF EXISTS enforce_country_scope();
COMMIT;
