//go:build integration

package quote

import (
	"context"
	"math"
	"strings"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
)

func newIntegrationGenerator(t *testing.T) *QuoteGenerator {
	t.Helper()
	rdb := redis.NewClient(&redis.Options{
		Addr: "localhost:6379",
	})
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := rdb.Ping(ctx).Err(); err != nil {
		t.Skipf("Redis not available at localhost:6379: %v", err)
	}
	return New("integration-secret", rdb, 300*time.Second)
}

func TestQuoteGenerator_GenerateThenVerifySucceeds(t *testing.T) {
	gen := newIntegrationGenerator(t)
	ctx := context.Background()
	vehicleHash := "01HINTEGRATION01"
	nlcEUR := 25000.50

	quote, err := gen.Generate(ctx, vehicleHash, nlcEUR)
	if err != nil {
		t.Fatalf("Generate() error = %v", err)
	}
	gotNLC, err := gen.Verify(ctx, vehicleHash, quote.ID)
	if err != nil {
		t.Fatalf("Verify() error = %v", err)
	}
	if math.Abs(gotNLC-nlcEUR) > 0.01 {
		t.Errorf("Verify() nlc = %v, want %v", gotNLC, nlcEUR)
	}
}

func TestQuoteGenerator_VerifyWrongQuoteIDFails(t *testing.T) {
	gen := newIntegrationGenerator(t)
	ctx := context.Background()
	vehicleHash := "01HINTEGRATION02"
	nlcEUR := 20000.0

	_, err := gen.Generate(ctx, vehicleHash, nlcEUR)
	if err != nil {
		t.Fatalf("Generate() error = %v", err)
	}
	_, err = gen.Verify(ctx, vehicleHash, "wrong-quote-id")
	if err == nil {
		t.Fatal("Verify() expected error for wrong quote ID")
	}
	if !strings.Contains(err.Error(), "mismatch") {
		t.Errorf("Verify() error = %v, want substring 'mismatch'", err)
	}
}

func TestQuoteGenerator_VerifyNonExistentVehicleFails(t *testing.T) {
	gen := newIntegrationGenerator(t)
	ctx := context.Background()

	_, err := gen.Verify(ctx, "01HNONEXISTENT99", "any-id")
	if err == nil {
		t.Fatal("Verify() expected error for non-existent vehicle")
	}
	if !strings.Contains(err.Error(), "not found") {
		t.Errorf("Verify() error = %v, want substring 'not found'", err)
	}
}
