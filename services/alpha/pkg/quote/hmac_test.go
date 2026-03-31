package quote

import (
	"context"
	"fmt"
	"math"
	"strings"
	"sync"
	"testing"
	"time"
)

type mockQuoteStore struct {
	mu    sync.Mutex
	data  map[string]struct {
		quoteID string
		nlc     float64
		expires time.Time
	}
}

func (m *mockQuoteStore) Store(ctx context.Context, vehicleHash, quoteID string, nlc float64, ts, expires time.Time, ttl time.Duration) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.data == nil {
		m.data = make(map[string]struct {
			quoteID string
			nlc     float64
			expires time.Time
		})
	}
	m.data[vehicleHash] = struct {
		quoteID string
		nlc     float64
		expires time.Time
	}{quoteID: quoteID, nlc: nlc, expires: expires}
	return nil
}

func (m *mockQuoteStore) Load(ctx context.Context, vehicleHash string) (string, float64, time.Time, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	v, ok := m.data[vehicleHash]
	if !ok {
		return "", 0, time.Time{}, fmt.Errorf("quote: vehicle state not found")
	}
	return v.quoteID, v.nlc, v.expires, nil
}

func TestQuoteGenerator_GenerateVerify_RoundTrip(t *testing.T) {
	mock := &mockQuoteStore{}
	gen := NewWithStore("test-secret", mock, 5*time.Minute)
	ctx := context.Background()

	vehicleHash := "01HXYZ123"
	nlcEUR := 25000.50

	quote, err := gen.Generate(ctx, vehicleHash, nlcEUR)
	if err != nil {
		t.Fatalf("Generate() error = %v", err)
	}
	if quote.ID == "" {
		t.Error("Generate() quote ID is empty")
	}
	if quote.VehicleHash != vehicleHash {
		t.Errorf("Generate() VehicleHash = %q, want %q", quote.VehicleHash, vehicleHash)
	}
	if math.Abs(quote.NLCEUR-nlcEUR) > 0.01 {
		t.Errorf("Generate() NLCEUR = %v, want %v", quote.NLCEUR, nlcEUR)
	}

	gotNLC, err := gen.Verify(ctx, vehicleHash, quote.ID)
	if err != nil {
		t.Errorf("Verify() error = %v", err)
	}
	if math.Abs(gotNLC-nlcEUR) > 0.01 {
		t.Errorf("Verify() nlc = %v, want %v", gotNLC, nlcEUR)
	}
}

func TestQuoteGenerator_ExpiredQuoteFails(t *testing.T) {
	mock := &mockQuoteStore{}
	gen := NewWithStore("test-secret", mock, 1*time.Millisecond)
	ctx := context.Background()

	vehicleHash := "01HEXPIRED"
	nlcEUR := 25000.0

	quote, err := gen.Generate(ctx, vehicleHash, nlcEUR)
	if err != nil {
		t.Fatalf("Generate() error = %v", err)
	}

	time.Sleep(10 * time.Millisecond)

	_, err = gen.Verify(ctx, vehicleHash, quote.ID)
	if err == nil {
		t.Fatal("Verify() expected error for expired quote")
	}
	if !strings.Contains(err.Error(), "expired") {
		t.Errorf("Verify() error = %v, want substring 'expired'", err)
	}
}
