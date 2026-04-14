// Package autocasion implements sub-technique F.3 — Autocasion dealer directory (ES).
//
// # Current status: DEFERRED — Cloudflare protection
//
// Autocasion (autocasion.com) operates Spain's second-largest used-car marketplace.
// All cloud-egress IP ranges are blocked by a Cloudflare JS challenge (HTTP 403 with
// a CF-Ray header). robots.txt was also inaccessible during Sprint 6 research (TCP
// timeout from cloud-hosted IPs), preventing verification of crawl permissions.
//
// # Planned approach (Sprint 11+):
//
//  1. Verify robots.txt is accessible and permits /concesionarios/ path crawl.
//  2. Fetch paginated listing: GET /concesionarios/?p={page}
//     — each page returns ~30 dealer cards as static HTML.
//  3. For each dealer card: extract slug, name, city, province.
//  4. Follow /concesionario/{slug} profile pages to extract phone, address, website.
//  5. De-duplicate by slug; upsert via kg.KnowledgeGraph.
//
// # Unblocking conditions:
//
//   - Option A: Residential proxy egress — bypasses Cloudflare geographic/IP heuristics.
//   - Option B: Cloudflare Turnstile bypass via Playwright stealth mode (Sprint 10+
//     browser capability extension).
//   - Option C: Official Autocasion API partnership.
//
// All three options require business or technical decisions outside sprint scope.
// This skeleton exists to document the blocker and keep the package import path
// stable so that familia_f/family.go can activate it without structural changes.
package autocasion

import (
	"context"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID    = "F"
	subTechID   = "F.ES.3"
	subTechName = "Autocasion dealer directory (ES)"
	countryES   = "ES"

	defaultBaseURL = "https://www.autocasion.com"
)

// Autocasion implements the F.3 sub-technique.
// Currently always returns a deferred result; Run() is a no-op.
type Autocasion struct {
	graph   kg.KnowledgeGraph
	baseURL string
	log     *slog.Logger
}

// New constructs an Autocasion executor. The graph is retained for when
// the implementation is activated in a future sprint.
func New(graph kg.KnowledgeGraph) *Autocasion {
	return &Autocasion{
		graph:   graph,
		baseURL: defaultBaseURL,
		log:     slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (a *Autocasion) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (a *Autocasion) Name() string { return subTechName }

// Run logs the deferred-blocker reason and returns an empty result.
// Activation requires Cloudflare bypass capability (residential proxy or
// Playwright stealth extension) — see package-level documentation.
func (a *Autocasion) Run(_ context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	a.log.Info("autocasion: F.3 deferred — Cloudflare JS challenge blocks cloud egress",
		"country", countryES,
		"blocker", "Cloudflare HTTP 403 + robots.txt inaccessible from cloud IPs",
		"unblock", "residential proxy OR Playwright stealth mode (Sprint 11+)",
	)
	return &runner.SubTechniqueResult{
		SubTechniqueID: subTechID,
		Country:        countryES,
		Duration:       time.Since(start),
	}, nil
}
