// Package runner defines the execution contracts for discovery families and
// their sub-techniques.
package runner

import (
	"context"
	"time"
)

// ── Sub-technique level ─────────────────────────────────────────────────────

// SubTechniqueResult is the outcome of a single sub-technique execution.
type SubTechniqueResult struct {
	SubTechniqueID  string
	Country         string
	Discovered      int           // new entities written to KG
	Confirmed       int           // existing entities re-confirmed
	Errors          int
	Duration        time.Duration
}

// SubTechnique is the interface that every leaf data-source crawler implements.
type SubTechnique interface {
	// ID returns the sub-technique identifier, e.g. "A.FR.1".
	ID() string

	// Name returns a human-readable label.
	Name() string

	// Country returns the ISO-3166-1 alpha-2 code this sub-technique covers.
	Country() string

	// Run executes the crawl/fetch cycle and persists results to the KG.
	// Implementations must respect ctx cancellation and honour their
	// rate limits. Partial progress is acceptable — results should be
	// written incrementally rather than buffered in memory.
	Run(ctx context.Context) (*SubTechniqueResult, error)
}

// ── Family level ────────────────────────────────────────────────────────────

// FamilyResult aggregates results from all sub-techniques of a family.
type FamilyResult struct {
	FamilyID    string
	Country     string
	SubResults  []*SubTechniqueResult
	TotalNew    int
	TotalErrors int
	Duration    time.Duration
	StartedAt   time.Time
	FinishedAt  time.Time
}

// FamilyRunner is the interface that each family (A–O) implements.
// The Orchestrator (future Sprint 2) invokes families in parallel per country.
type FamilyRunner interface {
	// FamilyID returns the single-letter family identifier, e.g. "A".
	FamilyID() string

	// Name returns the human-readable family name.
	Name() string

	// Run executes all sub-techniques for the given country and returns
	// an aggregated FamilyResult.
	Run(ctx context.Context, country string) (*FamilyResult, error)

	// HealthCheck verifies that external API credentials and network
	// connectivity are operational. Returns nil if healthy.
	HealthCheck(ctx context.Context) error
}
