// Package cantonal_ch implements sub-technique J.CH — Swiss cantonal
// Handelsregister coverage (26 cantons).
//
// # STATUS: DEFERRED — 26 heterogeneous cantonal portals + UID overlap
//
// # Why deferred
//
// Switzerland has 26 cantonal Handelsregister portals, each with:
//   - Different web technology (mix of AXIANTA, eHR, custom portals)
//   - Different search interfaces (some SPA, some server-rendered)
//   - Different data formats (no federal API standard below Zefix)
//   - Different update frequencies (daily to weekly)
//
// The federal Zefix (Zentraler Firmenindex) at zefix.ch already federates
// all 26 cantonal registers via a unified REST API, which is implemented in
// A.CH.1. J.CH would only add value for:
//   1. Cantonal-specific metadata not in Zefix (e.g. Zurich ZHR direct extract
//      includes shareholder registers not federated to Zefix)
//   2. Sub-day freshness for specific high-priority cantons (ZH, BE, GE, VD)
//
// Neither use-case is prioritised in Phase 2 given Zefix coverage is >98%.
//
// The Swiss UID validation is already handled by M.2 (ch_uid package), which
// cross-validates dealers discovered by any family against the UID-Register SOAP
// service. This provides the fiscal-signal validation that cantonal HR would
// otherwise supply.
//
// # Activation path
//
// For cantons with public REST APIs (ZH: zh.ch/handelsregister/api,
// GE: ge.ch/ide-hregister):
//  1. Implement per-canton client in cantonal_ch/{canton_code}/ subpackage.
//  2. Add to cantonal_ch/family.go dispatch table.
//  3. Rate limit: 1 req/5 s per canton API.
// Estimated activation sprint: Sprint 16+ (post-revenue, when CH market is
// prioritised for expansion).
package cantonal_ch

import (
	"context"
	"log/slog"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	subTechID   = "J.CH"
	subTechName = "CH cantonal Handelsregister (DEFERRED -- Zefix federal API covers >98%)"
)

// CantonalCH is the J.CH stub.
type CantonalCH struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs a CantonalCH stub.
func New(graph kg.KnowledgeGraph) *CantonalCH {
	return &CantonalCH{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (c *CantonalCH) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (c *CantonalCH) Name() string { return subTechName }

// Run logs the deferral reason and returns an empty result.
func (c *CantonalCH) Run(_ context.Context) (*runner.SubTechniqueResult, error) {
	c.log.Info("J.CH cantonal Handelsregister: DEFERRED",
		"reason", "26 heterogeneous portals; Zefix federal API (A.CH.1) covers >98%; M.2 UID validates CH dealers",
		"activation", "Sprint 16+ post-revenue; start with ZH+GE REST APIs",
	)
	return &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: "CH"}, nil
}
