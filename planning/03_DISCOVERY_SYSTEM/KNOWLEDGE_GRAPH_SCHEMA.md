# Knowledge Graph Schema — Dealer Ecosystem

## Identificador
- Documento: KNOWLEDGE_GRAPH_SCHEMA
- Versión: 1.0
- Fecha: 2026-04-14
- Estado: AUTORITATIVO

## Propósito
Esquema relacional del knowledge graph que modela el ecosistema dealer europeo construido por las 15 familias de discovery. Implementación primaria sobre SQLite (OLTP) con índices secundarios en DuckDB (OLAP). El grafo es la primary truth del estado del universo dealer + vehículos indexados.

## Modelo de entidades

### Entidad `dealer_entity`
Representa a un operador B2B único. Clave canónica derivada de cross-validation multi-fuente.

```sql
CREATE TABLE dealer_entity (
  dealer_id TEXT PRIMARY KEY,           -- ULID
  canonical_name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,        -- lowercase, sin diacríticos, sin sufijos legales
  country_code TEXT NOT NULL,           -- DE|FR|ES|BE|NL|CH
  primary_vat TEXT,                     -- primary VAT/UID para dedup cross-family
  legal_form TEXT,                      -- GmbH|SARL|SL|BV|SA|AG|etc.
  founded_year INTEGER,
  status TEXT NOT NULL,                 -- ACTIVE|DORMANT|CLOSED|UNVERIFIED
  operational_score REAL,               -- M.M4 composite score
  confidence_score REAL NOT NULL,       -- R5 — función del número fuentes independientes
  first_discovered_at TIMESTAMP NOT NULL,
  last_confirmed_at TIMESTAMP NOT NULL,
  metadata_json TEXT                    -- flexible blob para campos opcionales
);

CREATE INDEX idx_dealer_country ON dealer_entity(country_code);
CREATE INDEX idx_dealer_status ON dealer_entity(status);
CREATE INDEX idx_dealer_vat ON dealer_entity(primary_vat) WHERE primary_vat IS NOT NULL;
CREATE INDEX idx_dealer_confidence ON dealer_entity(confidence_score);
```

### Entidad `dealer_identifier`
IDs externos (VAT, SIRET, KvK, BCE, Zefix UID, NIF, Handelsregister, etc.) → entity mapping. Un dealer puede tener múltiples.

```sql
CREATE TABLE dealer_identifier (
  identifier_id TEXT PRIMARY KEY,       -- ULID
  dealer_id TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  identifier_type TEXT NOT NULL,        -- VIES_VAT|SIRET|KVK|BCE|ZEFIX_UID|HANDELSREGISTER|etc.
  identifier_value TEXT NOT NULL,
  source_family TEXT NOT NULL,          -- A..O
  validated_at TIMESTAMP,
  valid_status TEXT                     -- VALID|INVALID|UNKNOWN
);

CREATE UNIQUE INDEX idx_identifier_unique ON dealer_identifier(identifier_type, identifier_value);
CREATE INDEX idx_identifier_dealer ON dealer_identifier(dealer_id);
```

### Entidad `dealer_location`
Ubicaciones físicas. Un dealer puede tener N locations (chains multi-site).

```sql
CREATE TABLE dealer_location (
  location_id TEXT PRIMARY KEY,
  dealer_id TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  is_primary BOOLEAN NOT NULL,
  address_line1 TEXT,
  address_line2 TEXT,
  postal_code TEXT,
  city TEXT,
  region TEXT,
  country_code TEXT NOT NULL,
  lat REAL,
  lon REAL,
  h3_index TEXT,                        -- H3 geospatial index
  opening_hours_json TEXT,
  source_families TEXT NOT NULL         -- comma-separated: "A,B,H"
);

CREATE INDEX idx_location_dealer ON dealer_location(dealer_id);
CREATE INDEX idx_location_h3 ON dealer_location(h3_index);
CREATE INDEX idx_location_country_region ON dealer_location(country_code, region);
```

### Entidad `dealer_web_presence`
Sites web del dealer. Un dealer puede tener N.

```sql
CREATE TABLE dealer_web_presence (
  web_id TEXT PRIMARY KEY,
  dealer_id TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  domain TEXT NOT NULL,
  url_root TEXT NOT NULL,
  platform_type TEXT,                   -- CMS detected (cross-Familia D) o NATIVE o DMS_HOSTED
  dms_provider TEXT,                    -- si platform_type=DMS_HOSTED (cross-Familia E)
  extraction_strategy TEXT,             -- E1..E12 assigned
  robots_txt_fetched_at TIMESTAMP,
  sitemap_url TEXT,
  rss_feed_url TEXT,
  last_health_check TIMESTAMP,
  health_status TEXT,                   -- UP|DOWN|DEGRADED
  discovered_by_families TEXT NOT NULL  -- comma-separated
);

CREATE UNIQUE INDEX idx_web_domain ON dealer_web_presence(domain);
CREATE INDEX idx_web_dealer ON dealer_web_presence(dealer_id);
CREATE INDEX idx_web_platform ON dealer_web_presence(platform_type);
```

### Entidad `dealer_social_profile`
Perfiles sociales (cross-Familia L).

```sql
CREATE TABLE dealer_social_profile (
  profile_id TEXT PRIMARY KEY,
  dealer_id TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  platform TEXT NOT NULL,               -- google_maps|facebook|linkedin|instagram|youtube|xing
  profile_url TEXT NOT NULL,
  external_id TEXT,                     -- platform-specific ID (Place-ID, FB Page-ID, etc.)
  rating REAL,
  review_count INTEGER,
  last_activity_detected TIMESTAMP,
  metadata_json TEXT
);

CREATE INDEX idx_social_dealer ON dealer_social_profile(dealer_id);
CREATE INDEX idx_social_platform ON dealer_social_profile(platform);
```

### Entidad `dealer_oem_affiliation`
Relaciones dealer↔marca OEM (cross-Familia H).

```sql
CREATE TABLE dealer_oem_affiliation (
  affiliation_id TEXT PRIMARY KEY,
  dealer_id TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  oem_brand TEXT NOT NULL,              -- VW|BMW|Mercedes|Toyota|etc.
  affiliation_type TEXT NOT NULL,       -- OFFICIAL|SERVICE|PARTS|CERTIFIED_USED
  oem_dealer_id TEXT,                   -- ID asignado por OEM
  first_observed TIMESTAMP,
  last_confirmed TIMESTAMP
);

CREATE INDEX idx_oem_dealer ON dealer_oem_affiliation(dealer_id);
CREATE INDEX idx_oem_brand ON dealer_oem_affiliation(oem_brand);
```

### Entidad `dealer_association_membership`
Membresías en asociaciones sectoriales (cross-Familia G).

```sql
CREATE TABLE dealer_association_membership (
  membership_id TEXT PRIMARY KEY,
  dealer_id TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  association TEXT NOT NULL,            -- ZDK|CNPA|FACONAUTO|BOVAG|FEBIAC|AGVS|TRAXIO|Mobilians|etc.
  member_number TEXT,
  active BOOLEAN,
  first_observed TIMESTAMP,
  last_confirmed TIMESTAMP
);
```

### Entidad `discovery_record`
Auditoría granular: cada (dealer, familia, sub-técnica) que participó en discovery.

```sql
CREATE TABLE discovery_record (
  record_id TEXT PRIMARY KEY,
  dealer_id TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  family TEXT NOT NULL,                 -- A..O
  sub_technique TEXT NOT NULL,          -- A.DE.1, B.1.1, C.1.3, etc.
  source_url TEXT,
  source_record_id TEXT,
  confidence_contributed REAL NOT NULL,
  discovered_at TIMESTAMP NOT NULL,
  last_reconfirmed_at TIMESTAMP
);

CREATE INDEX idx_dr_dealer ON discovery_record(dealer_id);
CREATE INDEX idx_dr_family ON discovery_record(family);
CREATE INDEX idx_dr_composite ON discovery_record(dealer_id, family);
```

### Entidad `vehicle_record`
Índice atómico de vehículo — modelo índice-puntero puro.

```sql
CREATE TABLE vehicle_record (
  vehicle_id TEXT PRIMARY KEY,          -- ULID
  vin TEXT,                             -- canonical VIN (puede ser NULL si fuente no lo expone)
  dealer_id TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  location_id TEXT REFERENCES dealer_location(location_id),

  -- Metadatos vehicle (facts, no copyrightable)
  make_canonical TEXT,
  model_canonical TEXT,
  year INTEGER,
  mileage_km INTEGER,
  fuel_type TEXT,
  transmission TEXT,
  power_kw INTEGER,
  body_type TEXT,
  color TEXT,

  -- Precio
  price_net_eur REAL,
  price_gross_eur REAL,
  currency_original TEXT,
  vat_mode TEXT,                        -- NET|GROSS|UNKNOWN

  -- Punteros (no copias)
  source_url TEXT NOT NULL,
  source_platform TEXT NOT NULL,        -- BCA|MOBILE_DE|AUTOSCOUT24|OWN_WEB|DMS_FEED|etc.
  source_listing_id TEXT,
  image_url TEXT,
  image_url_sha256 TEXT,

  -- Generated content (CARDEX IP)
  title_generated TEXT,                 -- factual short string
  description_generated_ml TEXT,        -- multi-language NLG output

  -- Quality pipeline
  validators_passed INTEGER,            -- 0-20
  validators_failed_json TEXT,          -- JSON array de V01-V20 que fallaron
  confidence_score REAL,
  manual_review_required BOOLEAN,
  manual_review_verdict TEXT,

  -- Lifecycle
  indexed_at TIMESTAMP NOT NULL,
  last_confirmed_at TIMESTAMP NOT NULL,
  ttl_expires_at TIMESTAMP NOT NULL,
  status TEXT NOT NULL,                 -- ACTIVE|EXPIRED|SOLD|WITHDRAWN|PENDING_REVIEW
  fingerprint_sha256 TEXT               -- hash del payload completo para delta detection
);

CREATE UNIQUE INDEX idx_vehicle_vin_dealer ON vehicle_record(vin, dealer_id) WHERE vin IS NOT NULL;
CREATE INDEX idx_vehicle_dealer ON vehicle_record(dealer_id);
CREATE INDEX idx_vehicle_status ON vehicle_record(status);
CREATE INDEX idx_vehicle_ttl ON vehicle_record(ttl_expires_at);
CREATE INDEX idx_vehicle_make_model_year ON vehicle_record(make_canonical, model_canonical, year);
```

### Entidad `vehicle_source_witness`
Cada fuente que vio el mismo VIN. Permite cross-source dedup y convergencia de precio.

```sql
CREATE TABLE vehicle_source_witness (
  witness_id TEXT PRIMARY KEY,
  vehicle_id TEXT NOT NULL REFERENCES vehicle_record(vehicle_id),
  source_platform TEXT NOT NULL,
  source_listing_id TEXT NOT NULL,
  source_url TEXT NOT NULL,
  price_net_eur REAL,
  observed_at TIMESTAMP NOT NULL,
  last_seen_at TIMESTAMP NOT NULL,
  status_at_source TEXT                 -- ACTIVE|SOLD|REMOVED en la fuente original
);

CREATE INDEX idx_witness_vehicle ON vehicle_source_witness(vehicle_id);
CREATE UNIQUE INDEX idx_witness_unique ON vehicle_source_witness(source_platform, source_listing_id);
```

### Entidad `vehicle_equipment`
Equipment list normalizada (V18).

```sql
CREATE TABLE vehicle_equipment (
  vehicle_id TEXT NOT NULL REFERENCES vehicle_record(vehicle_id),
  equipment_code TEXT NOT NULL,         -- vocabulario controlado (DAT/ABV-inspired)
  source_text TEXT,
  PRIMARY KEY (vehicle_id, equipment_code)
);
```

### Entidad `dealer_chain` (opcional, inferred)
Grupos dealer multi-brand/multi-location detectados por análisis cross-familia.

```sql
CREATE TABLE dealer_chain (
  chain_id TEXT PRIMARY KEY,
  chain_name TEXT,
  inference_method TEXT,                -- WHOIS_COMMON_REGISTRANT|ASN_CLUSTER|LEGAL_PARENT|etc.
  confidence REAL NOT NULL
);

CREATE TABLE dealer_chain_membership (
  chain_id TEXT NOT NULL REFERENCES dealer_chain(chain_id),
  dealer_id TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  PRIMARY KEY (chain_id, dealer_id)
);
```

## Vistas OLAP (DuckDB sobre parquet)

### `v_coverage_by_country`
Coverage_Score por país y fecha. Input para dashboards de salud.

### `v_discovery_by_family`
Stats por familia: total descubiertos, únicos, shared, false positive rate.

### `v_vehicle_cross_source`
Vehículos cross-source: VINs indexados por N>1 fuentes, análisis de convergencia.

### `v_dealer_confidence_distribution`
Distribución de confidence_score para flagging de outliers.

## Invariantes de integridad

1. Cada `dealer_entity` debe tener al menos una entrada en `discovery_record` (R5 multi-source enforcement si `confidence_score > threshold`).
2. `vehicle_record.status = ACTIVE` implica `ttl_expires_at > NOW()`.
3. `dealer_identifier` garantiza unicidad por (type, value): un VAT → un dealer, sin excepción.
4. `vehicle_source_witness` unique por (platform, listing_id): sin doble-indexación accidental.

## Migración y versionado

Schema versionado en `schema_version` table. Migraciones sequential en `migrations/` con rollback documentado. Nunca drop columns, siempre add + deprecate + backfill + remove en releases separados.
