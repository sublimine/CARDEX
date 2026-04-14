// Package marginalia implements sub-technique K.2 — Marginalia Search (pan-EU).
//
// # Current status: DEFERRED — Sprint 12+ if time permits
//
// Marginalia Search (search.marginalia.nu) is an independent search engine
// specialised in the "small web" — non-commercial, non-SEO-optimised sites that
// larger engines often de-rank. For CARDEX, it is valuable for discovering
// long-tail independent dealer sites that are invisible to mainstream engines.
//
// # API
//
// Marginalia exposes a public JSON REST API (no auth required):
//
//	GET https://api.search.marginalia.nu/search/{query}?count=20&index=0
//
// Response:
//
//	{"query":"...","results":[{"url":"...","title":"...","description":"...","quality":"..."}]}
//
// # Why deferred:
//
//   - Marginalia indexes the English/international web well; coverage of
//     German/French/Spanish dealer sites is significantly lower than SearXNG.
//   - Sprint 11 budget is consumed by K.1 SearXNG implementation.
//   - Sprint 12 will implement K.2 if coverage analysis confirms incremental value
//     over K.1.
//
// robots.txt: api.search.marginalia.nu has no robots.txt restrictions on the /search
// endpoint. The operator (Viktor Lofgren, @marginalia.nu) explicitly supports
// programmatic API use.
//
// Rate limiting: 1 req / 5 s (same as K.1 SearXNG).
// BaseWeights["K"] = 0.05.
package marginalia

import (
	"context"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID    = "K"
	subTechID   = "K.2"
	subTechName = "Marginalia Search (pan-EU)"
)

// Marginalia implements the K.2 sub-technique (skeleton).
type Marginalia struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs a Marginalia executor.
func New(graph kg.KnowledgeGraph) *Marginalia {
	return &Marginalia{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (m *Marginalia) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (m *Marginalia) Name() string { return subTechName }

// Run logs the deferred-blocker reason and returns an empty result.
func (m *Marginalia) Run(_ context.Context, country string) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	m.log.Info("marginalia: K.2 deferred — lower coverage for EU dealer market vs K.1 SearXNG",
		"country", country,
		"api_endpoint", "https://api.search.marginalia.nu/search/{query}?count=20&index=0",
		"planned", "Sprint 12: implement if coverage analysis confirms incremental value over K.1",
	)
	return &runner.SubTechniqueResult{
		SubTechniqueID: subTechID,
		Country:        country,
		Duration:       time.Since(start),
	}, nil
}
