package l1

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/redis/go-redis/v9"
)

const dictKey = "dict:l1_tax"

// Result is a cached tax classification.
type Result struct {
	TaxStatus  string  `json:"tax_status"`
	Confidence float64 `json:"confidence"`
}

// Cache provides L1 exact-match lookups on vehicle ULID.
type Cache struct {
	rdb *redis.Client
}

// NewCache creates an L1 cache backed by Redis HASH.
func NewCache(rdb *redis.Client) *Cache {
	return &Cache{rdb: rdb}
}

// Get retrieves a cached classification. Returns (result, true) on hit.
func (c *Cache) Get(ctx context.Context, vehicleULID string) (Result, bool) {
	val, err := c.rdb.HGet(ctx, dictKey, vehicleULID).Result()
	if err != nil {
		return Result{}, false
	}
	var r Result
	if err := json.Unmarshal([]byte(val), &r); err != nil {
		return Result{}, false
	}
	return r, true
}

// Set stores a classification result.
func (c *Cache) Set(ctx context.Context, vehicleULID string, r Result) error {
	data, err := json.Marshal(r)
	if err != nil {
		return fmt.Errorf("l1: marshal: %w", err)
	}
	return c.rdb.HSet(ctx, dictKey, vehicleULID, string(data)).Err()
}

// Size returns the number of cached classifications.
func (c *Cache) Size(ctx context.Context) (int64, error) {
	return c.rdb.HLen(ctx, dictKey).Result()
}
