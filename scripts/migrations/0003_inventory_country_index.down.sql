-- 0003_inventory_country_index.down.sql
BEGIN;
DROP INDEX IF EXISTS idx_vi_country_url;
COMMIT;
