#!/usr/bin/env bash
# =============================================================================
# CARDEX Redis 7.2+ Initialization
# Execute on: Nodo 02 (NUMA node 0, cores 0-15)
# Requires: redis-cli, RedisBloom module loaded
# =============================================================================
set -euo pipefail

REDIS_CLI="redis-cli"
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
R="$REDIS_CLI -h $REDIS_HOST -p $REDIS_PORT"

echo "=== CARDEX Redis Bootstrap ==="

# ---------------------------------------------------------------------------
# 1. STREAMS + CONSUMER GROUPS
# ---------------------------------------------------------------------------
declare -A STREAMS=(
    ["stream:ingestion_raw"]="cg_pipeline"
    ["stream:db_write"]="cg_forensics"
    ["stream:classified"]="cg_alpha"
    ["stream:l3_pending"]="cg_qwen_workers"
    ["stream:visual_audit"]="cg_ocr_workers"
    ["stream:market_ready"]="cg_alpha"
    ["stream:market_pricing"]="cg_alpha"
    ["stream:legal_audit_pending"]="cg_gov"
    ["stream:forensic_updates"]="cg_forensics"
    ["stream:operator_events"]="cg_karma"
)

for stream in "${!STREAMS[@]}"; do
    cg="${STREAMS[$stream]}"
    # Create stream with initial entry if it doesn't exist, then create consumer group
    $R XGROUP CREATE "$stream" "$cg" 0 MKSTREAM 2>/dev/null || \
        echo "  [SKIP] $stream/$cg already exists"
    echo "  [OK] $stream → $cg"
done

# ---------------------------------------------------------------------------
# 2. BLOOM FILTER (Vehicle Deduplication — Phase 4)
# ---------------------------------------------------------------------------
# Capacity: 50M entries, False Positive rate: 0.01% (0.0001)
# Memory: ~60MB
$R BF.RESERVE bloom:vehicles 0.0001 50000000 NONSCALING 2>/dev/null || \
    echo "  [SKIP] bloom:vehicles already exists"
echo "  [OK] bloom:vehicles (50M capacity, 0.01% FP)"

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
# Atomic: verify quote_id, lock vehicle, return result
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
    return -2  -- PRICE_MISMATCH
end

local lock_key = "lock:" .. KEYS[1]
local locked = redis.call("SET", lock_key, buyer_id, "NX", "EX", lock_ttl)
if locked == false then
    return -1  -- ALREADY_LOCKED
end

redis.call("HSET", key, "locked_by", buyer_id)
return 1  -- SUCCESS
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
    return -1  -- INSUFFICIENT_CREDITS
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
    return 0  -- RATE_LIMITED
end

redis.call("HMSET", key, "tokens", new_tokens - 1, "last_refill", now)
redis.call("EXPIRE", key, 3600)
return 1  -- ALLOWED
')
echo "  [OK] Lua: rate_limiter ($RATE_LIMIT_SHA)"

# ---------------------------------------------------------------------------
# 6. CONFIGURATION VERIFICATION
# ---------------------------------------------------------------------------
echo ""
echo "=== Verification ==="
echo "Streams:  $($R KEYS 'stream:*' | wc -l) created"
echo "Bloom:    $($R BF.INFO bloom:vehicles Capacity 2>/dev/null | head -2)"
echo "FX keys:  $($R HLEN fx_buffer) currencies"
echo "Lua:      3 scripts loaded"
echo ""
echo "=== CARDEX Redis Bootstrap Complete ==="
