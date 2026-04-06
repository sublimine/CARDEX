#!/bin/sh
# =============================================================================
# CARDEX Redis 7.2+ Initialization
# Execute on: Nodo 02 (NUMA node 0, cores 0-15)
# Requires: redis-cli, RedisBloom module loaded
# =============================================================================
set -eu

REDIS_CLI="redis-cli"
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
R="$REDIS_CLI -h $REDIS_HOST -p $REDIS_PORT"

echo "=== CARDEX Redis Bootstrap ==="

# ---------------------------------------------------------------------------
# 1. STREAMS + CONSUMER GROUPS
# ---------------------------------------------------------------------------
create_stream_group() {
    stream="$1"
    cg="$2"
    $R XGROUP CREATE "$stream" "$cg" 0 MKSTREAM 2>/dev/null || \
        echo "  [SKIP] $stream/$cg already exists"
    echo "  [OK] $stream → $cg"
}

# Core pipeline
create_stream_group "stream:ingestion_raw" "cg_pipeline"
create_stream_group "stream:db_write" "cg_forensics"
create_stream_group "stream:classified" "cg_alpha"
create_stream_group "stream:forensic_updates" "cg_forensics"
# Marketplace / search sync
create_stream_group "stream:meili_sync" "cg_meili_indexer"
create_stream_group "stream:publish_jobs" "cg_multipost"
create_stream_group "stream:lead_events" "cg_crm"
create_stream_group "stream:google_maps_raw" "cg_pipeline"
# Analytics
create_stream_group "stream:price_events" "cg_price_index"
create_stream_group "stream:demand_signals" "cg_analytics"
# Legacy (retained for compatibility)
create_stream_group "stream:legal_audit_pending" "cg_gov"
create_stream_group "stream:operator_events" "cg_karma"

# ---------------------------------------------------------------------------
# 2. BLOOM FILTERS
# ---------------------------------------------------------------------------

# Vehicle identity dedup (by VIN/fingerprint) — 50M cap, ~60MB
$R BF.RESERVE bloom:vehicles 0.0001 50000000 NONSCALING 2>/dev/null || \
    echo "  [SKIP] bloom:vehicles already exists"
echo "  [OK] bloom:vehicles (50M capacity, 0.01% FP, ~60MB)"

# Listing URL dedup — prevents re-scraping identical URLs, 100M cap, ~120MB
$R BF.RESERVE bloom:listing_urls 0.0001 100000000 NONSCALING 2>/dev/null || \
    echo "  [SKIP] bloom:listing_urls already exists"
echo "  [OK] bloom:listing_urls (100M capacity, 0.01% FP, ~120MB)"

# Dealer discovery dedup (Google Maps place_id) — 5M cap, ~6MB
$R BF.RESERVE bloom:dealer_place_ids 0.001 5000000 NONSCALING 2>/dev/null || \
    echo "  [SKIP] bloom:dealer_place_ids already exists"
echo "  [OK] bloom:dealer_place_ids (5M capacity, 0.1% FP, ~6MB)"

# ---------------------------------------------------------------------------
# 3. FX BUFFER (Banker's Buffer — Phase 4)
# Populated by external FX oracle. Fail-closed if missing.
# ---------------------------------------------------------------------------
$R HSET fx_buffer \
    EUR 1.0 \
    GBP 1.17 \
    CHF 1.08 \
    SEK 0.088 \
    NOK 0.087 \
    DKK 0.134 \
    PLN 0.232 \
    CZK 0.041 \
    HUF 0.0027 \
    RON 0.201 \
    BGN 0.511 \
    HRK 0.133 \
    > /dev/null
echo "  [OK] fx_buffer (12 currencies)"

# ---------------------------------------------------------------------------
# 4. LOGISTICS WORST-CASE TABLE (Phase 6)
# EUR cost of transport from origin to any EU destination (pessimistic)
# ---------------------------------------------------------------------------
$R HSET logistics:worst_case \
    DE 800 \
    FR 1000 \
    NL 900 \
    BE 900 \
    IT 1200 \
    ES 1100 \
    AT 950 \
    PL 850 \
    CZ 900 \
    SE 1400 \
    PT 1300 \
    GB 1500 \
    > /dev/null
echo "  [OK] logistics:worst_case (12 countries)"

# ---------------------------------------------------------------------------
# 5. LUA SCRIPTS — REGISTER
# ---------------------------------------------------------------------------

# 5a. HMAC Quote Mutex (Phase 6)
QUOTE_MUTEX_SHA=$($R SCRIPT LOAD '
local key = KEYS[1]
local expected_quote = ARGV[1]
local buyer_id = ARGV[2]
local lock_ttl = tonumber(ARGV[3])

local current = redis.call("HGET", key, "quote_id")
if current == false then
    return redis.error_reply("VEHICLE_NOT_FOUND")
end
if current ~= expected_quote then
    return -2
end

local lock_key = "lock:" .. KEYS[1]
local locked = redis.call("SET", lock_key, buyer_id, "NX", "EX", lock_ttl)
if locked == false then
    return -1
end

redis.call("HSET", key, "locked_by", buyer_id)
return 1
')
echo "  [OK] Lua: quote_mutex ($QUOTE_MUTEX_SHA)"

# 5b. Credit Consumption (Anti-MiCA)
CREDIT_CONSUME_SHA=$($R SCRIPT LOAD '
local key = KEYS[1]
local cost = tonumber(ARGV[1])

local remaining = tonumber(redis.call("GET", key))
if remaining == nil then
    return redis.error_reply("NO_CREDITS")
end
if remaining < cost then
    return -1
end

local ttl = redis.call("TTL", key)
redis.call("DECRBY", key, cost)
return remaining - cost
')
echo "  [OK] Lua: credit_consume ($CREDIT_CONSUME_SHA)"

# 5c. Rate Limiter Token Bucket (Phase 3)
RATE_LIMIT_SHA=$($R SCRIPT LOAD '
local key = KEYS[1]
local max_tokens = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local data = redis.call("HMGET", key, "tokens", "last_refill")
local tokens = tonumber(data[1]) or max_tokens
local last_refill = tonumber(data[2]) or now

local elapsed = now - last_refill
local new_tokens = math.min(max_tokens, tokens + (elapsed * refill_rate))

if new_tokens < 1 then
    return 0
end

redis.call("HMSET", key, "tokens", new_tokens - 1, "last_refill", now)
redis.call("EXPIRE", key, 3600)
return 1
')
echo "  [OK] Lua: rate_limiter ($RATE_LIMIT_SHA)"

# ---------------------------------------------------------------------------
# 6. SORTED SETS — Leaderboards / Rankings
# ---------------------------------------------------------------------------

$R ZADD demand:top_models:placeholder 0 "placeholder" > /dev/null
echo "  [OK] demand:top_models (placeholder, scheduler populates nightly)"

# ---------------------------------------------------------------------------
# 7. HASH — Scraper Rate Limit Config (per domain)
# ---------------------------------------------------------------------------
$R HSET scraper:rate_limits \
    autoscout24.es  "0.3" \
    autoscout24.de  "0.3" \
    autoscout24.fr  "0.3" \
    autoscout24.nl  "0.3" \
    autoscout24.be  "0.3" \
    autoscout24.ch  "0.3" \
    mobile.de       "0.2" \
    leboncoin.fr    "0.2" \
    lacentrale.fr   "0.3" \
    coches.net      "0.3" \
    milanuncios.com "0.2" \
    wallapop.com    "0.2" \
    marktplaats.nl  "0.2" \
    2dehands.be     "0.2" \
    > /dev/null
echo "  [OK] scraper:rate_limits (14 domains configured)"

# ---------------------------------------------------------------------------
# 8. CONFIGURATION VERIFICATION
# ---------------------------------------------------------------------------
echo ""
echo "=== Verification ==="
echo "Streams:  $($R KEYS 'stream:*' | wc -l) created"
echo "Blooms:   bloom:vehicles, bloom:listing_urls, bloom:dealer_place_ids"
echo "FX keys:  $($R HLEN fx_buffer) currencies"
echo "Lua:      3 scripts loaded"
echo "Rate cfg: $($R HLEN scraper:rate_limits) domains"
echo ""
# ---------------------------------------------------------------------------
# 9. CENSUS & FRONTIER BLOOM FILTERS
# ---------------------------------------------------------------------------
echo ""
echo "--- Census & Frontier ---"
$R BF.RESERVE bloom:census_vins 0.001 20000000 NONSCALING 2>/dev/null || \
    echo "  [SKIP] bloom:census_vins already exists"
echo "  [OK] bloom:census_vins (20M capacity, 0.1% FP)"

# Stream for frontier crawl results (scrapers report back)
$R XGROUP CREATE stream:crawl_results cg_frontier 0 MKSTREAM 2>/dev/null || \
    echo "  [SKIP] stream:crawl_results/cg_frontier already exists"
echo "  [OK] stream:crawl_results → cg_frontier"

# Stream for thumbnail generation requests (pipeline → thumbgen)
$R XGROUP CREATE stream:thumb_requests cg_thumbgen 0 MKSTREAM 2>/dev/null || \
    echo "  [SKIP] stream:thumb_requests/cg_thumbgen already exists"
echo "  [OK] stream:thumb_requests → cg_thumbgen"

echo "=== CARDEX Redis Bootstrap Complete ==="
