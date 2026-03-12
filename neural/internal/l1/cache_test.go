package l1

import (
	"context"
	"testing"

	"github.com/redis/go-redis/v9"
)

func TestCacheSetGet(t *testing.T) {
	rdb := redis.NewClient(&redis.Options{Addr: "127.0.0.1:6379"})
	ctx := context.Background()

	if err := rdb.Ping(ctx).Err(); err != nil {
		t.Skip("Redis not available:", err)
	}

	// Clean up
	rdb.Del(ctx, dictKey)
	defer rdb.Del(ctx, dictKey)

	cache := NewCache(rdb)

	// Miss
	_, ok := cache.Get(ctx, "01JTEST0001")
	if ok {
		t.Fatal("expected miss on empty cache")
	}

	// Set + Hit
	err := cache.Set(ctx, "01JTEST0001", Result{TaxStatus: "DEDUCTIBLE", Confidence: 0.98})
	if err != nil {
		t.Fatal("Set failed:", err)
	}

	r, ok := cache.Get(ctx, "01JTEST0001")
	if !ok {
		t.Fatal("expected hit after Set")
	}
	if r.TaxStatus != "DEDUCTIBLE" {
		t.Fatalf("expected DEDUCTIBLE, got %s", r.TaxStatus)
	}
	if r.Confidence != 0.98 {
		t.Fatalf("expected 0.98, got %f", r.Confidence)
	}

	// Size
	size, err := cache.Size(ctx)
	if err != nil {
		t.Fatal("Size failed:", err)
	}
	if size != 1 {
		t.Fatalf("expected size 1, got %d", size)
	}
}
