// Package familia_b implements Family B — Geocartografía (OSM + Wikidata).
//
// Sprint 3: two sub-techniques are active for all 6 target countries:
//   - B.1 — OSM Overpass API (OpenStreetMap)
//   - B.2 — Wikidata SPARQL query
//
// Each Run call executes both sub-techniques for the given country in sequence:
//  1. Overpass query for the country
//  2. 10-second delay (Overpass rate limit: 1 req/10 s)
//  3. Wikidata SPARQL query for the country
//  4. 2-second delay (Wikidata etiquette: 1 req/2 s before the next country)
//
// When country is "" or "*", all 6 countries are iterated in order.
package familia_b

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/families/familia_b/osm"
	"cardex.eu/discovery/internal/families/familia_b/wikidata"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID   = "B"
	familyName = "Geocartografía (OSM Overpass + Wikidata SPARQL)"
)

// allCountries is the canonical order for a full 6-country run.
var allCountries = []string{"DE", "FR", "ES", "BE", "NL", "CH"}

// Config holds Family B runtime configuration.
// Currently no credentials are required for either sub-technique
// (Overpass and Wikidata are both public endpoints).
type Config struct {
	// Countries overrides the default 6-country set when non-empty.
	// Each element is an ISO 3166-1 alpha-2 code.
	Countries []string
}

// FamilyB orchestrates sub-techniques B.1 (OSM Overpass) and B.2 (Wikidata)
// for all configured countries.
type FamilyB struct {
	overpass  *osm.Overpass
	wikidata  *wikidata.Wikidata
	countries []string
	log       *slog.Logger
}

// New constructs a FamilyB with production endpoints and the default 6-country
// target set (overridden by cfg.Countries when non-empty).
func New(graph kg.KnowledgeGraph, cfg Config) *FamilyB {
	countries := allCountries
	if len(cfg.Countries) > 0 {
		countries = cfg.Countries
	}
	return &FamilyB{
		overpass:  osm.New(graph),
		wikidata:  wikidata.New(graph),
		countries: countries,
		log:       slog.Default().With("family", familyID),
	}
}

// FamilyID returns the single-letter family identifier.
func (f *FamilyB) FamilyID() string { return familyID }

// Name returns the human-readable family label.
func (f *FamilyB) Name() string { return familyName }

// Run executes both sub-techniques for the given country and returns an
// aggregated FamilyResult.
//
// Special values for country:
//   - "" or "*": iterate over all configured countries in order
//   - any ISO 3166-1 alpha-2 code: run for that single country only
func (f *FamilyB) Run(ctx context.Context, country string) (*runner.FamilyResult, error) {
	start := time.Now()
	result := &runner.FamilyResult{
		FamilyID:  familyID,
		Country:   country,
		StartedAt: start,
	}

	// Determine the set of countries to iterate.
	countries := []string{country}
	if country == "" || country == "*" {
		countries = f.countries
	}

	for i, iso := range countries {
		if ctx.Err() != nil {
			break
		}
		if err := f.runForCountry(ctx, iso, result); err != nil {
			f.log.Warn("familia_b: country run error", "country", iso, "err", err)
		}
		// Between countries (not after the last one): wait for Wikidata etiquette (2s).
		if i < len(countries)-1 {
			select {
			case <-ctx.Done():
			case <-time.After(2 * time.Second):
			}
		}
	}

	result.FinishedAt = time.Now()
	result.Duration = time.Since(start)

	if result.TotalErrors > 0 {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(0)
	} else {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(1)
	}
	return result, nil
}

// runForCountry executes B.1 then B.2 for a single country, accumulating
// results into the provided FamilyResult.
func (f *FamilyB) runForCountry(ctx context.Context, iso string, result *runner.FamilyResult) error {
	// ── B.1 — OSM Overpass ───────────────────────────────────────────────────
	osmRes, err := f.overpass.RunForCountry(ctx, iso)
	if osmRes != nil {
		result.SubResults = append(result.SubResults, osmRes)
		result.TotalNew += osmRes.Discovered
		result.TotalErrors += osmRes.Errors
	}
	if err != nil {
		result.TotalErrors++
		f.log.Warn("familia_b: OSM Overpass error", "country", iso, "err", err)
	}

	// Overpass rate limit: wait 10 s between country-level queries.
	// This wait also separates the Overpass and Wikidata requests within
	// the same country to avoid concurrent load on both endpoints.
	select {
	case <-ctx.Done():
		return fmt.Errorf("familia_b: context cancelled after Overpass %s", iso)
	case <-time.After(10 * time.Second):
	}

	// ── B.2 — Wikidata SPARQL ────────────────────────────────────────────────
	wdRes, err := f.wikidata.RunForCountry(ctx, iso)
	if wdRes != nil {
		result.SubResults = append(result.SubResults, wdRes)
		result.TotalNew += wdRes.Discovered
		result.TotalErrors += wdRes.Errors
	}
	if err != nil {
		result.TotalErrors++
		f.log.Warn("familia_b: Wikidata error", "country", iso, "err", err)
	}

	return nil
}

// HealthCheck verifies that both the Overpass API and the Wikidata SPARQL
// endpoint are reachable with minimal probe queries.
func (f *FamilyB) HealthCheck(ctx context.Context) error {
	if err := f.overpass.HealthCheck(ctx); err != nil {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(0)
		return fmt.Errorf("familia_b health: Overpass: %w", err)
	}
	if err := f.wikidata.HealthCheck(ctx); err != nil {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(0)
		return fmt.Errorf("familia_b health: Wikidata: %w", err)
	}
	metrics.HealthCheckStatus.WithLabelValues(familyID).Set(1)
	return nil
}
