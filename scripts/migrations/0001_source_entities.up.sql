-- 0001_source_entities.up.sql
-- Per-entity inventory encapsulation (CEO: "cada inventario de cada plataforma/dealer
-- encapsulado en una API vendible por separado").
--
-- DESIGN NOTE (reversible, non-destructive):
--   The existing `entities` table is the CUSTOMER/TENANT model (entity_type
--   DEALER/FLEET/INSTITUTION/INDIVIDUAL, vault_dek_id NOT NULL, Stripe/KYC,
--   referenced by 18 commercial tables). Overloading it with scraped platforms
--   (mobile.de) or 49K scraped dealers would break that model.
--   Therefore the SUPPLY-side catalog lives in a SEPARATE table `source_entities`.
--   A source MAY later be linked to a customer `entities` row when it onboards.
--
-- Fully reversible: see 0001_source_entities.down.sql.

BEGIN;

CREATE TABLE IF NOT EXISTS source_entities (
    entity_ulid   TEXT PRIMARY KEY,                 -- deterministic: 'se_'||md5(source_key)
    source_key    TEXT NOT NULL UNIQUE,             -- domain / source_platform natural key
    kind          TEXT NOT NULL CHECK (kind IN ('platform','dealer')),
    domain        TEXT,
    country       CHAR(2),
    defense_tier  TEXT CHECK (defense_tier IS NULL OR defense_tier IN ('T1','T2','T3')),
    waf           TEXT,
    config_ref    TEXT,                             -- path to versioned config (configs/portals|dealers)
    first_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_source_entities_country ON source_entities(country);
CREATE INDEX IF NOT EXISTS idx_source_entities_kind    ON source_entities(kind);
CREATE INDEX IF NOT EXISTS idx_source_entities_tier    ON source_entities(defense_tier);

-- Nullable link columns. FK ON DELETE SET NULL => dropping a source never deletes inventory.
ALTER TABLE vehicle_index ADD COLUMN IF NOT EXISTS entity_ulid TEXT;
ALTER TABLE vehicles      ADD COLUMN IF NOT EXISTS entity_ulid TEXT;

-- Add FKs as NOT VALID first; validated in the backfill once rows are linked
-- (avoids a long full-table validation lock on 436K rows at DDL time).
DO $mig$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_vi_source_entity') THEN
    ALTER TABLE vehicle_index ADD CONSTRAINT fk_vi_source_entity
      FOREIGN KEY (entity_ulid) REFERENCES source_entities(entity_ulid) ON DELETE SET NULL NOT VALID;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_veh_source_entity') THEN
    ALTER TABLE vehicles ADD CONSTRAINT fk_veh_source_entity
      FOREIGN KEY (entity_ulid) REFERENCES source_entities(entity_ulid) ON DELETE SET NULL NOT VALID;
  END IF;
END
$mig$;

CREATE INDEX IF NOT EXISTS idx_vi_entity  ON vehicle_index(entity_ulid);
CREATE INDEX IF NOT EXISTS idx_veh_entity ON vehicles(entity_ulid);

-- Index for per-entity delta lookups (vehicle_events filtered by source_domain).
-- Without it the /entities/{ulid}/delta and fiche delta_24h do a seq scan of ~467K events.
CREATE INDEX IF NOT EXISTS idx_ve_domain_ts ON vehicle_events(source_domain, ts);

-- Unified per-entity inventory VIEW. This is a live PROJECTION (no data copy):
--   - pointer rows from vehicle_index (the 436K live deep-links)
--   - rich rows from vehicles (make/model/price)
CREATE OR REPLACE VIEW entity_inventory AS
  SELECT
    vi.entity_ulid,
    vi.url_original                       AS source_url,
    vi.country::text                      AS country,
    NULLIF(vi.titulo_modelo,'')           AS title,
    NULL::text                            AS make,
    NULL::text                            AS model,
    vi.anio::int                          AS year,
    vi.precio::numeric                    AS price,
    NULLIF(vi.moneda,'')                  AS currency,
    vi.kilometraje::int                   AS mileage_km,
    NULLIF(vi.thumbnail_url,'')           AS thumb_url,
    'active'::text                        AS status,
    vi.last_seen                          AS seen_at,
    'pointer'::text                       AS detail_level
  FROM vehicle_index vi
  WHERE vi.entity_ulid IS NOT NULL
  UNION ALL
  SELECT
    v.entity_ulid,
    v.source_url                          AS source_url,
    v.source_country::text                AS country,
    NULLIF(btrim(concat_ws(' ', v.make, v.model, v.variant)),'') AS title,
    v.make,
    v.model,
    v.year::int                           AS year,
    v.gross_physical_cost_eur::numeric    AS price,
    'EUR'::text                           AS currency,
    v.mileage_km::int                     AS mileage_km,
    NULLIF(v.thumb_url,'')                AS thumb_url,
    COALESCE(v.listing_status,'ACTIVE')   AS status,
    v.last_updated_at                     AS seen_at,
    'rich'::text                          AS detail_level
  FROM vehicles v
  WHERE v.entity_ulid IS NOT NULL
    AND COALESCE(v.listing_status,'ACTIVE') NOT IN ('SOLD','DELISTED');

COMMIT;
