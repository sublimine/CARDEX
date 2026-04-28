// Package googlemaps implements sub-technique L.1 — Google Maps Places API
// (car_dealer category search).
//
// # STATUS: DEFERRED — €50 Phase 2 infrastructure budget constraint
//
// Google Maps Places API pricing (2024):
//   - Nearby Search: $32 per 1,000 requests
//   - Place Details: $17 per 1,000 requests
//   - Find Place: $17 per 1,000 requests
//
// Estimated cost for CARDEX scope (6 countries × ~5,000 postal codes × 2 API
// calls each) = ~$320 per full scan cycle, far exceeding the €50 budget.
//
// # Alternative coverage already in place
//
// The CARDEX discovery pipeline achieves equivalent coverage through:
//
//   - Familia B.1 (OSM Overpass): amenity=car_dealer, shop=car, office=car_dealer
//     tags cover >80% of EU car dealers with geo coordinates and opening hours.
//   - Familia B.2 (Wikidata): multi-brand dealer groups and major chains.
//   - Familia F (AutoScout24, mobile.de, La Centrale): marketplace-verified dealers
//     with address, phone, and inventory data.
//   - Familia H (OEM networks): OEM-verified dealer lists for 8 brands.
//
// # Activation path
//
// When monthly revenue > €500:
//  1. Enable Google Maps Platform billing account.
//  2. Set GOOGLE_MAPS_API_KEY environment variable.
//  3. Implement Places API Nearby Search with category car_dealer per bounding box.
//  4. Rate limit: 10 req/s (Maps Platform default quota).
//  5. Expected incremental yield: ~5-15% additional dealers not in OSM/OEM sources.
//
// Estimated activation sprint: post-revenue milestone 1 (tentative Sprint 20+).
package googlemaps

import (
	"context"
	"log/slog"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	subTechID   = "L.1"
	subTechName = "Google Maps Places API — car_dealer category (DEFERRED)"
)

// GoogleMaps is the L.1 stub. Run always returns an empty result.
type GoogleMaps struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs a GoogleMaps stub.
func New(graph kg.KnowledgeGraph) *GoogleMaps {
	return &GoogleMaps{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (g *GoogleMaps) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (g *GoogleMaps) Name() string { return subTechName }

// Run logs the deferral reason and returns an empty result. No API calls are made.
func (g *GoogleMaps) Run(_ context.Context, country string) (*runner.SubTechniqueResult, error) {
	g.log.Info("L.1 Google Maps Places: DEFERRED",
		"reason", "EUR 50 budget constraint (Places API ~$32/1000 req); OSM Overpass covers >80% equivalent",
		"activation", "post-revenue milestone 1; set GOOGLE_MAPS_API_KEY when ready",
		"country", country,
	)
	return &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}, nil
}
