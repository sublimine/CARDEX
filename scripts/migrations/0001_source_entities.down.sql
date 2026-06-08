-- 0001_source_entities.down.sql
-- Full reverse of 0001_source_entities.up.sql + backfill. Non-destructive to inventory:
-- only drops the added catalog + link columns/view. vehicle_index/vehicles rows are untouched.

BEGIN;

DROP VIEW IF EXISTS entity_inventory;

ALTER TABLE vehicle_index DROP CONSTRAINT IF EXISTS fk_vi_source_entity;
ALTER TABLE vehicles      DROP CONSTRAINT IF EXISTS fk_veh_source_entity;

DROP INDEX IF EXISTS idx_vi_entity;
DROP INDEX IF EXISTS idx_veh_entity;
DROP INDEX IF EXISTS idx_ve_domain_ts;

ALTER TABLE vehicle_index DROP COLUMN IF EXISTS entity_ulid;
ALTER TABLE vehicles      DROP COLUMN IF EXISTS entity_ulid;

DROP TABLE IF EXISTS source_entities;

COMMIT;
