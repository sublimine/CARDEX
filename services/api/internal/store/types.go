// Package store is the data-access layer over PostgreSQL's `vehicles` table.
//
// The Store interface is deliberately small and fakeable so handlers can be
// tested without a live database. The concrete implementation uses pgx and
// PostgreSQL's percentile_cont for market statistics.
package store

import (
	"context"
	"time"
)

// Filter selects a cohort of vehicles for market-price and arbitrage queries.
// Zero-valued optional fields mean "no constraint".
type Filter struct {
	// Make and Model are matched case-insensitively (exact, no wildcards).
	Make  string
	Model string
	// YearMin / YearMax bound the model year (inclusive). 0 means unbounded.
	YearMin int
	YearMax int
	// Fuel matches fuel_type case-insensitively when non-empty.
	Fuel string
	// MileageMin / MileageMax bound mileage_km (inclusive). 0 means unbounded.
	MileageMin int
	MileageMax int
	// Countries restricts to these ISO-3166-1 alpha-2 source countries. Nil/empty
	// means all countries.
	Countries []string
}

// CountryStats is the price distribution for one country within a Filter cohort.
// All prices are in EUR.
type CountryStats struct {
	Country string  `json:"country"`
	Count   int     `json:"count"`
	P10     float64 `json:"p10"`
	P25     float64 `json:"p25"`
	P50     float64 `json:"p50"`
	P75     float64 `json:"p75"`
	P90     float64 `json:"p90"`
	Avg     float64 `json:"avg"`
	Min     float64 `json:"min"`
	Max     float64 `json:"max"`
}

// Listing is a single vehicle listing surfaced as an actionable arbitrage link.
type Listing struct {
	ID            string    `json:"id"`
	Make          string    `json:"make"`
	Model         string    `json:"model"`
	Year          int       `json:"year,omitempty"`
	MileageKm     int       `json:"mileage_km,omitempty"`
	FuelType      string    `json:"fuel_type,omitempty"`
	CO2gkm        int       `json:"co2_gkm,omitempty"`
	PriceEUR      float64   `json:"price_eur"`
	PriceRaw      float64   `json:"price_raw,omitempty"`
	CurrencyRaw   string    `json:"currency_raw,omitempty"`
	SourceCountry string    `json:"source_country"`
	SourceURL     string    `json:"source_url"`
	FirstSeenAt   time.Time `json:"first_seen_at,omitempty"`
}

// Store is the read interface used by the market-price and arbitrage handlers.
type Store interface {
	// MarketStats returns per-country price percentiles for the filter cohort.
	MarketStats(ctx context.Context, f Filter) ([]CountryStats, error)
	// CheapestListings returns the cheapest active listings in one country for the
	// filter cohort, ordered by EUR price ascending.
	CheapestListings(ctx context.Context, f Filter, country string, limit int) ([]Listing, error)
	// Ping verifies database connectivity.
	Ping(ctx context.Context) error
}
