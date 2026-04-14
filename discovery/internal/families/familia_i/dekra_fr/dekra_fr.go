// Package dekra_fr implements sub-technique I.FR.1 — DEKRA inspection stations (FR).
//
// # Current status: SKELETON
//
// DEKRA France operates Contrôle Technique (CT) inspection centres, listed at:
//
//	https://www.dekra-autocite.fr/trouver-un-centre/
//
// The finder SPA calls an internal API to return centre locations as JSON.
// The API endpoint and schema require research (Sprint 11).
//
// Planned approach: same as I.DE.1 (dekra_de) — browser.InterceptXHR or
// direct API call once endpoint is identified.
//
// Rate limiting: 1 req / 3 s when activated.
// ConfidenceContributed: 0.05 (BaseWeights["I"]).
package dekra_fr

import (
	"context"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID    = "I"
	subTechID   = "I.FR.1"
	subTechName = "DEKRA Contrôle Technique stations (FR)"
	countryFR   = "FR"
)

// DekraFR implements the I.FR.1 sub-technique (skeleton).
type DekraFR struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs a DekraFR executor.
func New(graph kg.KnowledgeGraph) *DekraFR {
	return &DekraFR{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (d *DekraFR) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (d *DekraFR) Name() string { return subTechName }

// Run logs the deferred-blocker reason and returns an empty result.
func (d *DekraFR) Run(_ context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	d.log.Info("dekra_fr: I.FR.1 deferred — centre-finder API endpoint not yet identified",
		"country", countryFR,
		"planned", "Sprint 11: identify SPA API + InterceptXHR",
	)
	return &runner.SubTechniqueResult{
		SubTechniqueID: subTechID,
		Country:        countryFR,
		Duration:       time.Since(start),
	}, nil
}
