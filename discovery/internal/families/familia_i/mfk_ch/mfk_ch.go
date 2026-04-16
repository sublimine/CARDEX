// Package mfk_ch implements sub-technique I.CH.1 — Swiss cantonal MFK/SVA offices.
//
// Status: ACTIVE — static registry of 26 cantonal Strassenverkehrsaemter.
//
// MFK (Motorfahrzeugkontrolle) / SVA (Strassenverkehrsamt) is Switzerland's
// cantonal vehicle inspection authority. Each of Switzerland's 26 cantons
// operates its own office; there is no federal station-finder aggregator.
//
// This implementation uses a static registry derived from the ASTRA directory:
//
//	https://www.astra.admin.ch/astra/de/home/fachleute/fahrzeuge/motorfahrzeugkontrolle.html
//
// ConfidenceContributed: 0.05 (BaseWeights["I"]).
package mfk_ch

import (
	"context"
	"fmt"
	"log/slog"
	"net/url"
	"strings"
	"time"

	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID    = "I"
	subTechID   = "I.CH.1"
	subTechName = "Swiss cantonal MFK/SVA offices (CH) — static registry"
	countryCH   = "CH"

	metadataJSON = `{"is_dealer_candidate":false,"entity_type":"inspection_station","operator_network":"MFK_CH"}`
)

// CantonalSVA describes a Swiss cantonal Strassenverkehrsamt entry.
type CantonalSVA struct {
	ISOCode    string // ISO 3166-2:CH, e.g. "CH-ZH"
	Name       string // Canton name in German
	WebsiteURL string // Official SVA/MFK website
}

// swissSVAs is the static registry of all 26 Swiss cantonal offices.
var swissSVAs = []CantonalSVA{
	{"CH-ZH", "Kanton Zuerich", "https://www.zh.ch/de/fahrzeuge-strassenverkehr/fahrzeugpruefung.html"},
	{"CH-BE", "Kanton Bern", "https://www.sv.fin.be.ch/de/start.html"},
	{"CH-LU", "Kanton Luzern", "https://www.strassenverkehr.lu.ch/"},
	{"CH-UR", "Kanton Uri", "https://www.ur.ch/dienstleistungen/6221"},
	{"CH-SZ", "Kanton Schwyz", "https://www.sz.ch/behoerden/volkswirtschaftsdepartement/strassenverkehrsamt.html"},
	{"CH-OW", "Kanton Obwalden", "https://www.ow.ch/verwaltung/dienstleistungen/3600"},
	{"CH-NW", "Kanton Nidwalden", "https://www.nw.ch/strassenverkehrsamt/1"},
	{"CH-GL", "Kanton Glarus", "https://www.gl.ch/verwaltung/departemente/departement-volkswirtschaft/strassenverkehrsamt.html"},
	{"CH-ZG", "Kanton Zug", "https://www.zg.ch/behoerden/sicherheitsdirektion/strassenverkehrsamt"},
	{"CH-FR", "Kanton Freiburg", "https://www.fr.ch/sva"},
	{"CH-SO", "Kanton Solothurn", "https://www.so.ch/verwaltung/bau-und-justizdepartement/strassenverkehrsamt/"},
	{"CH-BS", "Kanton Basel-Stadt", "https://www.mfk.bs.ch/"},
	{"CH-BL", "Kanton Basel-Landschaft", "https://www.baselland.ch/politik-und-behorden/direktionen/sicherheitsdirektion/motorfahrzeugkontrolle"},
	{"CH-SH", "Kanton Schaffhausen", "https://www.sh.ch/CMS/get/article/0/6/all/strassenverkehr/"},
	{"CH-AR", "Kanton Appenzell Ausserrhoden", "https://www.ar.ch/verwaltung/departement-inneres-und-sicherheit/strassenverkehrsamt/"},
	{"CH-AI", "Kanton Appenzell Innerrhoden", "https://www.ai.ch/themen/strassenverkehr"},
	{"CH-SG", "Kanton St. Gallen", "https://www.sg.ch/sicherheit-justiz/strassenverkehr.html"},
	{"CH-GR", "Kanton Graubuenden", "https://www.gr.ch/DE/institutionen/verwaltung/djsg/stra/Seiten/start.aspx"},
	{"CH-AG", "Kanton Aargau", "https://www.ag.ch/de/verwaltung/mvd/motorfahrzeugpruefstation/"},
	{"CH-TG", "Kanton Thurgau", "https://www.strassenverkehr.tg.ch/"},
	{"CH-TI", "Kanton Tessin", "https://www.ti.ch/dt/sdv/"},
	{"CH-VD", "Kanton Waadt", "https://www.vd.ch/themes/mobilite/voitures-et-deux-roues/controle-technique/"},
	{"CH-VS", "Kanton Wallis", "https://www.vs.ch/web/sca"},
	{"CH-NE", "Kanton Neuenburg", "https://www.ne.ch/autorite/DDTE/SCAN/Pages/accueil.aspx"},
	{"CH-GE", "Kanton Genf", "https://www.ge.ch/organisme/service-des-automobiles-navigation"},
	{"CH-JU", "Kanton Jura", "https://www.jura.ch/OFT/Service-des-automobiles-et-de-la-navigation.html"},
}

// svaIndex maps ISO code to slice index for O(1) lookup.
var svaIndex map[string]int

func init() {
	svaIndex = make(map[string]int, len(swissSVAs))
	for i, s := range swissSVAs {
		svaIndex[s.ISOCode] = i
	}
}

// Count returns the number of cantonal SVA entries in the static registry.
func Count() int { return len(swissSVAs) }

// ForCantonCode returns the CantonalSVA for the given ISO 3166-2:CH code.
func ForCantonCode(isoCode string) (CantonalSVA, bool) {
	if i, ok := svaIndex[isoCode]; ok {
		return swissSVAs[i], true
	}
	return CantonalSVA{}, false
}

// MFKCH executes the I.CH.1 sub-technique.
type MFKCH struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs a MFKCH executor.
func New(graph kg.KnowledgeGraph) *MFKCH {
	return &MFKCH{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (m *MFKCH) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (m *MFKCH) Name() string { return subTechName }

// Run upserts all 26 Swiss cantonal SVA offices into the knowledge graph.
func (m *MFKCH) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: countryCH}

	for _, sva := range swissSVAs {
		if ctx.Err() != nil {
			break
		}
		upserted, err := m.upsert(ctx, sva)
		if err != nil {
			m.log.Warn("mfk_ch: upsert error", "canton", sva.ISOCode, "err", err)
			result.Errors++
			continue
		}
		if upserted {
			result.Discovered++
			metrics.DealersTotal.WithLabelValues(familyID, countryCH).Inc()
		} else {
			result.Confirmed++
		}
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, countryCH).Observe(result.Duration.Seconds())
	m.log.Info("mfk_ch: done", "discovered", result.Discovered, "errors", result.Errors)
	return result, nil
}

func (m *MFKCH) upsert(ctx context.Context, sva CantonalSVA) (bool, error) {
	now := time.Now().UTC()
	stationID := fmt.Sprintf("CH-%s", sva.ISOCode)

	existing, err := m.graph.FindDealerByIdentifier(ctx, kg.IdentifierMFKStationID, stationID)
	if err != nil {
		return false, fmt.Errorf("mfk_ch.upsert find: %w", err)
	}
	isNew := existing == ""
	dealerID := existing
	if isNew {
		dealerID = ulid.Make().String()
	}
	meta := metadataJSON
	if err := m.graph.UpsertDealer(ctx, &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     sva.Name,
		NormalizedName:    strings.ToLower(sva.Name),
		CountryCode:       countryCH,
		Status:            kg.StatusUnverified,
		ConfidenceScore:   kg.BaseWeights[familyID],
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
		MetadataJSON:      &meta,
	}); err != nil {
		return false, fmt.Errorf("mfk_ch.upsert dealer: %w", err)
	}
	if isNew {
		if err := m.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
			IdentifierID:    ulid.Make().String(),
			DealerID:        dealerID,
			IdentifierType:  kg.IdentifierMFKStationID,
			IdentifierValue: stationID,
		}); err != nil {
			return false, fmt.Errorf("mfk_ch.upsert identifier: %w", err)
		}
	}
	if err := m.graph.AddLocation(ctx, &kg.DealerLocation{
		LocationID:     ulid.Make().String(),
		DealerID:       dealerID,
		IsPrimary:      true,
		Region:         &sva.ISOCode,
		CountryCode:    countryCH,
		SourceFamilies: familyID,
	}); err != nil {
		m.log.Warn("mfk_ch: location error", "canton", sva.ISOCode, "err", err)
	}
	if sva.WebsiteURL != "" {
		domain := extractDomain(sva.WebsiteURL)
		if err := m.graph.UpsertWebPresence(ctx, &kg.DealerWebPresence{
			WebID:                ulid.Make().String(),
			DealerID:             dealerID,
			Domain:               domain,
			URLRoot:              sva.WebsiteURL,
			DiscoveredByFamilies: familyID,
		}); err != nil {
			m.log.Warn("mfk_ch: web presence error", "canton", sva.ISOCode, "err", err)
		}
	}
	if err := m.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
	}); err != nil {
		m.log.Warn("mfk_ch: discovery error", "canton", sva.ISOCode, "err", err)
	}
	return isNew, nil
}

func extractDomain(rawURL string) string {
	u, err := url.Parse(rawURL)
	if err != nil {
		return rawURL
	}
	return u.Host
}
