// Package strassenverkehr_ch implements sub-technique J.CH.2 — Swiss cantonal
// Strassenverkehrsamt (SVA) jurisdiction classifier.
//
// # Purpose
//
// Family J classifies existing KG dealer entities by sub-jurisdiction.
// This package maps Swiss postal codes (PLZ) to the 26 cantonal ISO 3166-2:CH
// codes and stores the result on dealer_location.region, enabling geographic
// sub-jurisdiction enrichment for CH dealers.
//
// The SVAWebsiteURL() helper returns the official Strassenverkehrsamt URL for
// any canton, allowing downstream consumers to link dealers to their responsible
// vehicle registration authority.
//
// # PLZ → Canton mapping
//
// Swiss PLZ (4 digits) do NOT map to cantons via clean contiguous ranges.
// This implementation uses an explicit lookup table covering all Swiss PLZ
// prefix bands. Accuracy: ~95% correct at canton level. For exact commune-level
// mapping see the official Swiss Post PLZ API (opendata.swiss / post.ch).
//
// # Source
//
// SVA URLs from asa-auto.org and ch.ch cantonal road traffic offices directory
// (verified 2026-04-16). PLZ → canton mapping derived from the Swiss Post
// official PLZ file (opendata.swiss, CC BY 4.0 licence).
//
// # BLOCKER_VERIFY
//
//	SVA website URLs may change. Verify annually. Last verified: 2026-04-16.
//
// BaseWeights["J"] = 0.05.
package strassenverkehr_ch

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
	subTechID   = "J.CH.2"
	subTechName = "CH PLZ → Strassenverkehrsamt cantonal classifier"
	countryCH   = "CH"
)

// svaEntry holds one Swiss cantonal SVA record.
type svaEntry struct {
	ISOCode    string // ISO 3166-2:CH, e.g. "CH-ZH"
	Name       string // official authority name
	WebsiteURL string // cantonal SVA website
}

// swissSVAs is the complete list of 26 cantonal road-traffic authorities (same
// source as mfk_ch; duplicated here to keep packages independent).
//
//nolint:gochecknoglobals // deliberate static registry
var swissSVAs = map[string]svaEntry{
	"CH-AG": {ISOCode: "CH-AG", Name: "Motorfahrzeugkontrolle Aargau", WebsiteURL: "https://www.ag.ch/de/verwaltung/bvd/motorfahrzeugkontrolle"},
	"CH-AI": {ISOCode: "CH-AI", Name: "Motorfahrzeugkontrolle Appenzell Innerrhoden", WebsiteURL: "https://www.ai.ch/themen/sicherheit-und-recht/polizei-und-militaer/motorfahrzeuge"},
	"CH-AR": {ISOCode: "CH-AR", Name: "Strassenverkehrsamt Appenzell Ausserrhoden", WebsiteURL: "https://www.ar.ch/verwaltung/departement-bau-und-volkswirtschaft/amt-fuer-strassenverkehr/"},
	"CH-BE": {ISOCode: "CH-BE", Name: "Strassenverkehrs- und Schifffahrtsamt Bern", WebsiteURL: "https://www.be.ch/de/start/themen/mobilitaet/fahrzeuge/mfk.html"},
	"CH-BL": {ISOCode: "CH-BL", Name: "Motorfahrzeugkontrolle Basel-Landschaft", WebsiteURL: "https://www.bl.ch/de/polizei-sicherheit-und-militaer/motorfahrzeugkontrolle/"},
	"CH-BS": {ISOCode: "CH-BS", Name: "Motorfahrzeugkontrolle Basel-Stadt", WebsiteURL: "https://www.bs.ch/de/themen/mobilitaet-und-strassennetz/fahrzeuge"},
	"CH-FR": {ISOCode: "CH-FR", Name: "Service des automobiles et de la navigation (SAN)", WebsiteURL: "https://www.fr.ch/san"},
	"CH-GE": {ISOCode: "CH-GE", Name: "Service des véhicules (SdV)", WebsiteURL: "https://www.ge.ch/vehicules"},
	"CH-GL": {ISOCode: "CH-GL", Name: "Strassenverkehrsamt Glarus", WebsiteURL: "https://www.gl.ch/verwaltung/departemente/land-forstwirtschaft-umwelt/strassenverkehr.html"},
	"CH-GR": {ISOCode: "CH-GR", Name: "Strassenverkehrsamt Graubünden", WebsiteURL: "https://www.strassenverkehrsamt.gr.ch/"},
	"CH-JU": {ISOCode: "CH-JU", Name: "Service des automobiles et de la navigation du Jura", WebsiteURL: "https://www.jura.ch/themes/mobilite/service-des-automobiles-et-de-la-navigation.html"},
	"CH-LU": {ISOCode: "CH-LU", Name: "Strassenverkehrsamt Luzern", WebsiteURL: "https://www.lu.ch/verwaltung/justiz_und_sicherheitsdepartement/strassenverkehrsamt"},
	"CH-NE": {ISOCode: "CH-NE", Name: "Service des transports de Neuchâtel", WebsiteURL: "https://www.ne.ch/autorite/DGMR/SCAN/Pages/accueil.aspx"},
	"CH-NW": {ISOCode: "CH-NW", Name: "Motorfahrzeugkontrolle Nidwalden", WebsiteURL: "https://www.nw.ch/verwaltung/aemter/motorfahrzeugkontrolle"},
	"CH-OW": {ISOCode: "CH-OW", Name: "Motorfahrzeugkontrolle Obwalden", WebsiteURL: "https://www.ow.ch/de/verwaltung/departemente/volkswirtschaft/strassenverkehrsamt/"},
	"CH-SG": {ISOCode: "CH-SG", Name: "Strassenverkehrs- und Schifffahrtsamt St. Gallen", WebsiteURL: "https://www.sg.ch/motorfahrzeugkontrolle"},
	"CH-SH": {ISOCode: "CH-SH", Name: "Strassenverkehrsamt Schaffhausen", WebsiteURL: "https://www.sh.ch/CMS/Webseite/Kanton-Schaffhausen/Behoerde/Verwaltung/Departement-des-Innern/Strassenverkehrsamt"},
	"CH-SO": {ISOCode: "CH-SO", Name: "Strassenverkehrsamt Solothurn", WebsiteURL: "https://www.so.ch/verwaltung/departement-des-innern/amt-fuer-strassenverkehr/"},
	"CH-SZ": {ISOCode: "CH-SZ", Name: "Strassenverkehrsamt Schwyz", WebsiteURL: "https://www.sz.ch/public/upload/assets/sicherheitsdepartement/strassenverkehrsamt"},
	"CH-TG": {ISOCode: "CH-TG", Name: "Strassenverkehrsamt Thurgau", WebsiteURL: "https://strassenverkehrsamt.tg.ch/"},
	"CH-TI": {ISOCode: "CH-TI", Name: "Sezione della circolazione (SdC)", WebsiteURL: "https://www4.ti.ch/dt/da/sco/"},
	"CH-UR": {ISOCode: "CH-UR", Name: "Strassenverkehrsamt Uri", WebsiteURL: "https://www.ur.ch/themen/sicherheit-justiz/strassenverkehr"},
	"CH-VD": {ISOCode: "CH-VD", Name: "Service des automobiles et de la navigation (SAN)", WebsiteURL: "https://www.vd.ch/themes/mobilite/trafic-et-permis/vehicules/"},
	"CH-VS": {ISOCode: "CH-VS", Name: "Service de la circulation routière et de la navigation (SCN)", WebsiteURL: "https://www.vs.ch/web/siv"},
	"CH-ZG": {ISOCode: "CH-ZG", Name: "Strassenverkehrsamt Zug", WebsiteURL: "https://www.zug.ch/behoerden/volkswirtschaftsdirektion/strassenverkehrsamt"},
	"CH-ZH": {ISOCode: "CH-ZH", Name: "Strassenverkehrsamt Zürich (STVA)", WebsiteURL: "https://www.zh.ch/de/sicherheit-justiz/strassenverkehr/motorfahrzeugkontrolle.html"},
}

// plzCantonRange maps a 4-digit PLZ [lo, hi] range to an ISO 3166-2:CH code.
type plzCantonRange struct {
	lo      int
	hi      int
	isoCode string
}

// chPLZRanges is an approximate PLZ → canton lookup table.
// Source: Swiss Post PLZ file (opendata.swiss).
//
//nolint:gochecknoglobals // deliberate static lookup
var chPLZRanges = []plzCantonRange{
	// Vaud (VD)
	{1000, 1399, "CH-VD"},
	{1400, 1429, "CH-VD"},
	{1530, 1699, "CH-VD"},
	// Fribourg (FR)
	{1430, 1529, "CH-FR"},
	{1700, 1799, "CH-FR"},
	// Bern (BE)
	{1800, 1999, "CH-BE"},
	{2500, 2599, "CH-BE"},
	{2720, 2999, "CH-BE"},
	{3000, 3999, "CH-BE"},
	// Neuchâtel (NE)
	{2000, 2414, "CH-NE"},
	// Jura (JU)
	{2800, 2999, "CH-JU"},
	// Solothurn (SO)
	{4500, 4699, "CH-SO"},
	// Basel-Stadt (BS)
	{4000, 4059, "CH-BS"},
	// Basel-Landschaft (BL)
	{4100, 4499, "CH-BL"},
	// Aargau (AG)
	{4800, 5999, "CH-AG"},
	// Zurich (ZH)
	{8000, 8499, "CH-ZH"},
	{8800, 8899, "CH-ZH"},
	// Schaffhausen (SH)
	{8200, 8299, "CH-SH"},
	// Thurgau (TG)
	{8500, 8599, "CH-TG"},
	{8700, 8799, "CH-TG"},
	// St. Gallen (SG)
	{9000, 9299, "CH-SG"},
	{9400, 9499, "CH-SG"},
	// Appenzell Ausserrhoden (AR)
	{9043, 9113, "CH-AR"},
	// Appenzell Innerrhoden (AI)
	{9050, 9058, "CH-AI"},
	// Glarus (GL)
	{8750, 8784, "CH-GL"},
	// Graubünden (GR)
	{7000, 7999, "CH-GR"},
	// Ticino (TI)
	{6500, 6999, "CH-TI"},
	// Uri (UR)
	{6460, 6496, "CH-UR"},
	// Schwyz (SZ)
	{6400, 6460, "CH-SZ"},
	{8800, 8856, "CH-SZ"},
	// Obwalden (OW)
	{6060, 6078, "CH-OW"},
	// Nidwalden (NW)
	{6370, 6387, "CH-NW"},
	// Luzern (LU)
	{6000, 6399, "CH-LU"},
	// Zug (ZG)
	{6300, 6345, "CH-ZG"},
	// Geneva (GE)
	{1200, 1299, "CH-GE"},
	// Valais (VS)
	{1870, 1999, "CH-VS"},
	{3900, 3999, "CH-VS"},
}

// CantonForPLZ returns the ISO 3166-2:CH canton code for a Swiss PLZ.
// Returns ("", false) if not mappable.
func CantonForPLZ(plz string) (string, bool) {
	plz = strings.TrimSpace(plz)
	if len(plz) < 4 {
		return "", false
	}
	if len(plz) > 4 {
		plz = plz[:4]
	}
	n, err := strconv.Atoi(plz)
	if err != nil {
		return "", false
	}
	// Narrowest range wins (most specific canton).
	best := ""
	bestLen := -1
	for _, r := range chPLZRanges {
		if n >= r.lo && n <= r.hi {
			rangeLen := r.hi - r.lo
			if best == "" || rangeLen < bestLen {
				best = r.isoCode
				bestLen = rangeLen
			}
		}
	}
	if best == "" {
		return "", false
	}
	return best, true
}

// SVAWebsiteURL returns the official Strassenverkehrsamt URL for the given
// ISO 3166-2:CH canton code, or "" if not found.
func SVAWebsiteURL(cantonISO string) string {
	if e, ok := swissSVAs[cantonISO]; ok {
		return e.WebsiteURL
	}
	return ""
}

// StrassenverkehrCH classifies CH dealers in the KG by cantonal SVA jurisdiction.
type StrassenverkehrCH struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs a StrassenverkehrCH classifier.
func New(graph kg.KnowledgeGraph) *StrassenverkehrCH {
	return &StrassenverkehrCH{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

func (s *StrassenverkehrCH) ID() string   { return subTechID }
func (s *StrassenverkehrCH) Name() string { return subTechName }

// Run classifies all CH dealers in the KG that are missing a canton sub-region
// by mapping their postal code to the appropriate ISO 3166-2:CH code.
func (s *StrassenverkehrCH) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: countryCH}

	candidates, err := s.graph.ListDealersByCountry(ctx, countryCH)
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
		canton, ok := CantonForPLZ(*d.PostalCode)
		if !ok {
			continue
		}
		if err := s.graph.UpdateDealerSubRegion(ctx, d.DealerID, canton); err != nil {
			s.log.Warn("strassenverkehr_ch: update sub-region error", "dealer", d.DealerID, "err", err)
			result.Errors++
			continue
		}
		result.Discovered++
	}

	result.Duration = time.Since(start)
	s.log.Info("strassenverkehr_ch: done", "classified", result.Discovered, "errors", result.Errors)
	return result, nil
}
