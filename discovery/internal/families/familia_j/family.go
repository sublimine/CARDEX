// Package familia_j implements Family J — sub-jurisdiction regional registries.
//
// Family J extends Family A (national registries) with sub-national coverage:
// regional Handelsregister, departmental registries, provincial classifiers,
// and vehicle registration authority classifiers that enrich existing KG
// entities with granular geographic metadata.
//
// Sprint 13 delivery (business registry classifiers):
//   - J.FR.1 Pappers.fr (active): APE 4511Z vehicle dealers per departement
//   - J.NL.1 Province classifier (active): postal code -> province (no API)
//   - J.BE.1 Gewest classifier (active): postal code -> gewest (no API)
//   - J.DE stub: covered by A.DE OffeneRegister + portal barriers
//   - J.ES.1 stub: BORME PDF requires LayoutLMv3 (deferred Sprint 21+)
//   - J.CH stub: Zefix covers >98%; cantonal portals heterogeneous
//
// Sprint 27 delivery (vehicle registration authority classifiers):
//   - J.DE.2 Kfz-Zulassung classifier (active): PLZ -> Bundesland ISO code
//   - J.ES.2 DGT Jefaturas classifier (active): PLZ -> province ISO code
//   - J.CH.2 Strassenverkehrsamt classifier (active): PLZ -> canton ISO code
//
// BaseWeights["J"] = 0.05 -- sub-jurisdiction registries extend A, not primary.
package familia_j

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/families/familia_j/borme_es"
	"cardex.eu/discovery/internal/families/familia_j/cantonal_ch"
	"cardex.eu/discovery/internal/families/familia_j/gewest_be"
	"cardex.eu/discovery/internal/families/familia_j/handelsregister_de"
	"cardex.eu/discovery/internal/families/familia_j/jefaturas_es"
	"cardex.eu/discovery/internal/families/familia_j/kfz_de"
	"cardex.eu/discovery/internal/families/familia_j/pappers"
	"cardex.eu/discovery/internal/families/familia_j/province_nl"
	"cardex.eu/discovery/internal/families/familia_j/strassenverkehr_ch"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID   = "J"
	familyName = "Sub-jurisdiction regional registries"
)

// FamilyJ orchestrates all J sub-jurisdiction sub-techniques.
type FamilyJ struct {
	pappers           *pappers.Pappers
	provinceNL        *province_nl.ProvinceClassifier
	gewestBE          *gewest_be.GewestClassifier
	handelsregisterDE *handelsregister_de.HandelsregisterDE
	bormeES           *borme_es.BormeES
	cantonalCH        *cantonal_ch.CantonalCH
	kfzDE             *kfz_de.KfzDE
	jefaturasES       *jefaturas_es.JefaturasES
	strassenverkehrCH *strassenverkehr_ch.StrassenverkehrCH
	log               *slog.Logger
}

// New constructs a FamilyJ with production configuration.
// pappersAPIKey is the Pappers.fr API token; pass "" for unauthenticated (rate-limited).
func New(graph kg.KnowledgeGraph, pappersAPIKey string) *FamilyJ {
	return &FamilyJ{
		pappers:           pappers.New(graph, pappersAPIKey),
		provinceNL:        province_nl.New(graph),
		gewestBE:          gewest_be.New(graph),
		handelsregisterDE: handelsregister_de.New(graph),
		bormeES:           borme_es.New(graph),
		cantonalCH:        cantonal_ch.New(graph),
		kfzDE:             kfz_de.New(graph),
		jefaturasES:       jefaturas_es.New(graph),
		strassenverkehrCH: strassenverkehr_ch.New(graph),
		log:               slog.Default().With("family", familyID),
	}
}

// FamilyID returns the single-letter family identifier.
func (f *FamilyJ) FamilyID() string { return familyID }

// Name returns the human-readable family label.
func (f *FamilyJ) Name() string { return familyName }

// Run executes J sub-techniques for the given country.
func (f *FamilyJ) Run(ctx context.Context, country string) (*runner.FamilyResult, error) {
	start := time.Now()
	result := &runner.FamilyResult{
		FamilyID:  familyID,
		Country:   country,
		StartedAt: start,
	}

	collect := func(res *runner.SubTechniqueResult, err error, label string) {
		if res != nil {
			result.SubResults = append(result.SubResults, res)
			result.TotalNew += res.Discovered
			result.TotalErrors += res.Errors
		}
		if err != nil {
			result.TotalErrors++
			f.log.Warn("familia_j: sub-technique error",
				"sub", label, "country", country, "err", err)
		}
	}

	switch country {
	case "FR":
		res, err := f.pappers.Run(ctx)
		collect(res, err, "pappers")

	case "NL":
		res, err := f.provinceNL.Run(ctx)
		collect(res, err, "province_nl")

	case "BE":
		res, err := f.gewestBE.Run(ctx)
		collect(res, err, "gewest_be")

	case "DE":
		// Business registry (deferred — A.DE OffeneRegister covers; portal barriers)
		res, err := f.handelsregisterDE.Run(ctx)
		collect(res, err, "handelsregister_de")
		// Vehicle registration authority classifier (Sprint 27 — ACTIVE)
		res2, err2 := f.kfzDE.Run(ctx)
		collect(res2, err2, "kfz_de")

	case "ES":
		// Business registry (deferred — BORME PDF requires LayoutLMv3)
		res, err := f.bormeES.Run(ctx)
		collect(res, err, "borme_es")
		// DGT Jefatura Provincial classifier (Sprint 27 — ACTIVE)
		res2, err2 := f.jefaturasES.Run(ctx)
		collect(res2, err2, "jefaturas_es")

	case "CH":
		// Business registry (deferred — Zefix federal API covers >98%)
		res, err := f.cantonalCH.Run(ctx)
		collect(res, err, "cantonal_ch")
		// Strassenverkehrsamt cantonal classifier (Sprint 27 — ACTIVE)
		res2, err2 := f.strassenverkehrCH.Run(ctx)
		collect(res2, err2, "strassenverkehr_ch")

	default:
		return result, fmt.Errorf("familia_j: unsupported country %q", country)
	}

	result.FinishedAt = time.Now()
	result.Duration = time.Since(start)

	if result.TotalErrors > 0 {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(0)
	} else {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(1)
	}
	return result, nil
}
