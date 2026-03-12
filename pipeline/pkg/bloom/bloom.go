// Package bloom provides a RedisBloom wrapper for vehicle fingerprint deduplication.
// Fingerprints are SHA-256 hashes computed externally (e.g. VIN + lowercase(color) + mileage_km).
package bloom

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/redis/go-redis/v9"
)

// Bloom wraps RedisBloom for fingerprint existence checks and adds.
type Bloom struct {
	rdb *redis.Client
	key string
}

// New creates a new Bloom filter wrapper.
func New(rdb *redis.Client, key string) *Bloom {
	return &Bloom{rdb: rdb, key: key}
}

// Exists returns true if the fingerprint may exist in the Bloom filter, false if it definitely does not.
// Fingerprint is the hex-encoded SHA-256 (64 chars) computed externally.
func (b *Bloom) Exists(ctx context.Context, fingerprint string) (bool, error) {
	result, err := b.rdb.Do(ctx, "BF.EXISTS", b.key, fingerprint).Bool()
	if err != nil {
		slog.Error("phase4: bloom exists failed",
			"key", b.key,
			"error", err)
		return false, fmt.Errorf("bloom exists: %w", err)
	}
	return result, nil
}

// Add adds the fingerprint to the Bloom filter.
// Fingerprint is the hex-encoded SHA-256 (64 chars) computed externally.
func (b *Bloom) Add(ctx context.Context, fingerprint string) error {
	_, err := b.rdb.Do(ctx, "BF.ADD", b.key, fingerprint).Result()
	if err != nil {
		slog.Error("phase4: bloom add failed",
			"key", b.key,
			"error", err)
		return fmt.Errorf("bloom add: %w", err)
	}
	return nil
}
