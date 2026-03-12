-- =============================================================================
-- CARDEX ClickHouse — OLAP Schema
-- Execute on: Nodo 01/05 (XFS Direct I/O, CCD0)
-- =============================================================================

CREATE DATABASE IF NOT EXISTS cardex;
CREATE DATABASE IF NOT EXISTS cardex_forensics;

-- =============================================================================
-- Vehicle Inventory (replicated from PostgreSQL via MaterializedPostgreSQL)
-- Zero-PII: no VIN, no raw_description, no source_id, no thumb_url
-- =============================================================================
CREATE TABLE cardex.vehicle_inventory (
    vehicle_ulid          String,
    fingerprint_sha256    String,
    source_platform       LowCardinality(String),
    ingestion_channel     LowCardinality(String),
    make                  LowCardinality(String),
    model                 LowCardinality(String),
    variant               String,
    year                  UInt16,
    mileage_km            UInt32,
    color                 LowCardinality(String),
    fuel_type             LowCardinality(String),
    transmission          LowCardinality(String),
    co2_gkm               UInt16,
    power_kw              UInt16,
    origin_country        LowCardinality(FixedString(2)),
    price_raw             Float64,
    currency_raw          FixedString(3),
    gross_physical_cost_eur Float64,
    net_landed_cost_eur   Float64,
    logistics_cost_eur    Float64,
    tax_amount_eur        Float64,
    tax_status            LowCardinality(String),
    tax_confidence        Float32,
    legal_status          LowCardinality(String),
    risk_score            Float32,
    liquidity_score       Float32,
    cardex_score          Float32,
    sdi_alert             UInt8,
    h3_index_res4         String,
    h3_index_res7         String,
    days_on_market        UInt16,
    first_seen_at         DateTime64(3),
    last_updated_at       DateTime64(3),
    sold_at               Nullable(DateTime64(3)),
    lifecycle_status      LowCardinality(String)
) ENGINE = ReplacingMergeTree(last_updated_at)
ORDER BY (make, model, vehicle_ulid)
PARTITION BY toYYYYMM(first_seen_at)
TTL first_seen_at + INTERVAL 2 YEAR DELETE
SETTINGS index_granularity = 8192;

-- =============================================================================
-- Mileage History (Odometer Rollback Detection — Phase 7)
-- =============================================================================
CREATE TABLE cardex_forensics.mileage_history (
    vin             String,
    recorded_date   Date,
    mileage         UInt32,
    country         LowCardinality(String),
    source          LowCardinality(String),
    ingested_at     DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (vin, recorded_date)
PARTITION BY toYYYYMM(recorded_date)
SETTINGS index_granularity = 8192;

-- =============================================================================
-- Salvage Ledger (Accident/Total Loss records — Phase 7)
-- =============================================================================
CREATE TABLE cardex_forensics.salvage_ledger (
    vin             String,
    event_date      Date,
    event_type      LowCardinality(String),
    severity        LowCardinality(String),
    source          LowCardinality(String),
    country         LowCardinality(String),
    description     String,
    ingested_at     DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (vin, event_date)
PARTITION BY toYYYYMM(event_date);

-- =============================================================================
-- Price Index (CARDEX Index — Phase 6 aggregation)
-- =============================================================================
CREATE TABLE cardex.price_index (
    index_date      Date,
    make            LowCardinality(String),
    model           LowCardinality(String),
    country         LowCardinality(FixedString(2)),
    h3_res4         String,
    avg_nlc_eur     Float64,
    median_nlc_eur  Float64,
    p10_nlc_eur     Float64,
    p90_nlc_eur     Float64,
    volume          UInt32,
    avg_days_on_market Float32,
    computed_at     DateTime DEFAULT now()
) ENGINE = SummingMergeTree()
ORDER BY (index_date, make, model, country)
PARTITION BY toYYYYMM(index_date);

-- =============================================================================
-- Materialized Views for common analytics
-- =============================================================================

-- Daily volume by source platform
CREATE MATERIALIZED VIEW cardex.mv_daily_volume
ENGINE = SummingMergeTree()
ORDER BY (day, source_platform, origin_country)
AS SELECT
    toDate(first_seen_at) AS day,
    source_platform,
    origin_country,
    count() AS vehicle_count,
    avg(net_landed_cost_eur) AS avg_nlc,
    avg(cardex_score) AS avg_score
FROM cardex.vehicle_inventory
GROUP BY day, source_platform, origin_country;

-- Tax status distribution
CREATE MATERIALIZED VIEW cardex.mv_tax_distribution
ENGINE = SummingMergeTree()
ORDER BY (day, tax_status, origin_country)
AS SELECT
    toDate(first_seen_at) AS day,
    tax_status,
    origin_country,
    count() AS cnt
FROM cardex.vehicle_inventory
GROUP BY day, tax_status, origin_country;

-- =============================================================================
-- Forensic Queries (stored as named queries for operational use)
-- =============================================================================

-- Odometer rollback detection:
-- SELECT vin, max(mileage) as historical_max
-- FROM cardex_forensics.mileage_history
-- WHERE vin = {vin:String}
--   AND mileage > {current_mileage:UInt32} + 500
-- GROUP BY vin
-- HAVING historical_max > 0;
