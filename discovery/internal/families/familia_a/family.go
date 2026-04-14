// Package familia_a implements Family A — Registros mercantiles federales y regionales.
//
// Sprint 1: only sub-technique A.FR.1 (INSEE Sirene) is active.
// Additional sub-techniques (DE, ES, NL, BE, CH) are registered as they are
// implemented in subsequent sprints.
package familia_a

import (
	"context"
	"fmt"
	"time"

	"cardex.eu/discovery/internal/families/familia_a/fr_sirene"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID   = "A"
	familyName = "Registros mercantiles federales y regionales"
)

// FamilyA orchestrates all registered sub-techniques for family A.
type FamilyA struct {
	techniques map[string]runner.SubTechnique // country → sub-technique
}

// New builds FamilyA, wiring the sub-techniques that are active in this sprint.
// token:       INSEE OAuth2 Bearer token (empty → unauthenticated, 429s expected).
// ratePerMin:  requests per minute for the INSEE API (recommend ≤25 on free tier).
func New(graph kg.KnowledgeGraph, token string, ratePerMin int) *FamilyA {
	fa := &FamilyA{
		techniques: make(map[string]runner.SubTechnique),
	}
	// A.FR.1 — INSEE Sirene
	fa.techniques["FR"] = fr_sirene.New(graph, token, ratePerMin)
	return fa
}

func (f *FamilyA) FamilyID() string { return familyID }
func (f *FamilyA) Name() string     { return familyName }

// Run executes the sub-technique registered for country and returns an aggregated
// FamilyResult. Returns an error if no sub-technique is registered for the
// requested country.
func (f *FamilyA) Run(ctx context.Context, country string) (*runner.FamilyResult, error) {
	st, ok := f.techniques[country]
	if !ok {
		return nil, fmt.Errorf("familia_a: no sub-technique registered for country %q", country)
	}

	start := time.Now()
	result := &runner.FamilyResult{
		FamilyID:  familyID,
		Country:   country,
		StartedAt: start,
	}

	subResult, err := st.Run(ctx)
	if err != nil {
		result.TotalErrors++
		result.SubResults = append(result.SubResults, subResult)
		result.FinishedAt = time.Now()
		result.Duration = time.Since(start)
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(0)
		return result, fmt.Errorf("familia_a.Run %s: %w", country, err)
	}

	result.SubResults = append(result.SubResults, subResult)
	result.TotalNew += subResult.Discovered
	result.TotalErrors += subResult.Errors
	result.FinishedAt = time.Now()
	result.Duration = time.Since(start)

	metrics.HealthCheckStatus.WithLabelValues(familyID).Set(1)
	return result, nil
}

// HealthCheck verifies that the INSEE Sirene API is reachable and the token
// is valid by issuing a minimal request (nombre=1).
func (f *FamilyA) HealthCheck(ctx context.Context) error {
	st, ok := f.techniques["FR"]
	if !ok {
		return nil // no FR sub-technique registered — nothing to check
	}

	sirene, ok := st.(*fr_sirene.Sirene)
	if !ok {
		return nil
	}
	return sirene.HealthCheck(ctx)
}
