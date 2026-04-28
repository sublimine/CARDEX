// Package ct_be implements sub-technique I.BE.1 — Belgian Contrôle Technique /
// Technische Keuring (CT/TK) inspection stations.
//
// # Status: PARTIALLY IMPLEMENTED — HTTP fetcher ready; JSON API endpoints are BLOCKERs
//
// Belgium has two independent CT networks:
//   - Wallonia (FR): AUTOSÉCURITÉ — https://www.autosecurite.be/trouver-un-centre
//   - Flanders + Brussels: GOCA / Keuring+ — https://www.keuringplus.be/zoek-een-keuringsplaats
//
// Both are React/Angular SPAs backed by internal JSON APIs.
//
// # BLOCKER: JSON API endpoints unknown
//
//	AUTOSÉCURITÉ: inspect XHR on https://www.autosecurite.be/trouver-un-centre
//	  → set DefaultAutoSecuriteAPIURL
//	GOCA / Keuring+: inspect XHR on https://www.keuringplus.be/zoek-een-keuringsplaats
//	  → set DefaultGOCAAPIURL
//	Alternative: search data.gov.be for "centres de contrôle technique" open dataset.
//
// Rate limiting: 1 req / 3 s per network.
// ConfidenceContributed: 0.05 (BaseWeights["I"]).
package ct_be

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID    = "I"
	subTechID   = "I.BE.1"
	subTechName = "Contrôle Technique / Technische Keuring stations (BE)"
	countryBE   = "BE"

	// DefaultAutoSecuriteAPIURL is the AUTOSÉCURITÉ (Wallonia) station list API endpoint.
	// BLOCKER: set to real URL discovered via browser DevTools on autosecurite.be.
	DefaultAutoSecuriteAPIURL = "" // intentionally empty until confirmed

	// DefaultGOCAAPIURL is the GOCA / Keuring+ (Flanders+BRU) station list API endpoint.
	// BLOCKER: set to real URL discovered via browser DevTools on keuringplus.be.
	DefaultGOCAAPIURL = "" // intentionally empty until confirmed

	defaultInterval = 3 * time.Second
	cardexUA        = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"

	metadataJSONWal = `{"is_dealer_candidate":false,"entity_type":"inspection_station","operator_network":"CT_BE_WAL"}`
	metadataJSONVlg = `{"is_dealer_candidate":false,"entity_type":"inspection_station","operator_network":"CT_BE_VLG"}`
)

type ctStation struct {
	ID         string
	Name       string
	Street     string
	PostalCode string
	City       string
	Region     string
	Metadata   string
}

// CTBE executes the I.BE.1 sub-technique (dual CT network).
type CTBE struct {
	graph         kg.KnowledgeGraph
	client        *http.Client
	autoSecureURL string
	gocaURL       string
	reqInterval   time.Duration
	log           *slog.Logger
}

// New constructs a CTBE executor with production configuration.
func New(graph kg.KnowledgeGraph) *CTBE {
	return NewWithConfig(graph, DefaultAutoSecuriteAPIURL, DefaultGOCAAPIURL, defaultInterval)
}

// NewWithConfig constructs a CTBE executor with custom API URLs and interval
// (use interval=0 in tests).
func NewWithConfig(graph kg.KnowledgeGraph, autoSecureURL, gocaURL string, reqInterval time.Duration) *CTBE {
	return &CTBE{
		graph:         graph,
		client:        &http.Client{Timeout: 30 * time.Second},
		autoSecureURL: autoSecureURL,
		gocaURL:       gocaURL,
		reqInterval:   reqInterval,
		log:           slog.Default().With("sub_technique", subTechID),
	}
}

func (c *CTBE) ID() string   { return subTechID }
func (c *CTBE) Name() string { return subTechName }

// Run fetches stations from both Belgian CT networks. Any network whose URL is
// empty logs a BLOCKER warning and is skipped.
func (c *CTBE) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: countryBE}

	if c.autoSecureURL == "" {
		c.log.Warn("ct_be: AUTOSÉCURITÉ (Wallonia) BLOCKED — API URL not configured",
			"blocker", "inspect XHR on https://www.autosecurite.be/trouver-un-centre",
		)
	} else {
		c.runNetwork(ctx, c.autoSecureURL, "BE-WAL", metadataJSONWal, result)
	}

	if c.reqInterval > 0 && c.autoSecureURL != "" && c.gocaURL != "" {
		select {
		case <-ctx.Done():
			goto done
		case <-time.After(c.reqInterval):
		}
	}

	if c.gocaURL == "" {
		c.log.Warn("ct_be: GOCA/Keuring+ (Flanders+BRU) BLOCKED — API URL not configured",
			"blocker", "inspect XHR on https://www.keuringplus.be/zoek-een-keuringsplaats",
		)
	} else {
		c.runNetwork(ctx, c.gocaURL, "BE-VLG", metadataJSONVlg, result)
	}

done:
	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, countryBE).Observe(result.Duration.Seconds())
	c.log.Info("ct_be: done", "discovered", result.Discovered, "errors", result.Errors)
	return result, nil
}

func (c *CTBE) runNetwork(ctx context.Context, apiURL, region, meta string, result *runner.SubTechniqueResult) {
	stations, err := c.fetchStations(ctx, apiURL)
	if err != nil {
		c.log.Warn("ct_be: network fetch error", "region", region, "err", err)
		result.Errors++
		return
	}
	for _, st := range stations {
		st.Region = region
		st.Metadata = meta
		upserted, err := c.upsert(ctx, st)
		if err != nil {
			c.log.Warn("ct_be: upsert error", "id", st.ID, "err", err)
			result.Errors++
			continue
		}
		if upserted {
			result.Discovered++
			metrics.DealersTotal.WithLabelValues(familyID, countryBE).Inc()
		} else {
			result.Confirmed++
		}
	}
}

func (c *CTBE) fetchStations(ctx context.Context, apiURL string) ([]ctStation, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, apiURL, nil)
	if err != nil {
		return nil, fmt.Errorf("ct_be fetch: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "application/json")
	resp, err := c.client.Do(req)
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return nil, fmt.Errorf("ct_be fetch: http: %w", err)
	}
	defer resp.Body.Close()
	metrics.SubTechniqueRequests.WithLabelValues(subTechID, fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("ct_be fetch: HTTP %d", resp.StatusCode)
	}
	var raw []map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&raw); err != nil {
		return nil, fmt.Errorf("ct_be fetch: decode: %w", err)
	}
	stations := make([]ctStation, 0, len(raw))
	for _, obj := range raw {
		st := normaliseStation(obj)
		if st.ID != "" && st.Name != "" {
			stations = append(stations, st)
		}
	}
	return stations, nil
}

func normaliseStation(obj map[string]any) ctStation {
	str := func(keys ...string) string {
		for _, k := range keys {
			if v, ok := obj[k]; ok {
				if s, ok := v.(string); ok && s != "" {
					return strings.TrimSpace(s)
				}
			}
		}
		return ""
	}
	idStr := func(keys ...string) string {
		for _, k := range keys {
			if v, ok := obj[k]; ok {
				switch n := v.(type) {
				case string:
					if n != "" {
						return n
					}
				case float64:
					return fmt.Sprintf("%.0f", n)
				}
			}
		}
		return ""
	}
	return ctStation{
		ID:         idStr("id", "ID", "stationId", "station_id", "centreId", "centre_id"),
		Name:       str("name", "naam", "nom", "Name", "Naam", "Nom", "denominatie", "denomination"),
		Street:     str("street", "straat", "rue", "address", "adresse", "adres"),
		PostalCode: str("postalCode", "postcode", "codePostal", "postal_code", "zip"),
		City:       str("city", "stad", "ville", "gemeente", "commune", "localite"),
	}
}

func (c *CTBE) upsert(ctx context.Context, st ctStation) (bool, error) {
	now := time.Now().UTC()
	existing, err := c.graph.FindDealerByIdentifier(ctx, kg.IdentifierCTStationID, st.ID)
	if err != nil {
		return false, fmt.Errorf("ct_be.upsert find: %w", err)
	}
	isNew := existing == ""
	dealerID := existing
	if isNew {
		dealerID = ulid.Make().String()
	}
	if err := c.graph.UpsertDealer(ctx, &kg.DealerEntity{
		DealerID: dealerID, CanonicalName: st.Name, NormalizedName: strings.ToLower(st.Name),
		CountryCode: countryBE, Status: kg.StatusUnverified,
		ConfidenceScore: kg.BaseWeights[familyID], FirstDiscoveredAt: now, LastConfirmedAt: now,
		MetadataJSON: &st.Metadata,
	}); err != nil {
		return false, fmt.Errorf("ct_be.upsert dealer: %w", err)
	}
	if isNew {
		if err := c.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
			IdentifierID: ulid.Make().String(), DealerID: dealerID,
			IdentifierType: kg.IdentifierCTStationID, IdentifierValue: st.ID,
		}); err != nil {
			return false, fmt.Errorf("ct_be.upsert identifier: %w", err)
		}
	}
	if st.Street != "" || st.PostalCode != "" || st.City != "" {
		region := st.Region
		if err := c.graph.AddLocation(ctx, &kg.DealerLocation{
			LocationID: ulid.Make().String(), DealerID: dealerID, IsPrimary: true,
			AddressLine1: ptrIfNotEmpty(st.Street), PostalCode: ptrIfNotEmpty(st.PostalCode),
			City: ptrIfNotEmpty(st.City), Region: &region,
			CountryCode: countryBE, SourceFamilies: familyID,
		}); err != nil {
			c.log.Warn("ct_be: location error", "station", st.Name, "err", err)
		}
	}
	if err := c.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID: ulid.Make().String(), DealerID: dealerID,
		Family: familyID, SubTechnique: subTechID,
		ConfidenceContributed: kg.BaseWeights[familyID], DiscoveredAt: now,
	}); err != nil {
		c.log.Warn("ct_be: discovery error", "station", st.Name, "err", err)
	}
	return isNew, nil
}

func ptrIfNotEmpty(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}
