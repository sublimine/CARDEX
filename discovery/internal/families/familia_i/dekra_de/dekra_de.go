// Package dekra_de implements sub-technique I.DE.1 — DEKRA inspection stations (DE).
//
// # Current status: SKELETON — API research required
//
// DEKRA SE is Europe's largest vehicle inspection organisation. Their station
// finder in Germany is at:
//
//	https://www.dekra.de/de/kfz-pruefdienst/pruefstellen-suche/
//
// The page renders via a Nuxt.js SPA that calls an internal JSON API, likely at
// a path like /api/stations or /de/ajax/pruefstellen. The exact endpoint and
// authentication scheme require network inspection (Sprint 11 research task).
//
// # Planned approach (Sprint 11+):
//
//  1. Intercept XHR calls made by the station-search SPA using browser.InterceptXHR.
//  2. Parse the response JSON (expected: array of station objects with id, name,
//     address fields).
//  3. Upsert with IdentifierDEKRAStationID; MetadataJSON = is_dealer_candidate:false.
//
// # Alternative approach (no browser):
//
//   - DEKRA Germany may expose a public REST API under api.dekra.de/stations.
//   - The sitemap at https://www.dekra.de/sitemap.xml may list individual station
//     pages parseable with net/http + goquery.
//
// Rate limiting: 1 req / 3 s when activated.
// ConfidenceContributed: 0.05 (BaseWeights["I"]).
package dekra_de

import (
	"context"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID    = "I"
	subTechID   = "I.DE.1"
	subTechName = "DEKRA inspection stations (DE)"
	countryDE   = "DE"
)

// DekraDE implements the I.DE.1 sub-technique (skeleton).
type DekraDE struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs a DekraDE executor.
func New(graph kg.KnowledgeGraph) *DekraDE {
	return &DekraDE{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (d *DekraDE) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (d *DekraDE) Name() string { return subTechName }

// Run logs the deferred-blocker reason and returns an empty result.
func (d *DekraDE) Run(_ context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	d.log.Info("dekra_de: I.DE.1 deferred — Nuxt.js SPA; internal API endpoint not yet identified",
		"country", countryDE,
		"blocker", "SPA XHR endpoint requires browser interception or API key research",
		"planned", "Sprint 11: browser.InterceptXHR or DEKRA open API",
	)
	return &runner.SubTechniqueResult{
		SubTechniqueID: subTechID,
		Country:        countryDE,
		Duration:       time.Since(start),
	}, nil
}
