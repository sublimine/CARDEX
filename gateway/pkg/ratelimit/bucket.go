// Package ratelimit implements a token bucket rate limiter backed by Redis Lua.
package ratelimit

import (
	"context"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

// Limiter provides rate limiting via Redis Lua token bucket.
type Limiter struct {
	rdb       *redis.Client
	scriptSHA string
}

// luaScript is the token bucket Lua script.
// Loaded once at startup, then called via EVALSHA.
const luaScript = `
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
`

// New creates a new Limiter, loading the Lua script into Redis.
func New(rdb *redis.Client) *Limiter {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	sha, err := rdb.ScriptLoad(ctx, luaScript).Result()
	if err != nil {
		// Non-fatal: will fall back to EVAL on each call
		sha = ""
	}

	return &Limiter{rdb: rdb, scriptSHA: sha}
}

// Allow checks if the given key is within rate limits.
// maxTokens: bucket capacity, refillRate: tokens per second.
// Returns true if allowed, false if rate limited.
func (l *Limiter) Allow(ctx context.Context, key string, maxTokens int, refillRate float64) (bool, error) {
	now := float64(time.Now().Unix())

	var result int64
	var err error

	if l.scriptSHA != "" {
		result, err = l.rdb.EvalSha(ctx, l.scriptSHA, []string{key},
			maxTokens, refillRate, now).Int64()
	} else {
		result, err = l.rdb.Eval(ctx, luaScript, []string{key},
			maxTokens, refillRate, now).Int64()
	}

	if err != nil {
		return false, fmt.Errorf("ratelimit: lua eval failed: %w", err)
	}

	return result == 1, nil
}
