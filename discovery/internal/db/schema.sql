-- Knowledge Graph Schema — Dealer Ecosystem
-- Version: 1.0  State: AUTHORITATIVE
-- SQLite WAL mode. ULID primary keys. H3 geo-index (Sprint 1 stub).

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ── Schema versioning ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_version (
  version     INTEGER NOT NULL,
  applied_at  TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  description TEXT
);

-- ── Dealer entity ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dealer_entity (
  dealer_id            TEXT PRIMARY KEY,
  canonical_name       TEXT NOT NULL,
  normalized_name      TEXT NOT NULL,
  country_code         TEXT NOT NULL,
  primary_vat          TEXT,
  legal_form           TEXT,
  founded_year         INTEGER,
  status               TEXT NOT NULL DEFAULT 'UNVERIFIED',
  operational_score    REAL,
  confidence_score     REAL NOT NULL DEFAULT 0.0,
  first_discovered_at  TIMESTAMP NOT NULL,
  last_confirmed_at    TIMESTAMP NOT NULL,
  metadata_json        TEXT
);

CREATE INDEX IF NOT EXISTS idx_dealer_country    ON dealer_entity(country_code);
CREATE INDEX IF NOT EXISTS idx_dealer_status     ON dealer_entity(status);
CREATE INDEX IF NOT EXISTS idx_dealer_vat        ON dealer_entity(primary_vat) WHERE primary_vat IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dealer_confidence ON dealer_entity(confidence_score);

-- ── Dealer identifiers ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dealer_identifier (
  identifier_id    TEXT PRIMARY KEY,
  dealer_id        TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  identifier_type  TEXT NOT NULL,
  identifier_value TEXT NOT NULL,
  source_family    TEXT NOT NULL,
  validated_at     TIMESTAMP,
  valid_status     TEXT DEFAULT 'UNKNOWN'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_identifier_unique ON dealer_identifier(identifier_type, identifier_value);
CREATE INDEX        IF NOT EXISTS idx_identifier_dealer ON dealer_identifier(dealer_id);

-- ── Dealer location ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dealer_location (
  location_id          TEXT PRIMARY KEY,
  dealer_id            TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  is_primary           BOOLEAN NOT NULL DEFAULT 1,
  address_line1        TEXT,
  address_line2        TEXT,
  postal_code          TEXT,
  city                 TEXT,
  region               TEXT,
  country_code         TEXT NOT NULL,
  lat                  REAL,
  lon                  REAL,
  h3_index             TEXT,
  opening_hours_json   TEXT,
  source_families      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_location_dealer         ON dealer_location(dealer_id);
CREATE INDEX IF NOT EXISTS idx_location_h3             ON dealer_location(h3_index);
CREATE INDEX IF NOT EXISTS idx_location_country_region ON dealer_location(country_code, region);

-- ── Dealer web presence ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dealer_web_presence (
  web_id                 TEXT PRIMARY KEY,
  dealer_id              TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  domain                 TEXT NOT NULL,
  url_root               TEXT NOT NULL,
  platform_type          TEXT,
  dms_provider           TEXT,
  extraction_strategy    TEXT,
  robots_txt_fetched_at  TIMESTAMP,
  sitemap_url            TEXT,
  rss_feed_url           TEXT,
  last_health_check      TIMESTAMP,
  health_status          TEXT,
  discovered_by_families TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_web_domain   ON dealer_web_presence(domain);
CREATE INDEX        IF NOT EXISTS idx_web_dealer   ON dealer_web_presence(dealer_id);
CREATE INDEX        IF NOT EXISTS idx_web_platform ON dealer_web_presence(platform_type);

-- ── Dealer social profile ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dealer_social_profile (
  profile_id             TEXT PRIMARY KEY,
  dealer_id              TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  platform               TEXT NOT NULL,
  profile_url            TEXT NOT NULL,
  external_id            TEXT,
  rating                 REAL,
  review_count           INTEGER,
  last_activity_detected TIMESTAMP,
  metadata_json          TEXT
);

CREATE INDEX IF NOT EXISTS idx_social_dealer   ON dealer_social_profile(dealer_id);
CREATE INDEX IF NOT EXISTS idx_social_platform ON dealer_social_profile(platform);

-- ── OEM affiliation ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dealer_oem_affiliation (
  affiliation_id   TEXT PRIMARY KEY,
  dealer_id        TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  oem_brand        TEXT NOT NULL,
  affiliation_type TEXT NOT NULL,
  oem_dealer_id    TEXT,
  first_observed   TIMESTAMP,
  last_confirmed   TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_oem_dealer ON dealer_oem_affiliation(dealer_id);
CREATE INDEX IF NOT EXISTS idx_oem_brand  ON dealer_oem_affiliation(oem_brand);

-- ── Association membership ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dealer_association_membership (
  membership_id   TEXT PRIMARY KEY,
  dealer_id       TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  association     TEXT NOT NULL,
  member_number   TEXT,
  active          BOOLEAN,
  first_observed  TIMESTAMP,
  last_confirmed  TIMESTAMP
);

-- ── Discovery record (audit log) ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS discovery_record (
  record_id              TEXT PRIMARY KEY,
  dealer_id              TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  family                 TEXT NOT NULL,
  sub_technique          TEXT NOT NULL,
  source_url             TEXT,
  source_record_id       TEXT,
  confidence_contributed REAL NOT NULL,
  discovered_at          TIMESTAMP NOT NULL,
  last_reconfirmed_at    TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dr_dealer    ON discovery_record(dealer_id);
CREATE INDEX IF NOT EXISTS idx_dr_family    ON discovery_record(family);
CREATE INDEX IF NOT EXISTS idx_dr_composite ON discovery_record(dealer_id, family);

-- ── Vehicle record ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vehicle_record (
  vehicle_id               TEXT PRIMARY KEY,
  vin                      TEXT,
  dealer_id                TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  location_id              TEXT REFERENCES dealer_location(location_id),
  make_canonical           TEXT,
  model_canonical          TEXT,
  year                     INTEGER,
  mileage_km               INTEGER,
  fuel_type                TEXT,
  transmission             TEXT,
  power_kw                 INTEGER,
  body_type                TEXT,
  color                    TEXT,
  price_net_eur            REAL,
  price_gross_eur          REAL,
  currency_original        TEXT,
  vat_mode                 TEXT,
  source_url               TEXT NOT NULL,
  source_platform          TEXT NOT NULL,
  source_listing_id        TEXT,
  image_url                TEXT,
  image_url_sha256         TEXT,
  title_generated          TEXT,
  description_generated_ml TEXT,
  validators_passed        INTEGER,
  validators_failed_json   TEXT,
  confidence_score         REAL,
  manual_review_required   BOOLEAN,
  manual_review_verdict    TEXT,
  indexed_at               TIMESTAMP NOT NULL,
  last_confirmed_at        TIMESTAMP NOT NULL,
  ttl_expires_at           TIMESTAMP NOT NULL,
  status                   TEXT NOT NULL DEFAULT 'PENDING_REVIEW',
  fingerprint_sha256       TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_vehicle_vin_dealer    ON vehicle_record(vin, dealer_id) WHERE vin IS NOT NULL;
CREATE INDEX        IF NOT EXISTS idx_vehicle_dealer        ON vehicle_record(dealer_id);
CREATE INDEX        IF NOT EXISTS idx_vehicle_status        ON vehicle_record(status);
CREATE INDEX        IF NOT EXISTS idx_vehicle_ttl           ON vehicle_record(ttl_expires_at);
CREATE INDEX        IF NOT EXISTS idx_vehicle_make_model_yr ON vehicle_record(make_canonical, model_canonical, year);

-- ── Vehicle source witness ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vehicle_source_witness (
  witness_id        TEXT PRIMARY KEY,
  vehicle_id        TEXT NOT NULL REFERENCES vehicle_record(vehicle_id),
  source_platform   TEXT NOT NULL,
  source_listing_id TEXT NOT NULL,
  source_url        TEXT NOT NULL,
  price_net_eur     REAL,
  observed_at       TIMESTAMP NOT NULL,
  last_seen_at      TIMESTAMP NOT NULL,
  status_at_source  TEXT
);

CREATE INDEX        IF NOT EXISTS idx_witness_vehicle ON vehicle_source_witness(vehicle_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_witness_unique  ON vehicle_source_witness(source_platform, source_listing_id);

-- ── Vehicle equipment ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vehicle_equipment (
  vehicle_id     TEXT NOT NULL REFERENCES vehicle_record(vehicle_id),
  equipment_code TEXT NOT NULL,
  source_text    TEXT,
  PRIMARY KEY (vehicle_id, equipment_code)
);

-- ── Dealer chain (optional, inferred) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS dealer_chain (
  chain_id          TEXT PRIMARY KEY,
  chain_name        TEXT,
  inference_method  TEXT,
  confidence        REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS dealer_chain_membership (
  chain_id  TEXT NOT NULL REFERENCES dealer_chain(chain_id),
  dealer_id TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  PRIMARY KEY (chain_id, dealer_id)
);

-- ── Seed schema version ────────────────────────────────────────────────────
INSERT OR IGNORE INTO schema_version(version, description)
VALUES (1, 'initial schema — KG Sprint 1');
