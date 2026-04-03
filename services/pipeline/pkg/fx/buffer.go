// Package fx provides the Banker's Buffer FX converter for Phase 4 pipeline.
// Fail-closed: unknown currency returns error, vehicle DESTROYED.
package fx

import (
	"context"
	"fmt"
	"log/slog"
	"strconv"
	"sync"

	"github.com/redis/go-redis/v9"
)

const fxBufferKey = "fx_buffer"

// Buffer holds FX multipliers from Redis for currency-to-EUR conversion.
type Buffer struct {
	rdb   *redis.Client
	cache sync.Map // currency (string) -> multiplier (float64)
}

// New creates a new FX buffer. Call Refresh at startup and periodically.
func New(rdb *redis.Client) *Buffer {
	return &Buffer{rdb: rdb}
}

// ToEUR converts amount from the given currency to EUR using the multiplier.
// Checks local cache first, then Redis. Unknown currency returns error — fail-closed.
func (b *Buffer) ToEUR(ctx context.Context, amount float64, currency string) (float64, error) {
	mult, err := b.multiplier(ctx, currency)
	if err != nil {
		return 0, err
	}
	return amount * mult, nil
}

func (b *Buffer) multiplier(ctx context.Context, currency string) (float64, error) {
	if v, ok := b.cache.Load(currency); ok {
		return v.(float64), nil
	}
	mult, err := b.rdb.HGet(ctx, fxBufferKey, currency).Result()
	if err == redis.Nil {
		slog.Error("phase4: fx buffer unknown currency",
			"currency", currency)
		return 0, fmt.Errorf("fx buffer: unknown currency %s — vehicle DESTROYED", currency)
	}
	if err != nil {
		slog.Error("phase4: fx buffer hget failed",
			"currency", currency,
			"error", err)
		return 0, fmt.Errorf("fx buffer hget: %w", err)
	}
	multF, err := strconv.ParseFloat(mult, 64)
	if err != nil {
		slog.Error("phase4: fx buffer invalid multiplier",
			"currency", currency,
			"value", mult,
			"error", err)
		return 0, fmt.Errorf("fx buffer invalid multiplier for %s: %w", currency, err)
	}
	b.cache.Store(currency, multF)
	return multF, nil
}

// Refresh loads the full fx_buffer hash from Redis into the local cache.
// Call once at startup and then periodically (e.g. hourly).
func (b *Buffer) Refresh(ctx context.Context) error {
	data, err := b.rdb.HGetAll(ctx, fxBufferKey).Result()
	if err != nil {
		slog.Error("phase4: fx buffer refresh failed",
			"error", err)
		return fmt.Errorf("fx buffer refresh: %w", err)
	}
	b.cache.Range(func(key, _ interface{}) bool {
		b.cache.Delete(key)
		return true
	})
	for currency, multStr := range data {
		multF, err := strconv.ParseFloat(multStr, 64)
		if err != nil {
			slog.Error("phase4: fx buffer invalid multiplier during refresh",
				"currency", currency,
				"value", multStr,
				"error", err)
			return fmt.Errorf("fx buffer invalid multiplier for %s: %w", currency, err)
		}
		b.cache.Store(currency, multF)
	}
	return nil
}
