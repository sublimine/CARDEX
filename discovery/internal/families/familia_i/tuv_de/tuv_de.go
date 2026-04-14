// Package tuv_de implements sub-technique I.DE.2 — TÜV inspection stations (DE).
//
// # Current status: SKELETON — multi-org complexity
//
// "TÜV" in Germany is not a single organisation; it comprises several independent
// entities, each with separate station finders:
//
//   - TÜV Rheinland  — https://www.tuv.com/germany/de/hv-standorte.html
//   - TÜV SÜD        — https://www.tuvsud.com/de-de/store-locator
//   - TÜV NORD       — https://www.tuev-nord.de/de/unternehmen/standorte/
//   - TÜV Thüringen  — https://www.tuev-thueringen.de/standorte/
//   - DEKRA (I.DE.1) — separate sub-technique
//   - GTÜ            — https://www.gtue.de/service/pruefstellen/
//
// # Planned approach (Sprint 11+):
//
// Each TÜV org will be implemented as a sub-locator (similar to OEM adapters in
// Family H) sharing a common TÜV station parsing interface. The aggregator pattern
// mirrors familia_h/family.go — a TÜVLocator interface + map[string]TÜVLocator.
//
// Rate limiting: 1 req / 3 s per org.
// ConfidenceContributed: 0.05 (BaseWeights["I"]).
package tuv_de

import (
	"context"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID    = "I"
	subTechID   = "I.DE.2"
	subTechName = "TÜV inspection stations (DE)"
	countryDE   = "DE"
)

// TuvDE implements the I.DE.2 sub-technique (skeleton).
type TuvDE struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs a TuvDE executor.
func New(graph kg.KnowledgeGraph) *TuvDE {
	return &TuvDE{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (t *TuvDE) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (t *TuvDE) Name() string { return subTechName }

// Run logs the deferred-blocker reason and returns an empty result.
func (t *TuvDE) Run(_ context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	t.log.Info("tuv_de: I.DE.2 deferred — multi-org complexity (TÜV Rheinland/SÜD/NORD/Thüringen/GTÜ)",
		"country", countryDE,
		"blocker", "multiple independent TÜV organisations with heterogeneous SPA station finders",
		"planned", "Sprint 11: TÜVLocator interface + per-org adapters (mirrors H OEM pattern)",
	)
	return &runner.SubTechniqueResult{
		SubTechniqueID: subTechID,
		Country:        countryDE,
		Duration:       time.Since(start),
	}, nil
}
