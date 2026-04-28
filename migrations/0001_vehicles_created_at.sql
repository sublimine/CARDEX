-- 0001: Add created_at to vehicles table
-- Purpose: track when a vehicle first appeared in CARDEX (first-seen date).
-- This is the foundation for the proprietary market history ("historial propio").
-- Rollback: ALTER TABLE vehicles DROP COLUMN created_at;

BEGIN;

ALTER TABLE vehicles
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- Backfill: set created_at = last_updated_at for existing rows.
-- last_updated_at is the closest proxy for when the row was created.
UPDATE vehicles
SET created_at = COALESCE(last_updated_at, NOW())
WHERE created_at = NOW();

-- Prevent future inserts from accidentally using NOW() for old data.
-- The pipeline sets created_at explicitly on first insert.
CREATE INDEX IF NOT EXISTS idx_vehicles_created_at ON vehicles (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_vehicles_vin_created ON vehicles (vin, created_at DESC)
    WHERE vin IS NOT NULL;

COMMIT;
