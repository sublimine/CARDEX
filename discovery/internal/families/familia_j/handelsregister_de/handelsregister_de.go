// Package handelsregister_de implements sub-technique J.DE — German Bundesland
// Handelsregister sub-jurisdiction coverage.
//
// # STATUS: DEFERRED — overlaps A.DE + portal anti-bot barriers
//
// # Overlap with Familia A
//
// Familia A.DE.1 uses OffeneRegister.de, which is a full-coverage mirror of
// the Handelsregister for all 16 Bundesländer. OffeneRegister ingests data from
// the Federal Handelsregister portal (handelsregister.de) and makes it available
// via bulk download + REST API with no bot protection.
//
// J.DE would only add value if it scrapes directly from the canonical
// handelsregister.de portal to capture same-day registrations that OffeneRegister
// has not yet indexed (typical lag: 24-72 h). This latency delta is not
// meaningful for CARDEX dealer discovery, which targets stable entities.
//
// # Portal anti-bot barriers
//
// handelsregister.de (operated by the Landesjustizverwaltungen) uses:
//   - Cloudflare DDoS protection with challenge pages
//   - CAPTCHA on search queries with >10 results
//   - Rate limit: ~10 queries/hour per IP before soft block
//   - Session token rotation that invalidates automated sessions
//
// Cloudflare WAF bypass via residential proxy is feasible but:
//   1. Violates handelsregister.de Nutzungsbedingungen §4 (automated access prohibited)
//   2. Falls under R1 zero-legal-risk policy (same assessment as LinkedIn L.2)
//
// # Activation path
//
// Option A: OffeneRegister refresh lag is acceptable (recommended) — no activation
// needed; A.DE.1 provides equivalent coverage.
//
// Option B: Direct Handelsregister partnership — contact:
// Bundesministerium der Justiz, open-data-justiz@bmj.bund.de
// Provides authenticated bulk access to all 16 Bundesländer without rate limits.
// Estimated activation sprint: Sprint 18+ (requires legal agreement).
package handelsregister_de

import (
	"context"
	"log/slog"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	subTechID   = "J.DE"
	subTechName = "DE Handelsregister Bundeslaender (DEFERRED -- covered by A.DE OffeneRegister)"
)

// HandelsregisterDE is the J.DE stub.
type HandelsregisterDE struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs a HandelsregisterDE stub.
func New(graph kg.KnowledgeGraph) *HandelsregisterDE {
	return &HandelsregisterDE{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (h *HandelsregisterDE) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (h *HandelsregisterDE) Name() string { return subTechName }

// Run logs the deferral reason and returns an empty result.
func (h *HandelsregisterDE) Run(_ context.Context) (*runner.SubTechniqueResult, error) {
	h.log.Info("J.DE Handelsregister: DEFERRED",
		"reason", "A.DE OffeneRegister covers all 16 Bundeslaender; portal has Cloudflare+CAPTCHA barriers",
		"legal", "direct handelsregister.de scraping violates Nutzungsbedingungen §4 (R1 policy)",
		"activation", "Option A: accept OffeneRegister lag (recommended). Option B: BMJ bulk API partnership",
	)
	return &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: "DE"}, nil
}
