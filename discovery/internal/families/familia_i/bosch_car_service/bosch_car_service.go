// Package bosch_car_service implements sub-technique I.XX.1 — Bosch Car Service
// partner network (pan-EU: DE/FR/NL/BE/CH/ES).
//
// # Current status: SKELETON — API research required
//
// Bosch Car Service is a pan-European franchise network of independent garages
// and inspection stations partnered with Bosch. The station finder is at:
//
//	https://www.boschcarservice.com/de/werkstatt-suchen/ (DE example)
//
// The finder is a React SPA backed by an internal REST API. The API base is
// believed to be under https://api.boschcarservice.com/v*/workshops or similar,
// returning JSON with workshop objects including:
//
//   - workshopId     — unique partner ID
//   - name / companyName
//   - address.street / postalCode / city / countryCode
//   - phone / website
//   - services[]     — list of offered services (inspection, repair, etc.)
//
// # Countries covered:
//
// DE, FR, NL, BE, CH, ES — all 6 cardex target countries.
// Each country has a separate locator base URL; the API is the same across all.
//
// # Planned approach (Sprint 11+):
//
//  1. Identify API endpoint via network inspection of the SPA.
//  2. For each country × postcode grid: GET /workshops?lat=X&lng=Y&radius=50 or
//     similar geo-based query.
//  3. Upsert with IdentifierBoschCarServiceID; MetadataJSON = is_dealer_candidate:false.
//
// Rate limiting: 1 req / 3 s per country.
// ConfidenceContributed: 0.05 (BaseWeights["I"]).
package bosch_car_service

import (
	"context"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID    = "I"
	subTechID   = "I.XX.1"
	subTechName = "Bosch Car Service partner network (pan-EU)"
)

// supportedCountries are the 6 cardex target countries covered by Bosch Car Service.
var supportedCountries = []string{"DE", "FR", "NL", "BE", "CH", "ES"}

// BoschCarService implements the I.XX.1 sub-technique (skeleton).
type BoschCarService struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs a BoschCarService executor.
func New(graph kg.KnowledgeGraph) *BoschCarService {
	return &BoschCarService{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (b *BoschCarService) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (b *BoschCarService) Name() string { return subTechName }

// Run logs the deferred-blocker reason and returns an empty result.
func (b *BoschCarService) Run(_ context.Context, country string) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	b.log.Info("bosch_car_service: I.XX.1 deferred — React SPA; internal API endpoint not yet identified",
		"country", country,
		"blocker", "SPA REST API requires network inspection",
		"planned", "Sprint 11: identify /api/workshops endpoint + geo-sweep",
	)
	return &runner.SubTechniqueResult{
		SubTechniqueID: subTechID,
		Country:        country,
		Duration:       time.Since(start),
	}, nil
}

// SupportedCountries returns the list of countries this sub-technique covers.
func (b *BoschCarService) SupportedCountries() []string { return supportedCountries }
