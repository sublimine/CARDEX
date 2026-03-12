// Package quote implements HMAC-authenticated quote generation for Phase 6.
package quote

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strconv"
	"time"

	"github.com/redis/go-redis/v9"
)

const vehicleStatePrefix = "vehicle_state:"

// Quote holds a generated quote with HMAC-authenticated ID.
type Quote struct {
	ID          string
	VehicleHash string
	NLCEUR      float64
	GeneratedAt time.Time
	ExpiresAt   time.Time
}

// QuoteStore abstracts Redis storage for quotes. Implemented by redis adapter; mock for tests.
type QuoteStore interface {
	Store(ctx context.Context, vehicleHash, quoteID string, nlc float64, ts, expires time.Time, ttl time.Duration) error
	Load(ctx context.Context, vehicleHash string) (quoteID string, nlc float64, expires time.Time, err error)
}

// redisQuoteStore adapts redis.Client to QuoteStore.
type redisQuoteStore struct {
	rdb *redis.Client
}

func (r *redisQuoteStore) Store(ctx context.Context, vehicleHash, quoteID string, nlc float64, ts, expires time.Time, ttl time.Duration) error {
	key := vehicleStatePrefix + vehicleHash
	nlcStr := strconv.FormatFloat(nlc, 'f', -1, 64)
	tsStr := strconv.FormatInt(ts.Unix(), 10)
	expiresStr := strconv.FormatInt(expires.Unix(), 10)
	pipe := r.rdb.Pipeline()
	pipe.HSet(ctx, key, "quote_id", quoteID, "nlc", nlcStr, "ts", tsStr, "expires", expiresStr)
	pipe.Expire(ctx, key, ttl)
	if _, err := pipe.Exec(ctx); err != nil {
		return fmt.Errorf("quote store: %w", err)
	}
	return nil
}

func (r *redisQuoteStore) Load(ctx context.Context, vehicleHash string) (string, float64, time.Time, error) {
	key := vehicleStatePrefix + vehicleHash
	data, err := r.rdb.HMGet(ctx, key, "quote_id", "nlc", "expires").Result()
	if err != nil {
		return "", 0, time.Time{}, fmt.Errorf("quote load: %w", err)
	}
	if data[0] == nil || data[1] == nil || data[2] == nil {
		return "", 0, time.Time{}, fmt.Errorf("quote: vehicle state not found")
	}
	quoteID, _ := data[0].(string)
	nlcStr, _ := data[1].(string)
	expiresStr, _ := data[2].(string)
	nlc, err := strconv.ParseFloat(nlcStr, 64)
	if err != nil {
		return "", 0, time.Time{}, fmt.Errorf("quote: invalid nlc: %w", err)
	}
	expiresUnix, err := strconv.ParseInt(expiresStr, 10, 64)
	if err != nil {
		return "", 0, time.Time{}, fmt.Errorf("quote: invalid expires: %w", err)
	}
	expires := time.Unix(expiresUnix, 0)
	return quoteID, nlc, expires, nil
}

// QuoteGenerator generates and verifies HMAC-authenticated quotes.
type QuoteGenerator struct {
	secret string
	store QuoteStore
	ttl   time.Duration
}

// New creates a QuoteGenerator with the given secret, Redis client, and TTL.
func New(secret string, rdb *redis.Client, ttl time.Duration) *QuoteGenerator {
	return &QuoteGenerator{
		secret: secret,
		store:  &redisQuoteStore{rdb: rdb},
		ttl:    ttl,
	}
}

// NewWithStore creates a QuoteGenerator with explicit store (for testing).
func NewWithStore(secret string, store QuoteStore, ttl time.Duration) *QuoteGenerator {
	return &QuoteGenerator{
		secret: secret,
		store:  store,
		ttl:    ttl,
	}
}

// Generate creates a new quote and stores it in Redis.
func (g *QuoteGenerator) Generate(ctx context.Context, vehicleHash string, nlcEUR float64) (Quote, error) {
	now := time.Now()
	expires := now.Add(g.ttl)
	ts := now.Unix()
	input := fmt.Sprintf("%s|%.2f|%d", vehicleHash, nlcEUR, ts)
	mac := hmac.New(sha256.New, []byte(g.secret))
	mac.Write([]byte(input))
	quoteID := hex.EncodeToString(mac.Sum(nil))

	if err := g.store.Store(ctx, vehicleHash, quoteID, nlcEUR, now, expires, g.ttl); err != nil {
		return Quote{}, err
	}

	return Quote{
		ID:          quoteID,
		VehicleHash: vehicleHash,
		NLCEUR:      nlcEUR,
		GeneratedAt: now,
		ExpiresAt:   expires,
	}, nil
}

// Verify checks the quote ID against Redis and returns the NLC if valid.
func (g *QuoteGenerator) Verify(ctx context.Context, vehicleHash string, quoteID string) (float64, error) {
	storedID, nlc, expires, err := g.store.Load(ctx, vehicleHash)
	if err != nil {
		return 0, err
	}
	if time.Now().After(expires) {
		return 0, fmt.Errorf("quote: expired")
	}
	if !hmac.Equal([]byte(storedID), []byte(quoteID)) {
		return 0, fmt.Errorf("quote: mismatch")
	}
	return nlc, nil
}
