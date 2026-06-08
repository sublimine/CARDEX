-- 0003_inventory_country_index.up.sql
-- Speeds the global /v1/inventory?country=XX endpoint. The entity_inventory view casts
-- vehicle_index.country::text for the UNION, so a plain CHAR(2) index is not used by the
-- `country = $1` predicate; this expression index matches the cast and the ORDER BY url.
BEGIN;
CREATE INDEX IF NOT EXISTS idx_vi_country_url ON vehicle_index ((country::text), url_original);
COMMIT;
ANALYZE vehicle_index;
