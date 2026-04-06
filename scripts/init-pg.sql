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
    email_verified_at TIMESTAMPTZ,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
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
-- PUBLISHING LISTINGS (Multipublicación — platform status per CRM vehicle)
-- =============================================================================
BEGIN;

CREATE TABLE IF NOT EXISTS publishing_listings (
    pub_ulid          TEXT PRIMARY KEY,
    entity_ulid       TEXT NOT NULL REFERENCES entities(entity_ulid) ON DELETE CASCADE,
    crm_vehicle_ulid  TEXT NOT NULL REFERENCES crm_vehicles(crm_vehicle_ulid) ON DELETE CASCADE,
    platform          TEXT NOT NULL CHECK (platform IN (
                          'AUTOSCOUT24','WALLAPOP','COCHES_NET','MOBILE_DE',
                          'MARKTPLAATS','LACENTRALE','MILANUNCIOS','MANUAL')),
    status            TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN (
                          'DRAFT','PENDING','ACTIVE','PAUSED','EXPIRED','REJECTED')),
    title             TEXT,
    external_id       TEXT,
    external_url      TEXT,
    error_message     TEXT,
    published_at      TIMESTAMPTZ,
    expires_at        TIMESTAMPTZ,
    last_synced_at    TIMESTAMPTZ,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(entity_ulid, crm_vehicle_ulid, platform)
) WITH (fillfactor = 80);

CREATE INDEX IF NOT EXISTS idx_publistings_entity   ON publishing_listings (entity_ulid);
CREATE INDEX IF NOT EXISTS idx_publistings_vehicle  ON publishing_listings (crm_vehicle_ulid);
CREATE INDEX IF NOT EXISTS idx_publistings_platform ON publishing_listings (platform, status);
CREATE INDEX IF NOT EXISTS idx_publistings_status   ON publishing_listings (status) WHERE status IN ('PENDING','ACTIVE');

ALTER TABLE publishing_listings ENABLE ROW LEVEL SECURITY;
CREATE POLICY publistings_isolation ON publishing_listings
    USING (entity_ulid = current_setting('app.current_entity', true));

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

-- =============================================================================
-- CRM SYSTEM — Full DealCar.io-level dealer CRM
-- =============================================================================
BEGIN;

-- CRM Contacts (customer database — separated from anonymous leads)
CREATE TABLE crm_contacts (
    contact_ulid      TEXT PRIMARY KEY,
    entity_ulid       TEXT NOT NULL REFERENCES entities(entity_ulid) ON DELETE CASCADE,
    full_name         TEXT NOT NULL,
    email             TEXT,
    phone             TEXT,
    phone_alt         TEXT,
    address_line1     TEXT,
    address_city      TEXT,
    address_country   CHAR(2),
    postal_code       TEXT,
    birth_year        INT,
    id_number         TEXT,  -- DNI/NIE/passport — encrypted
    preferred_contact TEXT CHECK (preferred_contact IN ('EMAIL','PHONE','WHATSAPP','SMS')),
    language          CHAR(2) DEFAULT 'ES',
    tags              TEXT[] DEFAULT '{}',
    notes             TEXT,
    source            TEXT,  -- how they came to us
    gdpr_consent      BOOLEAN DEFAULT FALSE,
    gdpr_consent_at   TIMESTAMPTZ,
    lifetime_value_eur NUMERIC(12,2) DEFAULT 0,
    total_purchases   INT DEFAULT 0,
    total_inquiries   INT DEFAULT 0,
    last_contact_at   TIMESTAMPTZ,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    vault_dek_id      TEXT NOT NULL  -- for PII encryption
) WITH (fillfactor = 80);

CREATE INDEX idx_crm_contacts_entity ON crm_contacts(entity_ulid);
CREATE INDEX idx_crm_contacts_email ON crm_contacts(email) WHERE email IS NOT NULL;
CREATE INDEX idx_crm_contacts_phone ON crm_contacts(phone) WHERE phone IS NOT NULL;
CREATE INDEX idx_crm_contacts_tags ON crm_contacts USING GIN(tags);

-- CRM Vehicles (full lifecycle inventory management — extends dealer_inventory)
CREATE TABLE crm_vehicles (
    crm_vehicle_ulid  TEXT PRIMARY KEY,
    entity_ulid       TEXT NOT NULL REFERENCES entities(entity_ulid) ON DELETE CASCADE,
    item_ulid         TEXT REFERENCES dealer_inventory(item_ulid),  -- link to main inventory
    vin               TEXT,
    make              TEXT NOT NULL,
    model             TEXT NOT NULL,
    variant           TEXT,
    year              INT NOT NULL,
    mileage_km        INT,
    fuel_type         TEXT,
    transmission      TEXT,
    color_exterior    TEXT,
    color_interior    TEXT,
    power_kw          INT,
    co2_gkm           INT,
    doors             INT,
    body_type         TEXT,
    registration_date DATE,
    first_registration_country CHAR(2),
    service_book      BOOLEAN DEFAULT FALSE,
    keys_count        INT DEFAULT 2,

    -- Lifecycle status (richer than dealer_inventory.status)
    lifecycle_status  TEXT NOT NULL DEFAULT 'SOURCING' CHECK (lifecycle_status IN (
        'SOURCING',        -- being acquired/negotiated
        'PURCHASED',       -- we own it, not yet reconditioned
        'RECONDITIONING',  -- at workshop
        'READY',           -- ready for sale
        'LISTED',          -- actively advertised
        'RESERVED',        -- deposit taken
        'SOLD',            -- completed sale
        'RETURNED',        -- post-sale return
        'ARCHIVED'         -- removed, not for sale
    )),

    -- Financial tracking (the core of DealCar.io's value)
    purchase_price_eur     NUMERIC(12,2),
    purchase_date          DATE,
    purchase_from          TEXT,  -- auction / private / dealer / trade-in
    purchase_channel       TEXT,  -- BCA / Manheim / Autorola / private / trade

    recon_cost_eur         NUMERIC(12,2) DEFAULT 0,  -- workshop costs
    transport_cost_eur     NUMERIC(12,2) DEFAULT 0,
    homologation_cost_eur  NUMERIC(12,2) DEFAULT 0,  -- ITV/TUV/CT
    marketing_cost_eur     NUMERIC(12,2) DEFAULT 0,
    financing_cost_eur     NUMERIC(12,2) DEFAULT 0,  -- floor plan interest
    other_cost_eur         NUMERIC(12,2) DEFAULT 0,

    asking_price_eur       NUMERIC(12,2),
    floor_price_eur        NUMERIC(12,2),  -- minimum acceptable
    target_margin_pct      NUMERIC(5,2) DEFAULT 15.0,

    -- Sale tracking
    sale_price_eur         NUMERIC(12,2),
    sale_date              DATE,
    sale_contact_ulid      TEXT REFERENCES crm_contacts(contact_ulid),
    payment_method         TEXT,  -- CASH / FINANCING / TRADE_IN_PLUS_CASH
    financing_bank         TEXT,

    -- Days in stock
    stock_entry_date       DATE DEFAULT CURRENT_DATE,

    -- Condition & photos
    condition_grade        TEXT CHECK (condition_grade IN ('A','B','C','D')),  -- A=excellent, D=rough
    photos                 TEXT[],
    main_photo_url         TEXT,

    -- Platform publishing
    published_platforms    TEXT[] DEFAULT '{}',
    meili_indexed          BOOLEAN DEFAULT FALSE,

    notes                  TEXT,
    created_at             TIMESTAMPTZ DEFAULT NOW(),
    updated_at             TIMESTAMPTZ DEFAULT NOW()
) WITH (fillfactor = 80);

CREATE INDEX idx_crm_vehicles_entity ON crm_vehicles(entity_ulid);
CREATE INDEX idx_crm_vehicles_lifecycle ON crm_vehicles(entity_ulid, lifecycle_status);
CREATE INDEX idx_crm_vehicles_vin ON crm_vehicles(vin) WHERE vin IS NOT NULL;
CREATE INDEX idx_crm_vehicles_make_model ON crm_vehicles(entity_ulid, make, model);

-- Reconditioning jobs (workshop tracking)
CREATE TABLE crm_recon_jobs (
    job_ulid          TEXT PRIMARY KEY,
    crm_vehicle_ulid  TEXT NOT NULL REFERENCES crm_vehicles(crm_vehicle_ulid) ON DELETE CASCADE,
    entity_ulid       TEXT NOT NULL,
    job_type          TEXT NOT NULL,  -- MECHANICAL / BODYWORK / DETAILING / ELECTRICAL / ITV / TIRES / OTHER
    description       TEXT NOT NULL,
    supplier_name     TEXT,
    cost_estimate_eur NUMERIC(10,2),
    cost_actual_eur   NUMERIC(10,2),
    status            TEXT DEFAULT 'PENDING' CHECK (status IN ('PENDING','IN_PROGRESS','DONE','CANCELLED')),
    started_at        DATE,
    completed_at      DATE,
    invoice_url       TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_recon_jobs_vehicle ON crm_recon_jobs(crm_vehicle_ulid);

-- CRM Pipeline (sales pipeline stages — like Kanban)
CREATE TABLE crm_pipeline_stages (
    stage_ulid        TEXT PRIMARY KEY,
    entity_ulid       TEXT NOT NULL REFERENCES entities(entity_ulid) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    color             TEXT DEFAULT '#15b570',
    position          INT NOT NULL,
    auto_action       TEXT,  -- e.g. 'SEND_EMAIL_TEMPLATE_1'
    is_won            BOOLEAN DEFAULT FALSE,
    is_lost           BOOLEAN DEFAULT FALSE
);

-- Pipeline deals (each deal = contact x vehicle x stage)
CREATE TABLE crm_deals (
    deal_ulid         TEXT PRIMARY KEY,
    entity_ulid       TEXT NOT NULL REFERENCES entities(entity_ulid) ON DELETE CASCADE,
    contact_ulid      TEXT NOT NULL REFERENCES crm_contacts(contact_ulid),
    crm_vehicle_ulid  TEXT REFERENCES crm_vehicles(crm_vehicle_ulid),
    stage_ulid        TEXT NOT NULL REFERENCES crm_pipeline_stages(stage_ulid),
    title             TEXT NOT NULL,
    status            TEXT DEFAULT 'OPEN' CHECK (status IN ('OPEN','WON','LOST','ON_HOLD')),
    deal_value_eur    NUMERIC(12,2),
    probability_pct   INT DEFAULT 50,
    expected_close    DATE,
    lost_reason       TEXT,
    assigned_to       TEXT REFERENCES users(user_ulid),
    notes             TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_crm_deals_entity ON crm_deals(entity_ulid);
CREATE INDEX idx_crm_deals_contact ON crm_deals(contact_ulid);
CREATE INDEX idx_crm_deals_stage ON crm_deals(stage_ulid);
CREATE INDEX idx_crm_deals_status ON crm_deals(entity_ulid, status);

-- Communications log (email/call/WhatsApp/SMS/visit)
CREATE TABLE crm_communications (
    comm_ulid         TEXT PRIMARY KEY,
    entity_ulid       TEXT NOT NULL,
    contact_ulid      TEXT REFERENCES crm_contacts(contact_ulid),
    deal_ulid         TEXT REFERENCES crm_deals(deal_ulid),
    crm_vehicle_ulid  TEXT REFERENCES crm_vehicles(crm_vehicle_ulid),
    channel           TEXT NOT NULL CHECK (channel IN ('EMAIL','PHONE','WHATSAPP','SMS','VISIT','VIDEO_CALL','NOTE')),
    direction         TEXT CHECK (direction IN ('INBOUND','OUTBOUND')),
    subject           TEXT,
    body              TEXT,
    outcome           TEXT,  -- 'interested', 'not_interested', 'callback', 'offer_made', etc.
    duration_sec      INT,   -- for calls
    created_by        TEXT REFERENCES users(user_ulid),
    created_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_crm_comm_contact ON crm_communications(contact_ulid);
CREATE INDEX idx_crm_comm_deal ON crm_communications(deal_ulid);
CREATE INDEX idx_crm_comm_entity ON crm_communications(entity_ulid, created_at DESC);

-- Documents (contracts, invoices, registration docs)
CREATE TABLE crm_documents (
    doc_ulid          TEXT PRIMARY KEY,
    entity_ulid       TEXT NOT NULL,
    crm_vehicle_ulid  TEXT REFERENCES crm_vehicles(crm_vehicle_ulid),
    contact_ulid      TEXT REFERENCES crm_contacts(contact_ulid),
    deal_ulid         TEXT REFERENCES crm_deals(deal_ulid),
    doc_type          TEXT NOT NULL CHECK (doc_type IN (
        'PURCHASE_CONTRACT','SALE_CONTRACT','INVOICE','TRADE_IN_RECEIPT',
        'REGISTRATION_CERT','SERVICE_HISTORY','INSURANCE','FINANCING_CONTRACT',
        'INSPECTION_REPORT','PHOTO_REPORT','OTHER'
    )),
    filename          TEXT NOT NULL,
    storage_url       TEXT NOT NULL,  -- S3/GCS/MinIO URL
    file_size_bytes   INT,
    uploaded_by       TEXT REFERENCES users(user_ulid),
    created_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_crm_docs_vehicle ON crm_documents(crm_vehicle_ulid);
CREATE INDEX idx_crm_docs_deal ON crm_documents(deal_ulid);

-- Financial transactions (per vehicle P&L)
CREATE TABLE crm_transactions (
    tx_ulid           TEXT PRIMARY KEY,
    entity_ulid       TEXT NOT NULL,
    crm_vehicle_ulid  TEXT NOT NULL REFERENCES crm_vehicles(crm_vehicle_ulid),
    tx_type           TEXT NOT NULL CHECK (tx_type IN (
        'PURCHASE','RECON','TRANSPORT','HOMOLOGATION','MARKETING',
        'FINANCING_COST','SALE_REVENUE','TRADE_IN_VALUE','TAX','OTHER_COST','OTHER_REVENUE'
    )),
    amount_eur        NUMERIC(12,2) NOT NULL,  -- negative = cost, positive = revenue
    description       TEXT,
    invoice_number    TEXT,
    tx_date           DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_crm_tx_vehicle ON crm_transactions(crm_vehicle_ulid);
CREATE INDEX idx_crm_tx_entity_date ON crm_transactions(entity_ulid, tx_date DESC);

-- KPI goals (monthly targets)
CREATE TABLE crm_goals (
    goal_ulid         TEXT PRIMARY KEY,
    entity_ulid       TEXT NOT NULL REFERENCES entities(entity_ulid) ON DELETE CASCADE,
    period_month      CHAR(7) NOT NULL,  -- '2025-01'
    target_units_sold INT DEFAULT 0,
    target_revenue_eur NUMERIC(12,2) DEFAULT 0,
    target_margin_pct NUMERIC(5,2) DEFAULT 0,
    target_avg_dom    INT DEFAULT 30,
    actual_units_sold INT DEFAULT 0,
    actual_revenue_eur NUMERIC(12,2) DEFAULT 0,
    actual_margin_pct  NUMERIC(5,2) DEFAULT 0,
    actual_avg_dom     INT DEFAULT 0,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(entity_ulid, period_month)
);

-- =============================================================================
-- NOTIFICATIONS (In-app notification centre — per user or per entity)
-- =============================================================================
CREATE TABLE notifications (
    notification_ulid  TEXT PRIMARY KEY,
    entity_ulid        TEXT REFERENCES entities(entity_ulid) ON DELETE CASCADE,
    user_ulid          TEXT REFERENCES users(user_ulid) ON DELETE CASCADE,
    type               TEXT NOT NULL CHECK (type IN (
        'PRICE_ALERT',
        'ARBITRAGE',
        'VIN_RESULT',
        'DEAL_UPDATE',
        'RECON_DONE',
        'GOAL_REACHED',
        'NEW_LEAD',
        'INVENTORY_LOW',
        'SYSTEM'
    )),
    title              TEXT NOT NULL,
    body               TEXT NOT NULL,
    action_url         TEXT,
    data               JSONB DEFAULT '{}',
    read_at            TIMESTAMPTZ,
    created_at         TIMESTAMPTZ DEFAULT NOW()
) WITH (fillfactor = 80);

CREATE INDEX idx_notifications_entity  ON notifications (entity_ulid, created_at DESC) WHERE read_at IS NULL;
CREATE INDEX idx_notifications_user    ON notifications (user_ulid,   created_at DESC) WHERE read_at IS NULL;
CREATE INDEX idx_notifications_all     ON notifications (entity_ulid, created_at DESC);

-- =============================================================================
-- USER ROLES (RBAC — sub-roles dentro de una entidad)
-- =============================================================================
CREATE TABLE user_roles (
    entity_ulid  TEXT NOT NULL REFERENCES entities(entity_ulid) ON DELETE CASCADE,
    user_ulid    TEXT NOT NULL REFERENCES users(user_ulid) ON DELETE CASCADE,
    role         TEXT NOT NULL DEFAULT 'SELLER' CHECK (role IN ('OWNER','MANAGER','SELLER','MECHANIC','VIEWER')),
    granted_by   TEXT REFERENCES users(user_ulid),
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (entity_ulid, user_ulid)
);
CREATE INDEX idx_user_roles_entity ON user_roles (entity_ulid);

-- =============================================================================
-- GROUP MANAGEMENT (Grupos de concesionarios — dealer groups)
-- =============================================================================
ALTER TABLE entities ADD COLUMN IF NOT EXISTS parent_entity_ulid TEXT REFERENCES entities(entity_ulid);
ALTER TABLE entities ADD COLUMN IF NOT EXISTS group_name TEXT;
CREATE INDEX idx_entities_parent ON entities (parent_entity_ulid) WHERE parent_entity_ulid IS NOT NULL;

-- Admin flag en users
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;

-- =============================================================================
-- FLEET CENSUS (Government registration statistics — KBA, RDW, DGT, SDES, DIV, ASTRA)
-- =============================================================================
CREATE TABLE fleet_census (
    id                BIGSERIAL PRIMARY KEY,
    country           CHAR(2) NOT NULL,
    make              TEXT NOT NULL,
    year              INT NOT NULL,
    fuel_type         TEXT,
    vehicle_count     BIGINT NOT NULL CHECK (vehicle_count >= 0),
    as_of_date        DATE NOT NULL,
    source            TEXT NOT NULL,
    raw_category      TEXT,
    ingested_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (country, make, year, fuel_type, source, as_of_date)
) WITH (fillfactor = 90);

CREATE INDEX idx_fleet_census_country ON fleet_census (country, make, year);
CREATE INDEX idx_fleet_census_date ON fleet_census (as_of_date DESC);

-- =============================================================================
-- COVERAGE MATRIX (Computed by census service: fleet × turnover × avg_dom / 365)
-- =============================================================================
CREATE TABLE coverage_matrix (
    id                BIGSERIAL PRIMARY KEY,
    country           CHAR(2) NOT NULL,
    make              TEXT NOT NULL,
    year              INT NOT NULL,
    fuel_type         TEXT,
    fleet_count       BIGINT NOT NULL,
    turnover_rate     NUMERIC(6,4),
    expected_for_sale INT NOT NULL,
    observed_count    INT NOT NULL,
    coverage          NUMERIC(5,4) NOT NULL CHECK (coverage >= 0),
    economic_value_eur NUMERIC(14,2),
    median_price_eur  NUMERIC(12,2),
    computed_at       TIMESTAMPTZ DEFAULT NOW()
) WITH (fillfactor = 80);

CREATE INDEX idx_coverage_country ON coverage_matrix (country, make);
CREATE INDEX idx_coverage_gap ON coverage_matrix (economic_value_eur DESC NULLS LAST);
CREATE INDEX idx_coverage_date ON coverage_matrix (computed_at DESC);

-- =============================================================================
-- CRAWL FRONTIER (Per-shard priority, Thompson Sampling state)
-- =============================================================================
CREATE TABLE crawl_frontier (
    id                BIGSERIAL PRIMARY KEY,
    platform          TEXT NOT NULL,
    country           CHAR(2) NOT NULL,
    make              TEXT NOT NULL,
    year              INT NOT NULL,
    priority_score    NUMERIC(6,4) NOT NULL DEFAULT 0,
    last_crawled_at   TIMESTAMPTZ,
    next_crawl_at     TIMESTAMPTZ,
    recrawl_interval_s INT DEFAULT 3600,
    listings_found    INT DEFAULT 0,
    listings_new      INT DEFAULT 0,
    thompson_alpha    INT DEFAULT 1,
    thompson_beta     INT DEFAULT 1,
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (platform, country, make, year)
) WITH (fillfactor = 70);

CREATE INDEX idx_frontier_priority ON crawl_frontier (priority_score DESC);
CREATE INDEX idx_frontier_next ON crawl_frontier (next_crawl_at) WHERE next_crawl_at IS NOT NULL;

-- =============================================================================
-- ENTITY MATCHES (Cross-source dedup: vehicles + dealers, Fellegi-Sunter)
-- =============================================================================
CREATE TABLE entity_matches (
    id                BIGSERIAL PRIMARY KEY,
    match_type        TEXT NOT NULL CHECK (match_type IN ('VEHICLE','DEALER')),
    entity_a_id       TEXT NOT NULL,
    entity_a_source   TEXT NOT NULL,
    entity_b_id       TEXT NOT NULL,
    entity_b_source   TEXT NOT NULL,
    confidence        NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    match_method      TEXT NOT NULL,
    match_fields      JSONB,
    validated         BOOLEAN,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (match_type, entity_a_id, entity_a_source, entity_b_id, entity_b_source)
) WITH (fillfactor = 80);

CREATE INDEX idx_entity_matches_a ON entity_matches (entity_a_id);
CREATE INDEX idx_entity_matches_b ON entity_matches (entity_b_id);
CREATE INDEX idx_entity_matches_type ON entity_matches (match_type, confidence DESC);

-- =============================================================================
-- SOURCE OVERLAP MATRIX (Capture-recapture: Lincoln-Petersen validation)
-- =============================================================================
CREATE TABLE source_overlap_matrix (
    id                BIGSERIAL PRIMARY KEY,
    country           CHAR(2) NOT NULL,
    source_a          TEXT NOT NULL,
    source_b          TEXT NOT NULL,
    overlap_count     INT NOT NULL,
    only_a_count      INT NOT NULL,
    only_b_count      INT NOT NULL,
    lincoln_petersen_n NUMERIC(14,2),
    chapman_n         NUMERIC(14,2),
    chapman_var       NUMERIC(20,2),
    ci_lower          NUMERIC(14,2),
    ci_upper          NUMERIC(14,2),
    capture_rate_a    NUMERIC(5,4),
    capture_rate_b    NUMERIC(5,4),
    computed_at       TIMESTAMPTZ DEFAULT NOW()
) WITH (fillfactor = 90);

CREATE INDEX idx_overlap_country ON source_overlap_matrix (country);

COMMIT;
