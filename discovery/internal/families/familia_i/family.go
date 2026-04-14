// Package familia_i implements Family I — Inspection & certification networks.
//
// Sprint 10 establishes the Family I skeleton with one active sub-technique
// (I.NL.1 RDW APK via Open Data API) and six deferred skeletons.
//
// Inspection stations are adjacent signals — they confirm that an entity holds
// a valid inspection authorisation, which is highly correlated with automotive
// dealer operations. They are stored with MetadataJSON.is_dealer_candidate=false
// and a reduced confidence weight (0.05).
//
// Active sub-techniques:
//
//   - I.NL.1 — RDW APK inspection stations (NL) via SODA Open Data API
//
// Deferred (Sprint 11+):
//
//   - I.DE.1 — DEKRA stations (DE) — Nuxt.js SPA; API endpoint unknown
//   - I.DE.2 — TÜV stations (DE)  — multi-org (Rheinland/SÜD/NORD/Thüringen/GTÜ)
//   - I.FR.1 — DEKRA/CT centres (FR) — SPA API endpoint unknown
//   - I.ES.1 — ITV stations (ES) — DGT ArcGIS service URL unknown
//   - I.BE.1 — CT stations (BE) — dual-network (AUTOSÉCURITÉ + GOCA); APIs unknown
//   - I.CH.1 — MFK stations (CH) — cantonal; no unified API
//   - I.XX.1 — Bosch Car Service (pan-EU) — React SPA; API unknown
//
// Country → sub-technique mapping:
//
//	NL → I.NL.1 (RDW APK) + I.XX.1 (Bosch Car Service, deferred)
//	DE → I.DE.1 (DEKRA, deferred) + I.DE.2 (TÜV, deferred) + I.XX.1 (Bosch, deferred)
//	FR → I.FR.1 (DEKRA/CT, deferred) + I.XX.1 (Bosch, deferred)
//	ES → I.ES.1 (ITV, deferred) + I.XX.1 (Bosch, deferred)
//	BE → I.BE.1 (CT, deferred) + I.XX.1 (Bosch, deferred)
//	CH → I.CH.1 (MFK, deferred) + I.XX.1 (Bosch, deferred)
package familia_i

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/families/familia_i/bosch_car_service"
	"cardex.eu/discovery/internal/families/familia_i/ct_be"
	"cardex.eu/discovery/internal/families/familia_i/dekra_de"
	"cardex.eu/discovery/internal/families/familia_i/dekra_fr"
	"cardex.eu/discovery/internal/families/familia_i/itv_es"
	"cardex.eu/discovery/internal/families/familia_i/mfk_ch"
	"cardex.eu/discovery/internal/families/familia_i/rdw_apk"
	"cardex.eu/discovery/internal/families/familia_i/tuv_de"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID   = "I"
	familyName = "Inspection & certification networks"
)

// FamilyI orchestrates all I inspection-network sub-techniques.
type FamilyI struct {
	rdwAPK       *rdw_apk.RDWAPK
	dekraDE      *dekra_de.DekraDE
	tuvDE        *tuv_de.TuvDE
	bosch        *bosch_car_service.BoschCarService
	dekraFR      *dekra_fr.DekraFR
	itvES        *itv_es.ITVES
	ctBE         *ct_be.CTBE
	mfkCH        *mfk_ch.MFKCH
	log          *slog.Logger
}

// New constructs a FamilyI with all registered sub-techniques.
func New(graph kg.KnowledgeGraph) *FamilyI {
	return &FamilyI{
		rdwAPK:  rdw_apk.New(graph),
		dekraDE: dekra_de.New(graph),
		tuvDE:   tuv_de.New(graph),
		bosch:   bosch_car_service.New(graph),
		dekraFR: dekra_fr.New(graph),
		itvES:   itv_es.New(graph),
		ctBE:    ct_be.New(graph),
		mfkCH:   mfk_ch.New(graph),
		log:     slog.Default().With("family", familyID),
	}
}

// FamilyID returns the single-letter family identifier.
func (f *FamilyI) FamilyID() string { return familyID }

// Name returns the human-readable family label.
func (f *FamilyI) Name() string { return familyName }

// Run executes all I sub-techniques for the given country.
func (f *FamilyI) Run(ctx context.Context, country string) (*runner.FamilyResult, error) {
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
			f.log.Warn("familia_i: sub-technique error", "sub", label, "country", country, "err", err)
		}
	}

	switch country {
	case "NL":
		res, err := f.rdwAPK.Run(ctx)
		collect(res, err, "rdw_apk")
		res2, err2 := f.bosch.Run(ctx, country)
		collect(res2, err2, "bosch_car_service")

	case "DE":
		res, err := f.dekraDE.Run(ctx)
		collect(res, err, "dekra_de")
		res2, err2 := f.tuvDE.Run(ctx)
		collect(res2, err2, "tuv_de")
		res3, err3 := f.bosch.Run(ctx, country)
		collect(res3, err3, "bosch_car_service")

	case "FR":
		res, err := f.dekraFR.Run(ctx)
		collect(res, err, "dekra_fr")
		res2, err2 := f.bosch.Run(ctx, country)
		collect(res2, err2, "bosch_car_service")

	case "ES":
		res, err := f.itvES.Run(ctx)
		collect(res, err, "itv_es")
		res2, err2 := f.bosch.Run(ctx, country)
		collect(res2, err2, "bosch_car_service")

	case "BE":
		res, err := f.ctBE.Run(ctx)
		collect(res, err, "ct_be")
		res2, err2 := f.bosch.Run(ctx, country)
		collect(res2, err2, "bosch_car_service")

	case "CH":
		res, err := f.mfkCH.Run(ctx)
		collect(res, err, "mfk_ch")
		res2, err2 := f.bosch.Run(ctx, country)
		collect(res2, err2, "bosch_car_service")

	default:
		return result, fmt.Errorf("familia_i: unsupported country %q", country)
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

// HealthCheck verifies that the RDW Open Data endpoint is reachable (proxy for
// Family I health; all other sub-techniques are deferred skeletons).
func (f *FamilyI) HealthCheck(ctx context.Context) error {
	if err := f.rdwAPK.HealthCheck(ctx); err != nil {
		metrics.HealthCheckStatus.WithLabelValues(familyID).Set(0)
		return fmt.Errorf("familia_i health: RDW APK: %w", err)
	}
	metrics.HealthCheckStatus.WithLabelValues(familyID).Set(1)
	return nil
}
