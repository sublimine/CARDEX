// Package itv_es implements sub-technique I.ES.1 — ITV inspection stations (ES).
//
// # Status: PARTIALLY IMPLEMENTED — ArcGIS fetcher ready; service URL is a BLOCKER
//
// ITV (Inspección Técnica de Vehículos) is Spain's mandatory vehicle inspection
// scheme. The DGT (Dirección General de Tráfico) station locator is at:
//
//	https://sede.dgt.gob.es/es/tu-coche-y-el-carnet/itv/localizador-itv/
//
// # BLOCKER: ArcGIS service URL unknown
//
//	Inspect XHR requests on the DGT ITV locator page. Filter by "arcgis" or
//	"FeatureServer". Set DefaultArcGISServiceURL to the base URL once confirmed.
//	Known pattern: https://services.arcgis.com/{orgId}/arcgis/rest/services/{name}/FeatureServer/0
//
// Rate limiting: 1 req / 3 s.
// ConfidenceContributed: 0.05 (BaseWeights["I"]).
package itv_es

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
	subTechID   = "I.ES.1"
	subTechName = "ITV inspection stations (ES) — DGT ArcGIS FeatureServer"
	countryES   = "ES"

	// DefaultArcGISServiceURL is the DGT ITV ArcGIS FeatureServer base URL.
	// BLOCKER: set to real URL discovered via browser DevTools on the DGT ITV locator.
	DefaultArcGISServiceURL = "" // intentionally empty until URL is confirmed

	pageSize        = 1000
	defaultInterval = 3 * time.Second
	cardexUA        = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"

	metadataJSON = `{"is_dealer_candidate":false,"entity_type":"inspection_station","operator_network":"ITV_ES"}`
)

type arcGISFeature struct {
	Attributes map[string]any `json:"attributes"`
}

type arcGISResponse struct {
	Features              []arcGISFeature `json:"features"`
	ExceededTransferLimit bool            `json:"exceededTransferLimit"`
}

func stationFromAttrs(attrs map[string]any) (id, name, street, postalCode, city string) {
	strField := func(keys ...string) string {
		for _, k := range keys {
			if v, ok := attrs[k]; ok {
				if s, ok := v.(string); ok && s != "" && s != "null" {
					return strings.TrimSpace(s)
				}
			}
		}
		return ""
	}
	intField := func(key string) string {
		if v, ok := attrs[key]; ok {
			if n, ok := v.(float64); ok {
				return fmt.Sprintf("%.0f", n)
			}
		}
		return ""
	}
	id = strField("OBJECTID", "FID", "ID_ITV", "objectid")
	if id == "" {
		id = intField("OBJECTID")
	}
	name = strField("NOMBRE", "NOMBRE_ITV", "DENOMINACION", "name", "Name")
	street = strField("DIRECCION", "DOMICILIO", "CALLE", "address")
	postalCode = strField("CP", "COD_POSTAL", "CODIGO_POSTAL", "postal_code")
	city = strField("MUNICIPIO", "POBLACION", "LOCALIDAD", "city")
	return
}

// ITVES executes the I.ES.1 sub-technique.
type ITVES struct {
	graph         kg.KnowledgeGraph
	client        *http.Client
	arcGISBaseURL string
	reqInterval   time.Duration
	log           *slog.Logger
}

// New constructs an ITVES executor. If DefaultArcGISServiceURL is empty, Run
// logs the BLOCKER and returns an empty result without error.
func New(graph kg.KnowledgeGraph) *ITVES {
	return NewWithConfig(graph, DefaultArcGISServiceURL, defaultInterval)
}

// NewWithConfig constructs an ITVES executor with a custom ArcGIS URL and
// request interval (pass interval=0 in tests).
func NewWithConfig(graph kg.KnowledgeGraph, arcGISURL string, reqInterval time.Duration) *ITVES {
	return &ITVES{
		graph:         graph,
		client:        &http.Client{Timeout: 30 * time.Second},
		arcGISBaseURL: arcGISURL,
		reqInterval:   reqInterval,
		log:           slog.Default().With("sub_technique", subTechID),
	}
}

func (i *ITVES) ID() string   { return subTechID }
func (i *ITVES) Name() string { return subTechName }

// Run fetches all ITV stations from the DGT ArcGIS FeatureServer.
// Returns empty result (no error) when URL is not configured.
func (i *ITVES) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: countryES}

	if i.arcGISBaseURL == "" {
		i.log.Warn("itv_es: I.ES.1 BLOCKED — ArcGIS service URL not configured",
			"blocker", "inspect XHR on sede.dgt.gob.es ITV locator, set DefaultArcGISServiceURL",
		)
		result.Duration = time.Since(start)
		return result, nil
	}

	seen := make(map[string]bool)
	for offset := 0; ; offset += pageSize {
		if ctx.Err() != nil {
			break
		}
		if i.reqInterval > 0 && offset > 0 {
			select {
			case <-ctx.Done():
				goto done
			case <-time.After(i.reqInterval):
			}
		}
		arcResp, err := i.fetchPage(ctx, offset)
		if err != nil {
			i.log.Warn("itv_es: page fetch error", "offset", offset, "err", err)
			result.Errors++
			break
		}
		if len(arcResp.Features) == 0 {
			break
		}
		for _, feat := range arcResp.Features {
			objID, name, street, postalCode, city := stationFromAttrs(feat.Attributes)
			if objID == "" || name == "" {
				continue
			}
			if seen[objID] {
				continue
			}
			seen[objID] = true
			upserted, err := i.upsert(ctx, objID, name, street, postalCode, city)
			if err != nil {
				i.log.Warn("itv_es: upsert error", "id", objID, "err", err)
				result.Errors++
				continue
			}
			if upserted {
				result.Discovered++
				metrics.DealersTotal.WithLabelValues(familyID, countryES).Inc()
			} else {
				result.Confirmed++
			}
		}
		if !arcResp.ExceededTransferLimit {
			break
		}
	}
done:
	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, countryES).Observe(result.Duration.Seconds())
	i.log.Info("itv_es: done", "discovered", result.Discovered, "errors", result.Errors)
	return result, nil
}

func (i *ITVES) fetchPage(ctx context.Context, offset int) (*arcGISResponse, error) {
	reqURL := fmt.Sprintf("%s/query?where=1%%3D1&outFields=*&resultOffset=%d&resultRecordCount=%d&f=json",
		i.arcGISBaseURL, offset, pageSize)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return nil, fmt.Errorf("itv_es fetchPage: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "application/json")
	resp, err := i.client.Do(req)
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return nil, fmt.Errorf("itv_es fetchPage: http: %w", err)
	}
	defer resp.Body.Close()
	metrics.SubTechniqueRequests.WithLabelValues(subTechID, fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("itv_es fetchPage: HTTP %d", resp.StatusCode)
	}
	var r arcGISResponse
	if err := json.NewDecoder(resp.Body).Decode(&r); err != nil {
		return nil, fmt.Errorf("itv_es fetchPage: decode: %w", err)
	}
	return &r, nil
}

func (i *ITVES) upsert(ctx context.Context, objID, name, street, postalCode, city string) (bool, error) {
	now := time.Now().UTC()
	existing, err := i.graph.FindDealerByIdentifier(ctx, kg.IdentifierITVStationID, objID)
	if err != nil {
		return false, fmt.Errorf("itv_es.upsert find: %w", err)
	}
	isNew := existing == ""
	dealerID := existing
	if isNew {
		dealerID = ulid.Make().String()
	}
	meta := metadataJSON
	if err := i.graph.UpsertDealer(ctx, &kg.DealerEntity{
		DealerID: dealerID, CanonicalName: name, NormalizedName: strings.ToLower(name),
		CountryCode: countryES, Status: kg.StatusUnverified,
		ConfidenceScore: kg.BaseWeights[familyID], FirstDiscoveredAt: now, LastConfirmedAt: now,
		MetadataJSON: &meta,
	}); err != nil {
		return false, fmt.Errorf("itv_es.upsert dealer: %w", err)
	}
	if isNew {
		if err := i.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
			IdentifierID: ulid.Make().String(), DealerID: dealerID,
			IdentifierType: kg.IdentifierITVStationID, IdentifierValue: objID,
		}); err != nil {
			return false, fmt.Errorf("itv_es.upsert identifier: %w", err)
		}
	}
	if street != "" || postalCode != "" || city != "" {
		if err := i.graph.AddLocation(ctx, &kg.DealerLocation{
			LocationID: ulid.Make().String(), DealerID: dealerID, IsPrimary: true,
			AddressLine1: ptrIfNotEmpty(street), PostalCode: ptrIfNotEmpty(postalCode),
			City: ptrIfNotEmpty(city), CountryCode: countryES, SourceFamilies: familyID,
		}); err != nil {
			i.log.Warn("itv_es: location error", "station", name, "err", err)
		}
	}
	if err := i.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID: ulid.Make().String(), DealerID: dealerID,
		Family: familyID, SubTechnique: subTechID,
		ConfidenceContributed: kg.BaseWeights[familyID], DiscoveredAt: now,
	}); err != nil {
		i.log.Warn("itv_es: discovery error", "station", name, "err", err)
	}
	return isNew, nil
}

func ptrIfNotEmpty(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}
