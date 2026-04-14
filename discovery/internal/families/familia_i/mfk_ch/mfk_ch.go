// Package mfk_ch implements sub-technique I.CH.1 — MFK inspection stations (CH).
//
// # Current status: SKELETON
//
// MFK (Motorfahrzeugkontrolle) is Switzerland's cantonal vehicle inspection
// authority. Each of Switzerland's 26 cantons operates its own MFK; there is
// no federal station-finder aggregator.
//
// The Swiss ASTRA (Bundesamt für Strassen) provides a cantonal MFK directory at:
//
//	https://www.astra.admin.ch/astra/de/home/fachleute/fahrzeuge/motorfahrzeugkontrolle.html
//
// Individual canton contact lists are available as HTML; no unified JSON API exists.
//
// Planned approach (Sprint 11+):
//  1. Scrape the ASTRA MFK contact page for cantonal station URLs.
//  2. For each canton URL: parse the HTML station listing (typically 1–3 stations).
//  3. Upsert with IdentifierMFKStationID (format: "CH-{canton}-{seq}").
//
// Scope note: Switzerland has ~26 cantonal MFKs (not commercial inspection centres).
// Entity count will be small (~50–100 records). Low priority.
//
// Rate limiting: 1 req / 3 s.
// ConfidenceContributed: 0.05 (BaseWeights["I"]).
package mfk_ch

import (
	"context"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID    = "I"
	subTechID   = "I.CH.1"
	subTechName = "MFK cantonal inspection stations (CH)"
	countryCH   = "CH"
)

// MFKCH implements the I.CH.1 sub-technique (skeleton).
type MFKCH struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs a MFKCH executor.
func New(graph kg.KnowledgeGraph) *MFKCH {
	return &MFKCH{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (m *MFKCH) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (m *MFKCH) Name() string { return subTechName }

// Run logs the deferred-blocker reason and returns an empty result.
func (m *MFKCH) Run(_ context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	m.log.Info("mfk_ch: I.CH.1 deferred — cantonal MFK; no unified API; ~50 records low priority",
		"country", countryCH,
		"planned", "Sprint 11: ASTRA HTML scrape + per-canton station listing",
	)
	return &runner.SubTechniqueResult{
		SubTechniqueID: subTechID,
		Country:        countryCH,
		Duration:       time.Since(start),
	}, nil
}
