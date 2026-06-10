-- 0007: entity_inventory sin doble servicio pointer/rich (gap FASE E declarado 2026-06-10)
-- Purpose: la view sirve UNION de punteros (vehicle_index) + filas ricas (vehicles). Cuando el
--   seam enriquece un coche ya cageado como puntero, el MISMO vehiculo se servia DOS veces por
--   la API per-entidad (pouw.nl: 1727 punteros + 30 ricas del mismo sitemap = 1757 servidas).
--   El dedup excluye de la rama pointer todo coche que ya se sirve rich para la MISMA entidad
--   y la MISMA URL (normalizacion minima ://www. -> :// porque la canonicalizacion del sitio
--   puede divergir entre el descubrimiento y el source_url persistido; documentado en
--   seam.make_live_purger). La fila RICA gana: es la de mayor detalle.
-- Diseño: CREATE OR REPLACE VIEW (aditivo, sin tocar datos) + indice de expresion en vehicles
--   para que el anti-join escale (parcial: solo filas linked). Idempotente.
-- Rollback: ver bloque final comentado (restaura la view 0006-era sin dedup).

CREATE INDEX IF NOT EXISTS idx_vehicles_entity_srcurl_norm
    ON vehicles ((replace(lower(source_url), '://www.', '://')))
    WHERE entity_ulid IS NOT NULL;

CREATE OR REPLACE VIEW entity_inventory AS
 SELECT vi.entity_ulid,
    vi.url_original AS source_url,
    vi.country::text AS country,
    NULLIF(vi.titulo_modelo, ''::text) AS title,
    NULL::text AS make,
    NULL::text AS model,
    vi.anio::integer AS year,
    vi.precio::numeric AS price,
    NULLIF(vi.moneda, ''::bpchar) AS currency,
    vi.kilometraje AS mileage_km,
    NULLIF(vi.thumbnail_url, ''::text) AS thumb_url,
    'active'::text AS status,
    vi.last_seen AS seen_at,
    'pointer'::text AS detail_level
   FROM vehicle_index vi
  WHERE vi.entity_ulid IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 FROM vehicles v
        WHERE v.entity_ulid = vi.entity_ulid
          AND COALESCE(v.listing_status, 'ACTIVE'::text) <> ALL (ARRAY['SOLD'::text, 'DELISTED'::text])
          AND replace(lower(v.source_url), '://www.', '://')
              = replace(lower(vi.url_original), '://www.', '://'))
 UNION ALL
  SELECT v.entity_ulid,
    v.source_url,
    v.source_country::text AS country,
    NULLIF(btrim(concat_ws(' '::text, v.make, v.model, v.variant)), ''::text) AS title,
    v.make,
    v.model,
    v.year,
    v.gross_physical_cost_eur::numeric AS price,
    'EUR'::text AS currency,
    v.mileage_km,
    NULLIF(v.thumb_url, ''::text) AS thumb_url,
    COALESCE(v.listing_status, 'ACTIVE'::text) AS status,
    v.last_updated_at AS seen_at,
    'rich'::text AS detail_level
   FROM vehicles v
  WHERE v.entity_ulid IS NOT NULL
    AND (COALESCE(v.listing_status, 'ACTIVE'::text) <> ALL (ARRAY['SOLD'::text, 'DELISTED'::text]));

-- Rollback:
--   DROP INDEX IF EXISTS idx_vehicles_entity_srcurl_norm;
--   CREATE OR REPLACE VIEW entity_inventory AS
--    SELECT vi.entity_ulid, vi.url_original AS source_url, vi.country::text AS country,
--           NULLIF(vi.titulo_modelo,'') AS title, NULL::text AS make, NULL::text AS model,
--           vi.anio::integer AS year, vi.precio::numeric AS price,
--           NULLIF(vi.moneda,''::bpchar) AS currency, vi.kilometraje AS mileage_km,
--           NULLIF(vi.thumbnail_url,'') AS thumb_url, 'active'::text AS status,
--           vi.last_seen AS seen_at, 'pointer'::text AS detail_level
--      FROM vehicle_index vi WHERE vi.entity_ulid IS NOT NULL
--    UNION ALL
--    SELECT v.entity_ulid, v.source_url, v.source_country::text,
--           NULLIF(btrim(concat_ws(' ', v.make, v.model, v.variant)),''), v.make, v.model,
--           v.year, v.gross_physical_cost_eur::numeric, 'EUR'::text, v.mileage_km,
--           NULLIF(v.thumb_url,''), COALESCE(v.listing_status,'ACTIVE'), v.last_updated_at, 'rich'::text
--      FROM vehicles v
--     WHERE v.entity_ulid IS NOT NULL
--       AND COALESCE(v.listing_status,'ACTIVE') <> ALL (ARRAY['SOLD','DELISTED']);
