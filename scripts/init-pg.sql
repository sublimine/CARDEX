-- =============================================================================
-- CARDEX PostgreSQL 16 — OLTP Schema
-- Execute on: Nodo 01 (ZFS mirror, CCD0)
-- Encoding: UTF-8, Locale: C (binary sort for determinism)
-- =============================================================================

BEGIN;

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gist";
CREATE EXTENSION IF NOT EXISTS "hstore";

-- =============================================================================
-- ENTITIES (Dealers, Fleets, Institutions)
-- =============================================================================
CREATE TABLE entities (
    entity_ulid       TEXT PRIMARY KEY,
    entity_type       TEXT NOT NULL CHECK (entity_type IN ('DEALER','FLEET','INSTITUTION','INDIVIDUAL')),
    legal_name        TEXT NOT NULL,
    trade_name        TEXT,
    vat_id            TEXT,
    vat_validated     BOOLEAN DEFAULT FALSE,
    vat_last_check    TIMESTAMPTZ,
    country_code      CHAR(2) NOT NULL,
    h3_index_res4     TEXT,
    contact_email     TEXT,
    contact_phone     TEXT,
    stripe_account_id TEXT,
    kyc_status        TEXT DEFAULT 'PENDING' CHECK (kyc_status IN ('PENDING','VERIFIED','REJECTED')),
    subscription_tier TEXT DEFAULT 'FREE' CHECK (subscription_tier IN ('FREE','PRO','CROSS_BORDER','INSTITUTIONAL')),
    karma_score       INT DEFAULT 100 CHECK (karma_score BETWEEN 0 AND 200),
    throttle_ms       INT DEFAULT 0,
    onboarded_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    vault_dek_id      TEXT NOT NULL
) WITH (fillfactor = 70);

CREATE INDEX idx_entities_type ON entities (entity_type);
CREATE INDEX idx_entities_country ON entities (country_code);
CREATE INDEX idx_entities_h3 ON entities (h3_index_res4);
CREATE INDEX idx_entities_tier ON entities (subscription_tier);

-- =============================================================================
-- MANDATES (Mandato Vivo — Atomic Unit)
-- =============================================================================
CREATE TABLE mandates (
    mandate_ulid      TEXT PRIMARY KEY,
    entity_ulid       TEXT NOT NULL REFERENCES entities(entity_ulid),
    status            TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','PAUSED','FULFILLED','EXPIRED','CANCELLED')),
    criteria          JSONB NOT NULL,
    target_quantity   INT DEFAULT 1,
    fulfilled_count   INT DEFAULT 0,
    max_days_active   INT DEFAULT 90,
    alert_channels    TEXT[] DEFAULT ARRAY['PUSH','EMAIL'],
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    expires_at        TIMESTAMPTZ,
    last_match_at     TIMESTAMPTZ,
    updated_at        TIMESTAMPTZ DEFAULT NOW()
) WITH (fillfactor = 70);

CREATE INDEX idx_mandates_entity ON mandates (entity_ulid);
CREATE INDEX idx_mandates_status ON mandates (status) WHERE status = 'ACTIVE';
CREATE INDEX idx_mandates_criteria ON mandates USING GIN (criteria jsonb_path_ops);

-- =============================================================================
-- VEHICLES (Active Inventory)
-- =============================================================================
CREATE TABLE vehicles (
    vehicle_ulid      TEXT PRIMARY KEY,
    fingerprint_sha256 TEXT UNIQUE NOT NULL,
    vin               TEXT,
    source_id         TEXT NOT NULL,
    source_platform   TEXT NOT NULL,
    ingestion_channel TEXT NOT NULL CHECK (ingestion_channel IN ('B2B_WEBHOOK','EDGE_FLEET','MANUAL','SCRAPER','GOOGLE_MAPS')),

    -- Raw data
    make              TEXT,
    model             TEXT,
    variant           TEXT,
    year              INT,
    mileage_km        INT CHECK (mileage_km >= 0),
    color             TEXT,
    fuel_type         TEXT,
    transmission      TEXT,
    co2_gkm           INT CHECK (co2_gkm >= 0),
    power_kw          INT CHECK (power_kw >= 0),
    doors             INT,
    origin_country    CHAR(2),
    raw_description   TEXT,
    thumb_url         TEXT,
    seller_type       TEXT,
    seller_vat_id     TEXT,

    -- Pricing (calculated by Pipeline Phases 4-6)
    price_raw         NUMERIC(12,2) CHECK (price_raw > 0),
    currency_raw      CHAR(3),
    gross_physical_cost_eur NUMERIC(12,2),
    net_landed_cost_eur     NUMERIC(12,2),
    logistics_cost_eur      NUMERIC(12,2),
    tax_amount_eur          NUMERIC(12,2),

    -- Scoring & status
    tax_status        TEXT DEFAULT 'UNKNOWN' CHECK (tax_status IN
                      ('DEDUCTIBLE','REBU','REQUIRES_HUMAN_AUDIT','PENDING_VIES_OPTIMISTIC','UNKNOWN')),
    tax_confidence    NUMERIC(3,2) CHECK (tax_confidence BETWEEN 0 AND 1),
    tax_method        TEXT,
    legal_status      TEXT DEFAULT 'UNCHECKED' CHECK (legal_status IN
                      ('UNCHECKED','LEGAL_CLEAR','LEGAL_LIEN_OR_STOLEN','FRAUD_ODOMETER_ROLLBACK',
                       'LEGAL_TIMEOUT','LEGAL_UNKNOWN')),
    risk_score        NUMERIC(3,2) CHECK (risk_score BETWEEN 0 AND 1),
    liquidity_score   NUMERIC(3,2) CHECK (liquidity_score BETWEEN 0 AND 1),
    cardex_score      NUMERIC(5,2),
    sdi_alert         BOOLEAN DEFAULT FALSE,
    sdi_zone          TEXT,

    -- Geospatial
    lat               NUMERIC(9,6),
    lng               NUMERIC(9,6),
    h3_index_res4     TEXT,
    h3_index_res7     TEXT,

    -- Lifecycle
    days_on_market    INT DEFAULT 0 CHECK (days_on_market >= 0),
    first_seen_at     TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at   TIMESTAMPTZ DEFAULT NOW(),
    sold_at           TIMESTAMPTZ,
    lifecycle_status  TEXT DEFAULT 'INGESTED' CHECK (lifecycle_status IN
                      ('INGESTED','ENRICHED','CLASSIFIED','QUOTED','MARKET_READY','RESERVED','SOLD','EXPIRED','FRAUD_BLOCKED')),

    -- HMAC Quote (Phase 6)
    current_quote_id   TEXT,
    quote_generated_at TIMESTAMPTZ,
    quote_expires_at   TIMESTAMPTZ,
    target_country     CHAR(2),

    -- OCR
    extracted_vin     TEXT,
    ocr_confidence    NUMERIC(3,2) CHECK (ocr_confidence BETWEEN 0 AND 1),

    -- Marketplace / Scraper fields
    source_url        TEXT,
    source_country    CHAR(2),
    photo_urls        TEXT[],
    listing_status    TEXT DEFAULT 'ACTIVE' CHECK (listing_status IN ('ACTIVE','SOLD','EXPIRED','REMOVED')),
    meili_indexed_at  TIMESTAMPTZ,
    price_drop_count  INT DEFAULT 0,
    last_price_eur    NUMERIC(12,2),
    re_listed         BOOLEAN DEFAULT FALSE
) WITH (fillfactor = 70);

CREATE INDEX idx_vehicles_fingerprint ON vehicles (fingerprint_sha256);
CREATE INDEX idx_vehicles_vin ON vehicles (vin) WHERE vin IS NOT NULL;
CREATE INDEX idx_vehicles_source ON vehicles (source_platform);
CREATE INDEX idx_vehicles_lifecycle ON vehicles (lifecycle_status);
CREATE INDEX idx_vehicles_h3_4 ON vehicles (h3_index_res4);
CREATE INDEX idx_vehicles_h3_7 ON vehicles (h3_index_res7);
CREATE INDEX idx_vehicles_nlc ON vehicles (net_landed_cost_eur) WHERE lifecycle_status = 'MARKET_READY';
CREATE INDEX idx_vehicles_score ON vehicles (cardex_score DESC) WHERE lifecycle_status = 'MARKET_READY';
CREATE INDEX idx_vehicles_make_model ON vehicles (make, model);
CREATE INDEX idx_vehicles_tax ON vehicles (tax_status) WHERE tax_status IN ('REQUIRES_HUMAN_AUDIT','PENDING_VIES_OPTIMISTIC');
CREATE INDEX idx_vehicles_source_url ON vehicles (source_url) WHERE source_url IS NOT NULL;
CREATE INDEX idx_vehicles_source_country ON vehicles (source_country);
CREATE INDEX idx_vehicles_listing_status ON vehicles (listing_status);
CREATE INDEX idx_vehicles_meili ON vehicles (meili_indexed_at) WHERE meili_indexed_at IS NULL;

-- =============================================================================
-- RESERVATIONS (Purchase Mutex)
-- =============================================================================
CREATE TABLE reservations (
    reservation_ulid  TEXT PRIMARY KEY,
    vehicle_ulid      TEXT NOT NULL REFERENCES vehicles(vehicle_ulid),
    buyer_entity_ulid TEXT NOT NULL REFERENCES entities(entity_ulid),
    quote_id_hmac     TEXT NOT NULL,
    nlc_at_reservation NUMERIC(12,2) NOT NULL,
    status            TEXT NOT NULL DEFAULT 'LOCKED' CHECK (status IN
                      ('LOCKED','LEGAL_PENDING','CONFIRMED','EXPIRED','CANCELLED','PRICE_MISMATCH')),
    locked_at         TIMESTAMPTZ DEFAULT NOW(),
    lock_expires_at   TIMESTAMPTZ NOT NULL,
    legal_resolved_at TIMESTAMPTZ,
    confirmed_at      TIMESTAMPTZ,
    waiver_signed     BOOLEAN DEFAULT FALSE,
    stripe_payment_id TEXT,
    take_rate_eur     NUMERIC(8,2),
    CONSTRAINT uq_active_reservation EXCLUDE USING gist (
        vehicle_ulid WITH =
    ) WHERE (status IN ('LOCKED','LEGAL_PENDING'))
) WITH (fillfactor = 70);

CREATE INDEX idx_reservations_vehicle ON reservations (vehicle_ulid);
CREATE INDEX idx_reservations_buyer ON reservations (buyer_entity_ulid);
CREATE INDEX idx_reservations_status ON reservations (status) WHERE status IN ('LOCKED','LEGAL_PENDING');

-- =============================================================================
-- SUBSCRIPTIONS
-- =============================================================================
CREATE TABLE subscriptions (
    subscription_ulid TEXT PRIMARY KEY,
    entity_ulid       TEXT NOT NULL REFERENCES entities(entity_ulid),
    tier              TEXT NOT NULL CHECK (tier IN ('FREE','PRO','CROSS_BORDER','INSTITUTIONAL')),
    price_eur_month   NUMERIC(8,2) NOT NULL,
    billing_cycle     TEXT DEFAULT 'MONTHLY' CHECK (billing_cycle IN ('MONTHLY','ANNUAL')),
    stripe_sub_id     TEXT,
    started_at        TIMESTAMPTZ DEFAULT NOW(),
    current_period_end TIMESTAMPTZ,
    cancelled_at      TIMESTAMPTZ,
    status            TEXT DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','PAST_DUE','CANCELLED','TRIALING'))
) WITH (fillfactor = 70);

CREATE INDEX idx_subscriptions_entity ON subscriptions (entity_ulid);
CREATE INDEX idx_subscriptions_status ON subscriptions (status) WHERE status = 'ACTIVE';

-- =============================================================================
-- COMPUTE CREDITS (Anti-MiCA: 90-day TTL, non-transferable)
-- =============================================================================
CREATE TABLE compute_credits (
    credit_ulid       TEXT PRIMARY KEY,
    entity_ulid       TEXT NOT NULL REFERENCES entities(entity_ulid),
    amount            INT NOT NULL CHECK (amount > 0),
    remaining         INT NOT NULL CHECK (remaining >= 0),
    purchased_at      TIMESTAMPTZ DEFAULT NOW(),
    expires_at        TIMESTAMPTZ NOT NULL,
    stripe_charge_id  TEXT,
    CONSTRAINT chk_expires CHECK (expires_at = purchased_at + INTERVAL '90 days'),
    CONSTRAINT chk_remaining CHECK (remaining <= amount)
) WITH (fillfactor = 70);

CREATE INDEX idx_credits_entity ON compute_credits (entity_ulid);
CREATE INDEX idx_credits_expiry ON compute_credits (expires_at) WHERE remaining > 0;

-- =============================================================================
-- AUDIT LOG (Immutable append-only)
-- =============================================================================
CREATE TABLE audit_log (
    log_ulid          TEXT PRIMARY KEY,
    entity_ulid       TEXT,
    action            TEXT NOT NULL,
    target_type       TEXT NOT NULL,
    target_ulid       TEXT NOT NULL,
    payload           JSONB,
    ip_address        INET,
    created_at        TIMESTAMPTZ DEFAULT NOW()
) WITH (fillfactor = 100);  -- Never updated, 100% fill

CREATE INDEX idx_audit_entity ON audit_log (entity_ulid, created_at DESC);
CREATE INDEX idx_audit_target ON audit_log (target_type, target_ulid);

-- =============================================================================
-- PUBLICATION FOR CLICKHOUSE REPLICATION (Zero-PII)
-- FIX: PostgreSQL cannot publish VIEWs. Use column list on base table instead.
-- =============================================================================
CREATE PUBLICATION cardex_analytics_pub
    FOR TABLE vehicles (
        vehicle_ulid, fingerprint_sha256, source_platform, ingestion_channel,
        make, model, variant, year, mileage_km, color, fuel_type, transmission,
        co2_gkm, power_kw, origin_country,
        price_raw, currency_raw, gross_physical_cost_eur, net_landed_cost_eur,
        logistics_cost_eur, tax_amount_eur,
        tax_status, tax_confidence, legal_status, risk_score, liquidity_score,
        cardex_score, sdi_alert,
        h3_index_res4, h3_index_res7, days_on_market,
        first_seen_at, last_updated_at, sold_at, lifecycle_status
    );
-- NOTE: PII columns (vin, raw_description, source_id, thumb_url) are EXCLUDED.
-- ClickHouse MaterializedPostgreSQL engine subscribes to this publication.

-- =============================================================================
-- ROW LEVEL SECURITY (Multi-tenant isolation)
-- =============================================================================
ALTER TABLE vehicles ENABLE ROW LEVEL SECURITY;
ALTER TABLE mandates ENABLE ROW LEVEL SECURITY;
ALTER TABLE reservations ENABLE ROW LEVEL SECURITY;

-- App sets: SET app.current_entity = '<entity_ulid>';
CREATE POLICY entity_isolation_mandates ON mandates
    USING (entity_ulid = current_setting('app.current_entity', true));

CREATE POLICY entity_isolation_reservations ON reservations
    USING (buyer_entity_ulid = current_setting('app.current_entity', true));

-- Vehicles are globally visible (marketplace), but RLS can restrict by subscription tier if needed.

-- =============================================================================
-- USERS (Public marketplace registered users)
-- =============================================================================
CREATE TABLE users (
    user_ulid         TEXT PRIMARY KEY,
    email             TEXT UNIQUE NOT NULL,
    password_hash     TEXT,
    full_name         TEXT,
    country_code      CHAR(2),
    is_dealer         BOOLEAN DEFAULT FALSE,
    entity_ulid       TEXT REFERENCES entities(entity_ulid),
    email_verified    BOOLEAN DEFAULT FALSE,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    last_login_at     TIMESTAMPTZ,
    vault_dek_id      TEXT NOT NULL
) WITH (fillfactor = 80);

CREATE INDEX idx_users_email ON users (email);
CREATE INDEX idx_users_entity ON users (entity_ulid) WHERE entity_ulid IS NOT NULL;

-- =============================================================================
-- PRICE ALERTS (Saved searches with notifications)
-- =============================================================================
CREATE TABLE price_alerts (
    alert_ulid        TEXT PRIMARY KEY,
    user_ulid         TEXT NOT NULL REFERENCES users(user_ulid),
    criteria          JSONB NOT NULL,
    target_price_eur  NUMERIC(12,2),
    channel           TEXT DEFAULT 'EMAIL' CHECK (channel IN ('EMAIL','PUSH','BOTH')),
    active            BOOLEAN DEFAULT TRUE,
    last_fired_at     TIMESTAMPTZ,
    fire_count        INT DEFAULT 0,
    created_at        TIMESTAMPTZ DEFAULT NOW()
) WITH (fillfactor = 80);

CREATE INDEX idx_alerts_user ON price_alerts (user_ulid);
CREATE INDEX idx_alerts_active ON price_alerts (active) WHERE active = TRUE;
CREATE INDEX idx_alerts_criteria ON price_alerts USING GIN (criteria jsonb_path_ops);

-- =============================================================================
-- DEALER INVENTORY (Dealer's own stock, independent of scraped listings)
-- =============================================================================
CREATE TABLE dealer_inventory (
    item_ulid         TEXT PRIMARY KEY,
    entity_ulid       TEXT NOT NULL REFERENCES entities(entity_ulid),
    vin               TEXT,
    make              TEXT NOT NULL,
    model             TEXT NOT NULL,
    variant           TEXT,
    year              INT NOT NULL CHECK (year BETWEEN 1980 AND 2030),
    mileage_km        INT NOT NULL CHECK (mileage_km >= 0),
    fuel_type         TEXT,
    transmission      TEXT,
    color             TEXT,
    power_kw          INT,
    co2_gkm           INT,
    doors             INT,
    asking_price_eur  NUMERIC(12,2) NOT NULL CHECK (asking_price_eur > 0),
    cost_price_eur    NUMERIC(12,2),
    status            TEXT DEFAULT 'AVAILABLE' CHECK (status IN ('AVAILABLE','RESERVED','SOLD','DELISTED')),
    description       TEXT,
    photo_urls        TEXT[],
    features          JSONB,
    marketing_score   NUMERIC(3,2),
    days_in_stock     INT DEFAULT 0,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
) WITH (fillfactor = 80);

CREATE INDEX idx_dealerinv_entity ON dealer_inventory (entity_ulid);
CREATE INDEX idx_dealerinv_status ON dealer_inventory (status);
CREATE INDEX idx_dealerinv_vin ON dealer_inventory (vin) WHERE vin IS NOT NULL;

ALTER TABLE dealer_inventory ENABLE ROW LEVEL SECURITY;
CREATE POLICY dealer_inv_isolation ON dealer_inventory
    USING (entity_ulid = current_setting('app.current_entity', true));

-- =============================================================================
-- PUBLISH JOBS (Multiposting to external platforms)
-- =============================================================================
CREATE TABLE publish_jobs (
    job_ulid          TEXT PRIMARY KEY,
    item_ulid         TEXT NOT NULL REFERENCES dealer_inventory(item_ulid),
    entity_ulid       TEXT NOT NULL REFERENCES entities(entity_ulid),
    platform          TEXT NOT NULL,
    status            TEXT DEFAULT 'PENDING' CHECK (status IN ('PENDING','PUBLISHED','FAILED','REMOVED','UPDATING')),
    external_id       TEXT,
    external_url      TEXT,
    published_at      TIMESTAMPTZ,
    last_synced_at    TIMESTAMPTZ,
    error_message     TEXT,
    retry_count       INT DEFAULT 0,
    created_at        TIMESTAMPTZ DEFAULT NOW()
) WITH (fillfactor = 80);

CREATE INDEX idx_publishjobs_item ON publish_jobs (item_ulid);
CREATE INDEX idx_publishjobs_entity ON publish_jobs (entity_ulid);
CREATE INDEX idx_publishjobs_status ON publish_jobs (status) WHERE status IN ('PENDING','FAILED');

-- =============================================================================
-- LEADS (CRM — inbound contacts from marketplace or direct)
-- =============================================================================
CREATE TABLE leads (
    lead_ulid         TEXT PRIMARY KEY,
    entity_ulid       TEXT NOT NULL REFERENCES entities(entity_ulid),
    item_ulid         TEXT REFERENCES dealer_inventory(item_ulid),
    vehicle_ulid      TEXT REFERENCES vehicles(vehicle_ulid),
    contact_name      TEXT,
    contact_email     TEXT,
    contact_phone     TEXT,
    message           TEXT,
    source_platform   TEXT,
    utm_source        TEXT,
    status            TEXT DEFAULT 'NEW' CHECK (status IN ('NEW','CONTACTED','NEGOTIATING','SOLD','LOST')),
    notes             TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
) WITH (fillfactor = 80);

CREATE INDEX idx_leads_entity ON leads (entity_ulid);
CREATE INDEX idx_leads_status ON leads (status);
CREATE INDEX idx_leads_item ON leads (item_ulid) WHERE item_ulid IS NOT NULL;

ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
CREATE POLICY leads_isolation ON leads
    USING (entity_ulid = current_setting('app.current_entity', true));

-- =============================================================================
-- SCRAPE JOBS (Tracking per-platform scraper runs)
-- =============================================================================
CREATE TABLE scrape_jobs (
    job_ulid          TEXT PRIMARY KEY,
    platform          TEXT NOT NULL,
    country           CHAR(2) NOT NULL,
    status            TEXT DEFAULT 'PENDING' CHECK (status IN ('PENDING','RUNNING','COMPLETED','FAILED','ABORTED')),
    listings_found    INT DEFAULT 0,
    listings_new      INT DEFAULT 0,
    listings_updated  INT DEFAULT 0,
    listings_sold     INT DEFAULT 0,
    bytes_fetched     BIGINT DEFAULT 0,
    requests_made     INT DEFAULT 0,
    started_at        TIMESTAMPTZ,
    completed_at      TIMESTAMPTZ,
    duration_ms       INT,
    error_message     TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW()
) WITH (fillfactor = 80);

CREATE INDEX idx_scrapejobs_platform ON scrape_jobs (platform, country);
CREATE INDEX idx_scrapejobs_status ON scrape_jobs (status) WHERE status IN ('RUNNING','PENDING');

-- =============================================================================
-- VIN HISTORY CACHE (Denormalized for fast single-VIN lookups)
-- =============================================================================
CREATE TABLE vin_history_cache (
    id                BIGSERIAL PRIMARY KEY,
    vin               TEXT NOT NULL,
    event_type        TEXT NOT NULL CHECK (event_type IN
                      ('MILEAGE','ACCIDENT','OWNERSHIP','IMPORT','STOLEN_CHECK',
                       'LISTING','PRICE_CHANGE','MOT','DAMAGE')),
    event_date        DATE,
    data              JSONB NOT NULL,
    source            TEXT NOT NULL,
    confidence        NUMERIC(3,2) DEFAULT 1.0,
    created_at        TIMESTAMPTZ DEFAULT NOW()
) WITH (fillfactor = 90);

CREATE INDEX idx_vinhistory_vin ON vin_history_cache (vin, event_date DESC);
CREATE INDEX idx_vinhistory_type ON vin_history_cache (vin, event_type);

-- =============================================================================
-- DEALER MARKETING AUDIT (AI-generated improvement reports)
-- =============================================================================
CREATE TABLE marketing_audits (
    audit_ulid        TEXT PRIMARY KEY,
    entity_ulid       TEXT NOT NULL REFERENCES entities(entity_ulid),
    overall_score     NUMERIC(3,2),
    photo_score       NUMERIC(3,2),
    description_score NUMERIC(3,2),
    price_score       NUMERIC(3,2),
    platform_coverage_score NUMERIC(3,2),
    issues            JSONB,
    recommendations   JSONB,
    estimated_revenue_loss_eur NUMERIC(10,2),
    generated_at      TIMESTAMPTZ DEFAULT NOW()
) WITH (fillfactor = 80);

CREATE INDEX idx_audits_entity ON marketing_audits (entity_ulid);

COMMIT;

-- =============================================================================
-- DEALERS — Physical dealer registry (all discovery sources merged)
-- Populated by: DiscoveryOrchestrator (H3 grid + OSM + government registries)
-- Consumed by:  DealerWebSpider (fleet crawls dealer websites for inventory)
-- =============================================================================
-- (appended after COMMIT — run as separate migration if needed)
BEGIN;

CREATE TABLE IF NOT EXISTS dealers (
    id                BIGSERIAL PRIMARY KEY,
    place_id          TEXT,
    registry_id       TEXT,
    osm_id            TEXT,
    name              TEXT NOT NULL,
    country           TEXT NOT NULL,
    lat               DOUBLE PRECISION,
    lng               DOUBLE PRECISION,
    h3_res7           TEXT,
    h3_res4           TEXT,
    address           TEXT,
    city              TEXT,
    postcode          TEXT,
    canton            TEXT,
    website           TEXT,
    phone             TEXT,
    email             TEXT,
    brand_affiliation TEXT[],
    dealer_type       TEXT DEFAULT 'INDEPENDENT',
    source            TEXT NOT NULL,
    discovery_sources TEXT[] DEFAULT '{}',
    spider_status     TEXT DEFAULT 'PENDING',
    spider_last_run   TIMESTAMPTZ,
    spider_dms        TEXT,
    spider_listing_count INT DEFAULT 0,
    google_rating     NUMERIC(2,1),
    google_review_count INT,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (
        COALESCE(place_id, ''),
        COALESCE(registry_id, ''),
        name,
        country
    )
) WITH (fillfactor = 80);

CREATE INDEX IF NOT EXISTS idx_dealers_country     ON dealers (country);
CREATE INDEX IF NOT EXISTS idx_dealers_h3_res7     ON dealers (h3_res7);
CREATE INDEX IF NOT EXISTS idx_dealers_h3_res4     ON dealers (h3_res4);
CREATE INDEX IF NOT EXISTS idx_dealers_spider      ON dealers (spider_status, country);
CREATE INDEX IF NOT EXISTS idx_dealers_website     ON dealers (website) WHERE website IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dealers_place_id    ON dealers (place_id) WHERE place_id IS NOT NULL;

COMMIT;
