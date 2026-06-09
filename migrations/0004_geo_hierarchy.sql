-- 0004: Jerarquía geográfica institucional país→región/provincia→ciudad (FASE B del master plan)
-- Purpose: estructura geo canónica para que cada entidad se ubique país→provincia→ciudad (requisito
--   institucional del fundador). geo_country poblado con los 6 países. geo_city derivado en primer pase
--   de los datos reales de discovery_candidates (20.661 (country,city) distintos hoy); geo_region queda
--   como estructura a enriquecer luego con NUTS/LAU (no se bloquea aquí en el dump).
-- Diseño: ADITIVO + IDEMPOTENTE (IF NOT EXISTS / ON CONFLICT DO NOTHING). No toca ninguna tabla legacy.
-- Rollback: ver bloque final comentado.

CREATE TABLE IF NOT EXISTS geo_country (
    iso2  char(2) PRIMARY KEY,
    name  text NOT NULL
);
INSERT INTO geo_country (iso2, name) VALUES
    ('ES','España'), ('FR','France'), ('BE','Belgique/België'),
    ('NL','Nederland'), ('DE','Deutschland'), ('CH','Schweiz/Suisse')
ON CONFLICT (iso2) DO NOTHING;

CREATE TABLE IF NOT EXISTS geo_region (
    id       bigserial PRIMARY KEY,
    country  char(2) NOT NULL REFERENCES geo_country(iso2),
    code     text,                 -- NUTS / código provincial (enriquecer luego)
    name     text NOT NULL,
    UNIQUE (country, name)
);

CREATE TABLE IF NOT EXISTS geo_city (
    id        bigserial PRIMARY KEY,
    country   char(2) NOT NULL REFERENCES geo_country(iso2),
    region_id bigint REFERENCES geo_region(id),   -- nullable hasta enriquecer regiones
    name      text NOT NULL,
    postcode  text,
    lat       double precision,
    lng       double precision,
    UNIQUE (country, name)
);
CREATE INDEX IF NOT EXISTS idx_geo_city_country ON geo_city (country);
CREATE INDEX IF NOT EXISTS idx_geo_region_country ON geo_region (country);

-- Primer pase: derivar geo_city de los datos reales (ON CONFLICT DO NOTHING = idempotente).
-- Solo países conocidos (FK), ciudad no vacía. Toma un postcode/lat/lng representativo por (país,ciudad).
INSERT INTO geo_city (country, name, postcode, lat, lng)
SELECT DISTINCT ON (upper(country), city)
       upper(country)::char(2), city, postcode, lat, lng
FROM discovery_candidates
WHERE city IS NOT NULL AND city <> ''
  AND upper(country) IN ('ES','FR','BE','NL','DE','CH')
ORDER BY upper(country), city, (postcode IS NULL), (lat IS NULL)
ON CONFLICT (country, name) DO NOTHING;

-- Rollback:
--   DROP INDEX IF EXISTS idx_geo_region_country;
--   DROP INDEX IF EXISTS idx_geo_city_country;
--   DROP TABLE IF EXISTS geo_city;
--   DROP TABLE IF EXISTS geo_region;
--   DROP TABLE IF EXISTS geo_country;
