// Package jobboards implements sub-technique M.3 — Job board signals (pan-EU).
//
// # Current status: DEFERRED — Sprint 12+
//
// Job board signals detect automotive dealer operators by mining job postings
// for automotive-sector roles (mechanic, salesperson, Verkaufsberater, vendeur
// automobile, etc.) on major European job boards:
//
//   - Indeed (indeed.com/de, .fr, .es, .nl, .be, .ch)
//   - Stepstone (stepstone.de, .fr, .be, .nl)
//   - InfoJobs (infojobs.net — ES)
//   - Monster (monster.de, .fr, .be, .nl, .ch)
//   - APEC (apec.fr — FR executive)
//
// # Planned approach (Sprint 12+):
//
//  1. Use browser.InterceptXHR to intercept Indeed / Stepstone API calls for
//     job search queries (query: "mécanique automobile" + city grid).
//  2. Extract company_name, company_website, location from job posting API responses.
//  3. Cross-check company_name + domain against KG — new signals are stored as
//     LOW_CONFIDENCE entries pending cross-validation from Families A/B/H.
//
// # Why deferred:
//
//   - Indeed enforces aggressive JavaScript fingerprinting; Playwright stealth
//     extensions required beyond Sprint 11 scope.
//   - Stepstone rate-limits IP ranges without API key agreement.
//   - Sprint 12 will add M.3 as a named Playwright browser extension sub-technique.
package jobboards

import (
	"context"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID    = "M"
	subTechID   = "M.3"
	subTechName = "Job board signals (pan-EU)"
)

// JobBoards implements the M.3 sub-technique (skeleton).
type JobBoards struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs a JobBoards executor.
func New(graph kg.KnowledgeGraph) *JobBoards {
	return &JobBoards{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (j *JobBoards) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (j *JobBoards) Name() string { return subTechName }

// Run logs the deferred-blocker reason and returns an empty result.
func (j *JobBoards) Run(_ context.Context, country string) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	j.log.Info("jobboards: M.3 deferred — Indeed/Stepstone JS fingerprinting requires Playwright stealth",
		"country", country,
		"planned", "Sprint 12: browser.InterceptXHR + stealth mode + Indeed/Stepstone/InfoJobs/Monster",
	)
	return &runner.SubTechniqueResult{
		SubTechniqueID: subTechID,
		Country:        country,
		Duration:       time.Since(start),
	}, nil
}
