//go:build integration

// Integration tests for the PostgreSQL store. Require a live database via
// TEST_DATABASE_URL. Run with:
//
//	GOWORK=off go test -tags integration ./internal/store/
package store

import (
	"context"
	"os"
	"testing"
	"time"
)

const createVehicles = `
CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_ulid   TEXT PRIMARY KEY,
    make           TEXT,
    model          TEXT,
    year           INT,
    mileage_km     INT,
    fuel_type      TEXT,
    co2_gkm        INT,
    price_raw      NUMERIC(12,2),
    currency_raw   CHAR(3),
    last_price_eur NUMERIC(12,2),
    source_country CHAR(2),
    source_url     TEXT,
    listing_status TEXT DEFAULT 'ACTIVE',
    first_seen_at  TIMESTAMPTZ DEFAULT NOW()
);`

func setup(t *testing.T) *PGStore {
	t.Helper()
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL not set; skipping integration test")
	}
	ctx := context.Background()
	s, err := NewPG(ctx, dsn, 1.04)
	if err != nil {
		t.Fatalf("NewPG: %v", err)
	}
	if _, err := s.Pool().Exec(ctx, `DROP TABLE IF EXISTS vehicles`); err != nil {
		t.Fatalf("drop: %v", err)
	}
	if _, err := s.Pool().Exec(ctx, createVehicles); err != nil {
		t.Fatalf("create: %v", err)
	}
	return s
}

func insert(t *testing.T, s *PGStore, id, mk, md string, year, km, co2 int, price float64, cur string, lastEUR *float64, country, url, status string) {
	t.Helper()
	_, err := s.Pool().Exec(context.Background(), `
        INSERT INTO vehicles (vehicle_ulid, make, model, year, mileage_km, co2_gkm,
            price_raw, currency_raw, last_price_eur, source_country, source_url, listing_status, first_seen_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)`,
		id, mk, md, year, km, co2, price, cur, lastEUR, country, url, status, time.Now())
	if err != nil {
		t.Fatalf("insert %s: %v", id, err)
	}
}

func TestMarketStatsIntegration(t *testing.T) {
	s := setup(t)
	defer s.Close()

	// DE: three active BMW 320d at 18000/20000/22000 EUR.
	insert(t, s, "de1", "BMW", "320d", 2020, 50000, 120, 18000, "EUR", nil, "DE", "https://d.de/1", "ACTIVE")
	insert(t, s, "de2", "BMW", "320d", 2020, 60000, 120, 20000, "EUR", nil, "DE", "https://d.de/2", "ACTIVE")
	insert(t, s, "de3", "BMW", "320d", 2020, 70000, 120, 22000, "EUR", nil, "DE", "https://d.de/3", "ACTIVE")
	// ES: two active, one SOLD (must be excluded).
	insert(t, s, "es1", "BMW", "320d", 2020, 40000, 120, 24000, "EUR", nil, "ES", "https://d.es/1", "ACTIVE")
	insert(t, s, "es2", "BMW", "320d", 2020, 45000, 120, 26000, "EUR", nil, "ES", "https://d.es/2", "ACTIVE")
	insert(t, s, "es3", "BMW", "320d", 2020, 45000, 120, 9999, "EUR", nil, "ES", "https://d.es/3", "SOLD")
	// Different model (must be excluded by filter).
	insert(t, s, "de9", "BMW", "X5", 2020, 10000, 120, 50000, "EUR", nil, "DE", "https://d.de/9", "ACTIVE")

	stats, err := s.MarketStats(context.Background(), Filter{Make: "BMW", Model: "320d"})
	if err != nil {
		t.Fatalf("MarketStats: %v", err)
	}
	byCountry := map[string]CountryStats{}
	for _, cs := range stats {
		byCountry[cs.Country] = cs
	}
	de, ok := byCountry["DE"]
	if !ok {
		t.Fatal("missing DE stats")
	}
	if de.Count != 3 {
		t.Errorf("DE count = %d, want 3", de.Count)
	}
	if de.P50 != 20000 {
		t.Errorf("DE P50 = %v, want 20000", de.P50)
	}
	es, ok := byCountry["ES"]
	if !ok {
		t.Fatal("missing ES stats")
	}
	if es.Count != 2 { // SOLD excluded
		t.Errorf("ES count = %d, want 2 (SOLD excluded)", es.Count)
	}
	if es.P50 != 25000 {
		t.Errorf("ES P50 = %v, want 25000", es.P50)
	}
}

func TestCheapestListingsIntegration(t *testing.T) {
	s := setup(t)
	defer s.Close()
	insert(t, s, "de1", "BMW", "320d", 2020, 50000, 120, 22000, "EUR", nil, "DE", "https://d.de/1", "ACTIVE")
	insert(t, s, "de2", "BMW", "320d", 2020, 60000, 120, 18000, "EUR", nil, "DE", "https://d.de/2", "ACTIVE")
	insert(t, s, "de3", "BMW", "320d", 2020, 70000, 120, 20000, "EUR", nil, "DE", "https://d.de/3", "ACTIVE")

	listings, err := s.CheapestListings(context.Background(), Filter{Make: "BMW", Model: "320d"}, "DE", 2)
	if err != nil {
		t.Fatalf("CheapestListings: %v", err)
	}
	if len(listings) != 2 {
		t.Fatalf("got %d listings, want 2 (limit)", len(listings))
	}
	if listings[0].PriceEUR != 18000 {
		t.Errorf("cheapest = %v, want 18000", listings[0].PriceEUR)
	}
	if listings[0].SourceURL != "https://d.de/2" {
		t.Errorf("cheapest url = %q, want https://d.de/2", listings[0].SourceURL)
	}
}

func TestCurrencyConversionIntegration(t *testing.T) {
	s := setup(t)
	defer s.Close()
	// CHF price without last_price_eur → converted at 1.04.
	insert(t, s, "ch1", "BMW", "320d", 2020, 50000, 120, 20000, "CHF", nil, "CH", "https://d.ch/1", "ACTIVE")
	// EUR-normalized via last_price_eur overrides price_raw.
	eur := 19000.0
	insert(t, s, "ch2", "BMW", "320d", 2020, 50000, 120, 30000, "CHF", &eur, "CH", "https://d.ch/2", "ACTIVE")

	stats, err := s.MarketStats(context.Background(), Filter{Make: "BMW", Model: "320d", Countries: []string{"CH"}})
	if err != nil {
		t.Fatalf("MarketStats: %v", err)
	}
	if len(stats) != 1 {
		t.Fatalf("got %d country stats, want 1", len(stats))
	}
	// Prices: ch1 = 20000*1.04 = 20800; ch2 = 19000 (last_price_eur). Min=19000, Max=20800.
	if stats[0].Min != 19000 {
		t.Errorf("CH min = %v, want 19000 (last_price_eur)", stats[0].Min)
	}
	if stats[0].Max != 20800 {
		t.Errorf("CH max = %v, want 20800 (CHF*1.04)", stats[0].Max)
	}
}
