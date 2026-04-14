// Package itv_es implements sub-technique I.ES.1 — ITV inspection stations (ES).
//
// # Current status: SKELETON
//
// ITV (Inspección Técnica de Vehículos) is Spain's mandatory vehicle inspection
// scheme. Each Spanish autonomous community manages its own ITV network; there is
// no single national API. The main aggregator is:
//
//	https://sede.dgt.gob.es/es/tu-coche-y-el-carnet/itv/localizador-itv/
//
// The DGT (Dirección General de Tráfico) locator is a map-based SPA backed by
// an ArcGIS Feature Service at:
//
//	https://services.arcgis.com/…/query?where=1%3D1&outFields=*&f=json
//
// The exact ArcGIS service URL requires network inspection. ArcGIS Feature Services
// are public and paginated (resultOffset / resultRecordCount).
//
// Planned approach (Sprint 11+):
//  1. Identify the ArcGIS service URL from the DGT SPA.
//  2. Paginate with resultOffset=0, 1000, 2000… until no more features.
//  3. Upsert with IdentifierITVStationID; MetadataJSON = is_dealer_candidate:false.
//
// Rate limiting: 1 req / 3 s.
// ConfidenceContributed: 0.05 (BaseWeights["I"]).
package itv_es

import (
	"context"
	"log/slog"
	"time"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID    = "I"
	subTechID   = "I.ES.1"
	subTechName = "ITV inspection stations (ES)"
	countryES   = "ES"
)

// ITVES implements the I.ES.1 sub-technique (skeleton).
type ITVES struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs an ITVES executor.
func New(graph kg.KnowledgeGraph) *ITVES {
	return &ITVES{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (i *ITVES) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (i *ITVES) Name() string { return subTechName }

// Run logs the deferred-blocker reason and returns an empty result.
func (i *ITVES) Run(_ context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	i.log.Info("itv_es: I.ES.1 deferred — DGT ArcGIS service URL requires network inspection",
		"country", countryES,
		"planned", "Sprint 11: identify ArcGIS Feature Service URL from DGT SPA + paginated fetch",
	)
	return &runner.SubTechniqueResult{
		SubTechniqueID: subTechID,
		Country:        countryES,
		Duration:       time.Since(start),
	}, nil
}
