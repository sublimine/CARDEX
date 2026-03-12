package cascade

import (
	"context"
	"testing"

	"github.com/redis/go-redis/v9"

	"cardex/neural/internal/l1"
)

func TestPrivateSellerOverride(t *testing.T) {
	rdb := redis.NewClient(&redis.Options{Addr: "127.0.0.1:6379"})
	ctx := context.Background()

	if err := rdb.Ping(ctx).Err(); err != nil {
		t.Skip("Redis not available:", err)
	}

	l1Cache := l1.NewCache(rdb)
	classifier := NewClassifier(rdb, l1Cache, nil)

	v := classifier.Classify(ctx, VehicleInput{
		VehicleULID: "01JTEST_PRIVATE",
		SellerType:  "PRIVATE",
	})

	if v.TaxStatus != "REBU" {
		t.Fatalf("expected REBU for PRIVATE seller, got %s", v.TaxStatus)
	}
	if v.Tier != "OVERRIDE" {
		t.Fatalf("expected OVERRIDE tier, got %s", v.Tier)
	}
	if v.Confidence != 1.0 {
		t.Fatalf("expected 1.0 confidence, got %f", v.Confidence)
	}
}

func TestL1Hit(t *testing.T) {
	rdb := redis.NewClient(&redis.Options{Addr: "127.0.0.1:6379"})
	ctx := context.Background()

	if err := rdb.Ping(ctx).Err(); err != nil {
		t.Skip("Redis not available:", err)
	}

	// Clean
	rdb.Del(ctx, "dict:l1_tax")
	defer rdb.Del(ctx, "dict:l1_tax")

	l1Cache := l1.NewCache(rdb)
	classifier := NewClassifier(rdb, l1Cache, nil)

	// Pre-populate L1
	l1Cache.Set(ctx, "01JTEST_L1HIT", l1.Result{
		TaxStatus:  "DEDUCTIBLE",
		Confidence: 0.99,
	})

	v := classifier.Classify(ctx, VehicleInput{
		VehicleULID: "01JTEST_L1HIT",
		SellerType:  "DEALER",
	})

	if v.TaxStatus != "DEDUCTIBLE" {
		t.Fatalf("expected DEDUCTIBLE from L1, got %s", v.TaxStatus)
	}
	if v.Tier != "L1" {
		t.Fatalf("expected L1 tier, got %s", v.Tier)
	}
}

func TestL3Dispatch(t *testing.T) {
	rdb := redis.NewClient(&redis.Options{Addr: "127.0.0.1:6379"})
	ctx := context.Background()

	if err := rdb.Ping(ctx).Err(); err != nil {
		t.Skip("Redis not available:", err)
	}

	// Clean
	rdb.Del(ctx, "dict:l1_tax", L3PendingStream)
	defer rdb.Del(ctx, "dict:l1_tax", L3PendingStream)

	l1Cache := l1.NewCache(rdb)
	classifier := NewClassifier(rdb, l1Cache, nil)

	v := classifier.Classify(ctx, VehicleInput{
		VehicleULID: "01JTEST_L3",
		SellerType:  "DEALER",
		Description: "Mercedes Sprinter 316 CDI",
		Country:     "DE",
	})

	if v.TaxStatus != "REQUIRES_HUMAN_AUDIT" {
		t.Fatalf("expected REQUIRES_HUMAN_AUDIT for L3 pending, got %s", v.TaxStatus)
	}
	if v.Tier != "L3_PENDING" {
		t.Fatalf("expected L3_PENDING tier, got %s", v.Tier)
	}

	// Verify message was dispatched to stream
	streamLen, _ := rdb.XLen(ctx, L3PendingStream).Result()
	if streamLen == 0 {
		t.Fatal("expected message in stream:l3_pending")
	}
}

func TestFailClosedLowConfidence(t *testing.T) {
	rdb := redis.NewClient(&redis.Options{Addr: "127.0.0.1:6379"})
	ctx := context.Background()

	if err := rdb.Ping(ctx).Err(); err != nil {
		t.Skip("Redis not available:", err)
	}

	rdb.Del(ctx, "dict:l1_tax")
	defer rdb.Del(ctx, "dict:l1_tax")

	l1Cache := l1.NewCache(rdb)
	classifier := NewClassifier(rdb, l1Cache, nil)

	// L1 entry with LOW confidence
	l1Cache.Set(ctx, "01JTEST_LOW", l1.Result{
		TaxStatus:  "DEDUCTIBLE",
		Confidence: 0.80,
	})

	v := classifier.Classify(ctx, VehicleInput{
		VehicleULID: "01JTEST_LOW",
		SellerType:  "DEALER",
	})

	// FAIL-CLOSED: low confidence → forced audit
	if v.TaxStatus != "REQUIRES_HUMAN_AUDIT" {
		t.Fatalf("expected REQUIRES_HUMAN_AUDIT for low confidence, got %s", v.TaxStatus)
	}
}
