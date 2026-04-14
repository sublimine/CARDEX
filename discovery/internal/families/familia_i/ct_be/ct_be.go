// Package ct_be implements sub-technique I.BE.1 — Contrôle Technique (CT) stations (BE).
//
// # Current status: SKELETON
//
// Belgium has two separate CT (Contrôle Technique / Technische Keuring) networks:
//
//   - Wallonia (FR): managed by AUTOSÉCURITÉ / SÉCURITEST, finder at
//     https://www.autosecurite.be/trouver-un-centre
//   - Flanders + Brussels (NL): managed by GOCA / DIV, finder at
//     https://www.keuringplus.be/zoek-een-keuringsplaats
//
// Both finders are React/Angular SPAs; their internal APIs require network
// inspection before implementation.
//
// Planned approach (Sprint 11+):
//  1. Identify JSON API endpoints for both CT networks.
//  2. For each endpoint: paginate or geo-sweep with Belgian postal codes.
//  3. Upsert with IdentifierCTStationID; MetadataJSON = is_dealer_candidate:false.
//
// Rate limiting: 1 req / 3 s.
// ConfidenceContributed: 0.05 (BaseWeights["I"]).
package ct_be

import (
	"context"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID    = "I"
	subTechID   = "I.BE.1"
	subTechName = "Contrôle Technique stations (BE)"
	countryBE   = "BE"
)

// CTBE implements the I.BE.1 sub-technique (skeleton).
type CTBE struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs a CTBE executor.
func New(graph kg.KnowledgeGraph) *CTBE {
	return &CTBE{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (c *CTBE) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (c *CTBE) Name() string { return subTechName }

// Run logs the deferred-blocker reason and returns an empty result.
func (c *CTBE) Run(_ context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	c.log.Info("ct_be: I.BE.1 deferred — two separate CT networks (AUTOSÉCURITÉ + GOCA); APIs require research",
		"country", countryBE,
		"planned", "Sprint 11: identify JSON API for AUTOSÉCURITÉ + GOCA/DIV networks",
	)
	return &runner.SubTechniqueResult{
		SubTechniqueID: subTechID,
		Country:        countryBE,
		Duration:       time.Since(start),
	}, nil
}
