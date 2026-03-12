// Package stolen implements stolen vehicle detection via EUROPOL SIS-II Redis set.
package stolen

import (
	"context"
	"fmt"

	"github.com/redis/go-redis/v9"
)

const (
	stolenSetKey = "set:stolen_vins"
	source       = "EUROPOL_SIS_II"
)

// StolenResult holds the result of stolen vehicle check.
type StolenResult struct {
	Flagged bool
	Source  string
}

// StolenStore checks if a VIN is in the stolen set. Implemented by redis.Client; mock for tests.
type StolenStore interface {
	IsMember(ctx context.Context, vin string) (bool, error)
}

// redisStolenStore adapts redis.Client to StolenStore.
type redisStolenStore struct {
	rdb *redis.Client
}

func (r *redisStolenStore) IsMember(ctx context.Context, vin string) (bool, error) {
	member, err := r.rdb.SIsMember(ctx, stolenSetKey, vin).Result()
	if err != nil {
		return false, fmt.Errorf("stolen: %w", err)
	}
	return member, nil
}

// Checker checks VINs against the EUROPOL SIS-II stolen vehicle set.
type Checker struct {
	store StolenStore
}

// New creates a Checker using the given Redis client.
func New(rdb *redis.Client) *Checker {
	return &Checker{store: &redisStolenStore{rdb: rdb}}
}

// NewWithStore creates a Checker with explicit store (for testing).
func NewWithStore(store StolenStore) *Checker {
	return &Checker{store: store}
}

// Check returns whether the VIN is flagged as stolen in EUROPOL SIS-II.
func (c *Checker) Check(ctx context.Context, vin string) (StolenResult, error) {
	member, err := c.store.IsMember(ctx, vin)
	if err != nil {
		return StolenResult{}, err
	}
	if member {
		return StolenResult{Flagged: true, Source: source}, nil
	}
	return StolenResult{Flagged: false}, nil
}
