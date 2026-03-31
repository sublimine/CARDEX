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
-- Price History (per-listing price changes — Diff Scraping feed)
-- =============================================================================
CREATE TABLE cardex.price_history (
    vehicle_ulid    String,
    vin             String,
    event_date      DateTime64(3),
    old_price_eur   Float64,
    new_price_eur   Float64,
    delta_pct       Float32,
    source_platform LowCardinality(String),
    source_country  LowCardinality(FixedString(2)),
    make            LowCardinality(String),
    model           LowCardinality(String),
    year            UInt16
) ENGINE = MergeTree()
ORDER BY (vehicle_ulid, event_date)
PARTITION BY toYYYYMM(event_date)
TTL toDate(event_date) + INTERVAL 3 YEAR DELETE;

-- =============================================================================
-- Price Index (CARDEX Index — computed nightly by scheduler)
-- Extended with year and mileage band for finer granularity
-- =============================================================================
CREATE TABLE cardex.price_index (
    index_date      Date,
    make            LowCardinality(String),
    model           LowCardinality(String),
    year            UInt16,
    mileage_band    LowCardinality(String),  -- '0-50k','50-100k','100-150k','150k+'
    country         LowCardinality(FixedString(2)),
    h3_res4         String,
    -- OHLCV-style: open=p10, close=median, high=p90, low=p5, volume=count
    p5_eur          Float64,
    p10_eur         Float64,
    p25_eur         Float64,
    median_eur      Float64,
    p75_eur         Float64,
    p90_eur         Float64,
    p95_eur         Float64,
    avg_eur         Float64,
    volume          UInt32,
    avg_days_on_market Float32,
    median_dom      Float32,
    computed_at     DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(computed_at)
ORDER BY (index_date, make, model, year, mileage_band, country)
PARTITION BY toYYYYMM(index_date)
TTL index_date + INTERVAL 5 YEAR DELETE;

-- =============================================================================
-- Market Depth (Order Book for Cars — price tier distribution)
-- Populated nightly by scheduler. Answers: "how many BMW 320d listed at 15k-20k in DE?"
-- =============================================================================
CREATE TABLE cardex.market_depth (
    snapshot_date   Date,
    make            LowCardinality(String),
    model           LowCardinality(String),
    year_from       UInt16,
    year_to         UInt16,
    country         LowCardinality(FixedString(2)),
    price_tier_eur  UInt32,           -- lower bound of 1 000 EUR bucket (e.g. 15000 = 15k-16k)
    listing_count   UInt32,
    avg_mileage_km  Float32,
    avg_dom         Float32           -- average days on market in this tier
) ENGINE = ReplacingMergeTree(snapshot_date)
ORDER BY (snapshot_date, make, model, year_from, year_to, country, price_tier_eur)
PARTITION BY toYYYYMM(snapshot_date)
TTL snapshot_date + INTERVAL 2 YEAR DELETE
SETTINGS index_granularity = 8192;

-- =============================================================================
-- Demand Signals (search/alert activity — proxy for buyer interest)
-- Written by api service whenever users search or create price alerts
-- =============================================================================
CREATE TABLE cardex.demand_signals (
    signal_date     Date,
    make            LowCardinality(String),
    model           LowCardinality(String),
    country         LowCardinality(FixedString(2)),
    signal_type     LowCardinality(String),  -- 'SEARCH','ALERT_CREATED','DETAIL_VIEW','SHARE'
    count           UInt32
) ENGINE = SummingMergeTree(count)
ORDER BY (signal_date, make, model, country, signal_type)
PARTITION BY toYYYYMM(signal_date)
TTL signal_date + INTERVAL 1 YEAR DELETE
SETTINGS index_granularity = 8192;

-- =============================================================================
-- Days-On-Market Distribution (per model/country — updated nightly)
-- =============================================================================
CREATE TABLE cardex.dom_distribution (
    snapshot_date   Date,
    make            LowCardinality(String),
    model           LowCardinality(String),
    country         LowCardinality(FixedString(2)),
    p10_dom         Float32,
    p25_dom         Float32,
    median_dom      Float32,
    p75_dom         Float32,
    p90_dom         Float32,
    avg_dom         Float32,
    sample_size     UInt32,
    computed_at     DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(computed_at)
ORDER BY (snapshot_date, make, model, country)
PARTITION BY toYYYYMM(snapshot_date)
TTL snapshot_date + INTERVAL 2 YEAR DELETE
SETTINGS index_granularity = 8192;

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

-- Platform coverage: how many listings per platform per country (updated on insert)
CREATE MATERIALIZED VIEW cardex.mv_platform_coverage
ENGINE = SummingMergeTree()
ORDER BY (day, source_platform, origin_country, make)
AS SELECT
    toDate(first_seen_at)       AS day,
    source_platform,
    origin_country,
    make,
    count()                     AS listing_count,
    countIf(sold_at IS NOT NULL) AS sold_count,
    avg(days_on_market)         AS avg_dom
FROM cardex.vehicle_inventory
GROUP BY day, source_platform, origin_country, make;

-- Price volatility: 30-day rolling coefficient of variation per model/country
-- (stddev / mean — higher = more price negotiation room)
CREATE MATERIALIZED VIEW cardex.mv_price_volatility
ENGINE = ReplacingMergeTree()
ORDER BY (week, make, model, country)
AS SELECT
    toStartOfWeek(toDate(first_seen_at))            AS week,
    make,
    model,
    origin_country                                   AS country,
    stddevPop(net_landed_cost_eur)                  AS price_stddev,
    avg(net_landed_cost_eur)                        AS price_avg,
    if(avg(net_landed_cost_eur) > 0,
       stddevPop(net_landed_cost_eur) / avg(net_landed_cost_eur),
       0)                                            AS volatility_coeff,
    count()                                          AS sample_size
FROM cardex.vehicle_inventory
WHERE net_landed_cost_eur > 0
GROUP BY week, make, model, origin_country;

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

-- =============================================================================
-- TradingCar — Price Candles (OHLCV for car model+year+country "tickers")
-- Computed nightly by scheduler from vehicle_inventory
-- open = p10, high = p90, low = p5, close = median (same as TradingView OHLC)
-- =============================================================================
CREATE TABLE IF NOT EXISTS cardex.price_candles (
    period_start    Date,
    period_type     LowCardinality(String),  -- 'W' (week), 'M' (month)
    make            LowCardinality(String),
    model           LowCardinality(String),
    year            UInt16,
    country         LowCardinality(FixedString(2)),
    fuel_type       LowCardinality(String),
    open_eur        Float64,
    high_eur        Float64,
    low_eur         Float64,
    close_eur       Float64,
    volume          UInt32,         -- listing count
    avg_mileage_km  Float32,
    avg_dom         Float32,        -- avg days on market = liquidity proxy
    computed_at     DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(computed_at)
ORDER BY (period_start, period_type, make, model, year, country, fuel_type)
PARTITION BY toYYYYMM(period_start)
TTL period_start + INTERVAL 10 YEAR DELETE
SETTINGS index_granularity = 8192;

-- Ticker metadata (top 200 most liquid tickers pre-computed)
CREATE TABLE IF NOT EXISTS cardex.ticker_stats (
    ticker_id       String,   -- e.g. "BMW_3-Series_2020_DE_Gasoline"
    make            LowCardinality(String),
    model           LowCardinality(String),
    year            UInt16,
    country         LowCardinality(FixedString(2)),
    fuel_type       LowCardinality(String),
    last_price_eur  Float64,
    change_1w_pct   Float32,
    change_1m_pct   Float32,
    change_3m_pct   Float32,
    volume_30d      UInt32,
    avg_dom_30d     Float32,
    liquidity_score Float32,
    updated_at      DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY ticker_id
SETTINGS index_granularity = 8192;

-- =============================================================================
-- Arbitrage Opportunities (computed hourly by arbitrage scanner)
-- =============================================================================
CREATE TABLE IF NOT EXISTS cardex.arbitrage_opportunities (
    opportunity_id  String,        -- UUID-like deterministic hash
    scanned_at      DateTime DEFAULT now(),
    opportunity_type LowCardinality(String),  -- PRICE_DIFF|BPM_EXPORT|EV_SUBSIDY|SEASONAL|DISTRESSED|CLASSIC
    make            LowCardinality(String),
    model           LowCardinality(String),
    year            UInt16,
    fuel_type       LowCardinality(String),
    origin_country  LowCardinality(FixedString(2)),
    dest_country    LowCardinality(FixedString(2)),
    origin_median_eur Float64,
    dest_median_eur   Float64,
    nlc_estimate_eur  Float64,     -- logistics + tax
    gross_margin_eur  Float64,     -- dest_median - origin_median - nlc
    margin_pct        Float32,     -- gross_margin / origin_median * 100
    confidence_score  Float32,     -- 0-1, based on sample size + recency
    sample_size_origin UInt32,     -- listings used for origin median
    sample_size_dest   UInt32,
    co2_gkm           UInt16,      -- relevant for BPM/IEDMT calculation
    bpm_refund_eur    Float64,     -- NL BPM refund estimate (0 if not applicable)
    iedmt_eur         Float64,     -- ES IEDMT estimate (0 if not applicable)
    malus_eur         Float64,     -- FR Malus estimate (0 if not applicable)
    example_listing_url String,    -- one representative listing URL
    status            LowCardinality(String) DEFAULT 'ACTIVE'  -- ACTIVE|EXPIRED|BOOKED
) ENGINE = ReplacingMergeTree(scanned_at)
ORDER BY (opportunity_id)
PARTITION BY toYYYYMM(scanned_at)
TTL scanned_at + INTERVAL 90 DAY DELETE
SETTINGS index_granularity = 8192;

-- Route performance tracking (for learning which routes work)
CREATE TABLE IF NOT EXISTS cardex.arbitrage_route_stats (
    route_key       String,        -- "DE_ES_BMW_3-Series_Gasoline"
    origin_country  LowCardinality(FixedString(2)),
    dest_country    LowCardinality(FixedString(2)),
    make            LowCardinality(String),
    model_family    LowCardinality(String),  -- "3 Series" → "3 Series" (group variants)
    fuel_type       LowCardinality(String),
    avg_margin_eur  Float64,
    avg_margin_pct  Float32,
    opportunity_count UInt32,
    avg_confidence  Float32,
    last_updated    DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(last_updated)
ORDER BY route_key
SETTINGS index_granularity = 8192;
