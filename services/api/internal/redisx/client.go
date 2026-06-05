// Package redisx wraps the Redis client with the three concerns the API needs:
// API-key lookup, per-key rate limiting (fixed-window), and a response cache.
package redisx

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"

	"cardex.eu/api/internal/apikeys"
)

// ErrKeyNotFound is returned by LookupAPIKey when the key has no Redis entry.
var ErrKeyNotFound = errors.New("api key not found")

// Client is a thin wrapper over *redis.Client with domain helpers.
type Client struct {
	rdb *redis.Client
}

// New creates a Redis client. It does not dial until the first command; call
// Ping to verify connectivity at startup.
func New(addr, password string, db int) *Client {
	return &Client{rdb: redis.NewClient(&redis.Options{
		Addr:         addr,
		Password:     password,
		DB:           db,
		DialTimeout:  5 * time.Second,
		ReadTimeout:  3 * time.Second,
		WriteTimeout: 3 * time.Second,
		PoolSize:     10,
	})}
}

// Ping verifies connectivity.
func (c *Client) Ping(ctx context.Context) error {
	return c.rdb.Ping(ctx).Err()
}

// Close releases the connection pool.
func (c *Client) Close() error { return c.rdb.Close() }

// apiKeyRedisKey namespaces an API key in Redis.
func apiKeyRedisKey(key string) string { return "apikey:" + key }

// LookupAPIKey fetches the metadata for a raw API key. It returns ErrKeyNotFound
// when the key is absent.
func (c *Client) LookupAPIKey(ctx context.Context, key string) (*apikeys.APIKey, error) {
	raw, err := c.rdb.Get(ctx, apiKeyRedisKey(key)).Bytes()
	if errors.Is(err, redis.Nil) {
		return nil, ErrKeyNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("redis get apikey: %w", err)
	}
	var ak apikeys.APIKey
	if err := json.Unmarshal(raw, &ak); err != nil {
		return nil, fmt.Errorf("decode apikey: %w", err)
	}
	return &ak, nil
}

// PutAPIKey provisions or updates an API key (used by seeding/admin tooling).
func (c *Client) PutAPIKey(ctx context.Context, key string, ak apikeys.APIKey) error {
	raw, err := json.Marshal(ak)
	if err != nil {
		return fmt.Errorf("encode apikey: %w", err)
	}
	if err := c.rdb.Set(ctx, apiKeyRedisKey(key), raw, 0).Err(); err != nil {
		return fmt.Errorf("redis set apikey: %w", err)
	}
	return nil
}

// rateLimitScript atomically increments the window counter and sets its TTL on
// first use. Returns the post-increment count.
var rateLimitScript = redis.NewScript(`
local c = redis.call('INCR', KEYS[1])
if c == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return c
`)

// RateResult reports the outcome of a rate-limit check.
type RateResult struct {
	Allowed   bool
	Limit     int
	Remaining int
	// ResetSeconds is the seconds until the current window resets.
	ResetSeconds int
}

// Allow applies a fixed-window (60s) rate limit to key. A limit <= 0 means
// unlimited and always allows. On Redis error it fails open (allows) so a Redis
// outage degrades to no-limit rather than a hard outage — callers log the error.
func (c *Client) Allow(ctx context.Context, key string, limitPerMin int) (RateResult, error) {
	if limitPerMin <= 0 {
		return RateResult{Allowed: true, Limit: limitPerMin, Remaining: -1, ResetSeconds: 0}, nil
	}
	now := time.Now().Unix()
	bucket := now / 60
	resetIn := int(60 - (now % 60))
	rkey := fmt.Sprintf("ratelimit:%s:%d", key, bucket)

	count, err := rateLimitScript.Run(ctx, c.rdb, []string{rkey}, 60).Int()
	if err != nil {
		// Fail open: do not let a Redis blip take down the API.
		return RateResult{Allowed: true, Limit: limitPerMin, Remaining: -1, ResetSeconds: resetIn}, err
	}
	remaining := limitPerMin - count
	if remaining < 0 {
		remaining = 0
	}
	return RateResult{
		Allowed:      count <= limitPerMin,
		Limit:        limitPerMin,
		Remaining:    remaining,
		ResetSeconds: resetIn,
	}, nil
}

// GetCached returns a cached value and whether it was present.
func (c *Client) GetCached(ctx context.Context, key string) ([]byte, bool, error) {
	raw, err := c.rdb.Get(ctx, "cache:"+key).Bytes()
	if errors.Is(err, redis.Nil) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	return raw, true, nil
}

// SetCached stores a value with a TTL. Errors are returned but are non-fatal to
// callers (cache is best-effort).
func (c *Client) SetCached(ctx context.Context, key string, val []byte, ttl time.Duration) error {
	return c.rdb.Set(ctx, "cache:"+key, val, ttl).Err()
}

// alertNotifiedTTL bounds how long alert notification state survives; well beyond
// any realistic evaluation cadence, and self-cleaning for deleted alerts.
const alertNotifiedTTL = 90 * 24 * time.Hour

// AlertSignature returns the last notification signature recorded for an alert
// (empty string when none).
//
// Per ADR-0006, alert notification state is kept in Redis rather than as mutable
// PostgreSQL columns. The signature dedups notifications: the evaluator only
// re-notifies when the opportunity set changes.
func (c *Client) AlertSignature(ctx context.Context, alertID string) (string, error) {
	sig, err := c.rdb.Get(ctx, "alertsig:"+alertID).Result()
	if errors.Is(err, redis.Nil) {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	return sig, nil
}

// SetAlertNotified records that an alert fired with the given signature at t.
func (c *Client) SetAlertNotified(ctx context.Context, alertID, signature string, t time.Time) error {
	pipe := c.rdb.TxPipeline()
	pipe.Set(ctx, "alertsig:"+alertID, signature, alertNotifiedTTL)
	pipe.Set(ctx, "alertfired:"+alertID, t.UTC().Format(time.RFC3339), alertNotifiedTTL)
	_, err := pipe.Exec(ctx)
	return err
}

// AlertLastFired returns the last fired time for an alert, or the zero time.
func (c *Client) AlertLastFired(ctx context.Context, alertID string) (time.Time, error) {
	v, err := c.rdb.Get(ctx, "alertfired:"+alertID).Result()
	if errors.Is(err, redis.Nil) {
		return time.Time{}, nil
	}
	if err != nil {
		return time.Time{}, err
	}
	return time.Parse(time.RFC3339, v)
}

// DeleteAlertState removes an alert's notification state (best effort, on delete).
func (c *Client) DeleteAlertState(ctx context.Context, alertID string) error {
	return c.rdb.Del(ctx, "alertsig:"+alertID, "alertfired:"+alertID).Err()
}
