// Package familia_a implements Family A — Registros mercantiles federales y regionales.
//
// Sprint 2: all six sub-techniques are active:
//   - A.FR.1 — INSEE Sirene API (France)
//   - A.DE.1 — OffeneRegister.de (Germany)
//   - A.ES.1 — BORME datosabiertos API (Spain)
//   - A.NL.1 — KvK Handelsregister Zoeken API + bulk dataset (Netherlands)
//   - A.BE.1 — KBO/BCE Open Data (Belgium)
//   - A.CH.1 — opendata.swiss CKAN + Zefix HTML fallback (Switzerland)
package familia_a

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"cardex.eu/discovery/internal/families/familia_a/be_kbo"
	"cardex.eu/discovery/internal/families/familia_a/ch_zefix"
	"cardex.eu/discovery/internal/families/familia_a/de_offeneregister"
	"cardex.eu/discovery/internal/families/familia_a/es_borme"
	"cardex.eu/discovery/internal/families/familia_a/fr_sirene"
	"cardex.eu/discovery/internal/families/familia_a/nl_kvk"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID   = "A"
	familyName = "Registros mercantiles federales y regionales"
)

// Config holds all per-family configuration needed by Sprint 2 sub-techniques.
type Config struct {
	// FR — INSEE Sirene API
	InseeToken      string
	InseeRatePerMin int // defaults to 25 if zero

	// DE — OffeneRegister.de
	// Path to the decompressed SQLite. Defaults to ./data/offeneregister.db.
	OffeneRegisterDBPath string

	// NL — KvK Handelsregister
	// API key for the KvK Zoeken v2 API (Path 2). Empty → Path 2 skipped.
	KvKAPIKey string

	// BE — KBO/BCE Open Data
	KBOUser string // KBO_USER env var
	KBOPass string // KBO_PASS env var
}

// FamilyA orchestrates all registered sub-techniques for family A.
type FamilyA struct {
	techniques map[string]runner.SubTechnique // country code → sub-technique
}

// New builds FamilyA, wiring all six sub-techniques for Sprint 2.
// db is the shared KG SQLite connection (used by the KvK sub-technique for
// rate-limit state persistence).
func New(graph kg.KnowledgeGraph, cfg *Config, db *sql.DB) *FamilyA {
	ratePerMin := cfg.InseeRatePerMin
	if ratePerMin <= 0 {
		ratePerMin = 25
	}
	dbPath := cfg.OffeneRegisterDBPath
	if dbPath == "" {
		dbPath = "./data/offeneregister.db"
	}

	fa := &FamilyA{
		techniques: make(map[string]runner.SubTechnique),
	}
	fa.techniques["FR"] = fr_sirene.New(graph, cfg.InseeToken, ratePerMin)
	fa.techniques["DE"] = de_offeneregister.New(graph, dbPath)
	fa.techniques["ES"] = es_borme.New(graph)
	fa.techniques["NL"] = nl_kvk.New(graph, db, cfg.KvKAPIKey)
	fa.techniques["BE"] = be_kbo.New(graph, cfg.KBOUser, cfg.KBOPass)
	fa.techniques["CH"] = ch_zefix.New(graph)
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
// is valid by issuing a minimal request.
func (f *FamilyA) HealthCheck(ctx context.Context) error {
	st, ok := f.techniques["FR"]
	if !ok {
		return nil
	}
	sirene, ok := st.(*fr_sirene.Sirene)
	if !ok {
		return nil
	}
	return sirene.HealthCheck(ctx)
}
