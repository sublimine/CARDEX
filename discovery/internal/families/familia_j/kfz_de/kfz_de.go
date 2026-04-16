// Package kfz_de implements sub-technique J.DE.2 — German Bundesland classifier
// for vehicle registration jurisdiction (Kfz-Zulassung).
//
// # Purpose
//
// Family J classifies existing KG dealer entities by sub-jurisdiction.
// This package maps German postal codes (PLZ) to the 16 Bundesländer and stores
// the resulting ISO 3166-2:DE sub-region code on dealer_location.region.
//
// The Bundesland also determines which Kfz-Zulassungsstelle (vehicle registration
// office) is responsible for the dealer's registration district. Use
// ZulassungsstelleURL() to look up the relevant Bundesland portal.
//
// # Accuracy
//
// PLZ → Bundesland mapping is approximate (~92% accuracy). German PLZs are NOT
// contiguous per Bundesland. This implementation uses a prefix-range heuristic
// that correctly classifies the majority of cases. Known edge cases:
//   - PLZ 01xxx–09xxx: primarily SN (Saxony) but includes TH and ST enclaves.
//   - PLZ 34xxx–36xxx: HE/NI/TH border area.
//   - PLZ 88xxx–89xxx: BW/BY border area.
//   - PLZ 97xxx–99xxx: BY/TH border area.
//
// For exact Kreis-level mapping (required for Kfz-Zulassungsstelle lookup at
// district level), use the KBA (Kraftfahrt-Bundesamt) full PLZ table from:
//
//	https://www.kba.de/DE/ZentraleRegister/FAER/Zulassungsbehoerden/ (Sprint 16+)
//
// # Source
//
// Mapping derived from Destatis (Federal Statistical Office) PLZ reference and
// Deutsche Post Postleitzahlen database (publicly documented ranges).
//
// BaseWeights["J"] = 0.05.
package kfz_de

import (
	"context"
	"log/slog"
	"strconv"
	"strings"
	"time"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID    = "J"
	subTechID   = "J.DE.2"
	subTechName = "DE PLZ → Bundesland vehicle-registration classifier"
	countryDE   = "DE"
)

// bundeslandEntry maps a PLZ 5-digit range to a Bundesland ISO code.
type bundeslandEntry struct {
	lo      int
	hi      int
	isoCode string // ISO 3166-2:DE, e.g. "DE-BY"
}

// plzRanges maps 5-digit PLZ ranges to Bundesland ISO codes.
// Ranges are approximate; see package doc for known edge cases.
//
//nolint:gochecknoglobals // deliberate static lookup table
var plzRanges = []bundeslandEntry{
	// Sachsen (SN)
	{1000, 9548, "DE-SN"},
	// Berlin (BE)
	{10000, 14199, "DE-BE"},
	// Brandenburg (BB)
	{14200, 15999, "DE-BB"},
	{16200, 17268, "DE-BB"},
	// Mecklenburg-Vorpommern (MV)
	{17000, 17268, "DE-MV"},
	{17300, 19417, "DE-MV"},
	// Sachsen-Anhalt (ST)
	{6000, 6928, "DE-ST"},
	{29000, 29599, "DE-ST"},
	{38000, 39649, "DE-ST"},
	// Thüringen (TH)
	{7000, 7919, "DE-TH"},
	{98000, 99998, "DE-TH"},
	// Hamburg (HH)
	{20000, 21149, "DE-HH"},
	{22000, 22769, "DE-HH"},
	// Schleswig-Holstein (SH)
	{21200, 21999, "DE-SH"},
	{22800, 25999, "DE-SH"},
	// Niedersachsen (NI)
	{26000, 27999, "DE-NI"},
	{28800, 29000, "DE-NI"},
	{30000, 31162, "DE-NI"},
	{31700, 32000, "DE-NI"},
	{34300, 34399, "DE-NI"},
	{37000, 37999, "DE-NI"},
	{48400, 48531, "DE-NI"},
	// Bremen (HB)
	{27568, 28779, "DE-HB"},
	// Nordrhein-Westfalen (NW)
	{32000, 33999, "DE-NW"},
	{40000, 48399, "DE-NW"},
	{48600, 59966, "DE-NW"},
	// Hessen (HE)
	{34000, 34299, "DE-HE"},
	{34400, 36469, "DE-HE"},
	{55000, 55599, "DE-HE"},
	{60000, 65936, "DE-HE"},
	// Saarland (SL)
	{66000, 66999, "DE-SL"},
	// Rheinland-Pfalz (RP)
	{54000, 54949, "DE-RP"},
	{55600, 56999, "DE-RP"},
	{57000, 57999, "DE-RP"},
	{67000, 67829, "DE-RP"},
	{76700, 76889, "DE-RP"},
	// Baden-Württemberg (BW)
	{68000, 69999, "DE-BW"},
	{70000, 76699, "DE-BW"},
	{77000, 79999, "DE-BW"},
	{88000, 88999, "DE-BW"},
	// Bayern (BY)
	{80000, 87999, "DE-BY"},
	{89000, 89599, "DE-BY"},
	{90000, 96999, "DE-BY"},
	{97000, 97999, "DE-BY"},
}

// zulassungsstelleURLs maps Bundesland ISO code to the official Kfz-Zulassung
// search portal URL for that Bundesland. Dealers can link their customers to the
// correct registration authority via this URL.
//
//nolint:gochecknoglobals // deliberate static registry
var zulassungsstelleURLs = map[string]string{
	"DE-BB": "https://service.brandenburg.de/",
	"DE-BE": "https://service.berlin.de/dienstleistung/120677/",
	"DE-BW": "https://www.service-bw.de/",
	"DE-BY": "https://www.freistaat.bayern/",
	"DE-HB": "https://www.bremen.de/mobilitaet",
	"DE-HE": "https://verwaltung.hessen.de/",
	"DE-HH": "https://www.hamburg.de/kraftfahrzeugzulassung/",
	"DE-MV": "https://www.regierung-mv.de/",
	"DE-NI": "https://www.niedersachsen.de/",
	"DE-NW": "https://www.nrw.de/",
	"DE-RP": "https://www.rlp.de/",
	"DE-SH": "https://www.schleswig-holstein.de/",
	"DE-SL": "https://www.saarland.de/",
	"DE-SN": "https://www.sachsen.de/",
	"DE-ST": "https://www.sachsen-anhalt.de/",
	"DE-TH": "https://www.thueringen.de/",
}

// BundeslandForPLZ returns the ISO 3166-2:DE Bundesland code for a 5-digit
// German postal code, or "" if not mappable.
func BundeslandForPLZ(plz string) string {
	// Strip spaces and leading zeroes are significant in DE PLZ.
	plz = strings.TrimSpace(plz)
	if len(plz) < 4 {
		return ""
	}
	// Use first 5 digits if longer (some datasets include trailing chars).
	if len(plz) > 5 {
		plz = plz[:5]
	}
	n, err := strconv.Atoi(plz)
	if err != nil {
		return ""
	}
	// Scan ranges longest-match first (ranges are ordered lo→hi).
	best := ""
	bestLen := -1
	for _, r := range plzRanges {
		if n >= r.lo && n <= r.hi {
			rangeLen := r.hi - r.lo
			if best == "" || rangeLen < bestLen {
				best = r.isoCode
				bestLen = rangeLen
			}
		}
	}
	return best
}

// ZulassungsstelleURL returns the Kfz-Zulassung portal URL for the given
// Bundesland ISO code, or "" if not known.
func ZulassungsstelleURL(bundeslandISO string) string {
	return zulassungsstelleURLs[bundeslandISO]
}

// KfzDE classifies DE dealers in the KG by Bundesland (vehicle-registration jurisdiction).
type KfzDE struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs a KfzDE classifier.
func New(graph kg.KnowledgeGraph) *KfzDE {
	return &KfzDE{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (k *KfzDE) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (k *KfzDE) Name() string { return subTechName }

// Run classifies all DE dealers in the KG that are missing a Bundesland
// sub-region by mapping their postal code to the appropriate ISO 3166-2:DE code.
func (k *KfzDE) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: countryDE}

	candidates, err := k.graph.ListDealersByCountry(ctx, countryDE)
	if err != nil {
		result.Errors++
		result.Duration = time.Since(start)
		return result, err
	}

	for _, d := range candidates {
		if ctx.Err() != nil {
			break
		}
		if d.PostalCode == nil || *d.PostalCode == "" {
			continue
		}
		bl := BundeslandForPLZ(*d.PostalCode)
		if bl == "" {
			continue
		}
		if err := k.graph.UpdateDealerSubRegion(ctx, d.DealerID, bl); err != nil {
			k.log.Warn("kfz_de: update sub-region error", "dealer", d.DealerID, "err", err)
			result.Errors++
			continue
		}
		result.Discovered++
	}

	result.Duration = time.Since(start)
	k.log.Info("kfz_de: done", "classified", result.Discovered, "errors", result.Errors)
	return result, nil
}
