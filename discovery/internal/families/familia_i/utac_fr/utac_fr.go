// Package utac_fr implements sub-technique I.FR.2 — French Contrôle Technique
// inspection centres via the data.economie.gouv.fr Opendatasoft open-data portal.
//
// # Data source
//
// The French Ministère de l'Économie publishes the complete list of approved
// Contrôle Technique centres (all operators: DEKRA Autocite, Sécuritest, Autosur,
// Norisko, Bureau Veritas, etc.) under the Opendatasoft v2.1 API at:
//
//	https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/controles_techniques/records
//
// robots.txt: data.economie.gouv.fr serves public government open data and permits
// automated programmatic access. The dataset is published under Licence Ouverte 2.0
// (ETALAB) and is designed for machine consumption.
//
// # BLOCKER_VERIFY
//
//	Dataset identifier "controles_techniques" confirmed from:
//	https://data.economie.gouv.fr/explore/dataset/controles_techniques/
//	Verify at https://data.economie.gouv.fr/explore before provisioning.
//	If the dataset has moved, search for "controle technique agréé" on that portal.
//	Alternative source: https://www.data.gouv.fr/fr/datasets/liste-des-organismes-agrees-de-controle-technique/
//
// # Records structure (Opendatasoft v2.1)
//
//	{
//	  "total_count": 6500,
//	  "results": [
//	    {
//	      "no_agrement": "03G0001",
//	      "nom_centre": "SECURITEST AUTO CONTROLE",
//	      "adresse": "6 RUE DE LA CHARME",
//	      "code_postal": "03200",
//	      "commune": "VICHY",
//	      "departement": "03 - Allier",
//	      "region_administrative": "Auvergne-Rhône-Alpes"
//	    }
//	  ]
//	}
//
// Pagination: offset-based with ?limit=100&offset=N until results array is empty.
//
// Rate limiting: 1 req / 3 s.
// ConfidenceContributed: 0.05 (BaseWeights["I"]).
package utac_fr

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
	subTechID   = "I.FR.2"
	subTechName = "Contrôle Technique centres (FR) — UTAC/data.economie.gouv.fr"
	countryFR   = "FR"

	defaultBaseURL  = "https://data.economie.gouv.fr"
	datasetPath     = "/api/explore/v2.1/catalog/datasets/controles_techniques/records"
	pageSize        = 100
	defaultInterval = 3 * time.Second
	cardexUA        = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"

	metadataJSON = `{"is_dealer_candidate":false,"entity_type":"inspection_station","operator_network":"CT_FR"}`
)

// ctRecord mirrors the relevant fields from the data.economie.gouv.fr dataset.
type ctRecord struct {
	NoAgrement          string `json:"no_agrement"`           // unique approval number, e.g. "03G0001"
	NomCentre           string `json:"nom_centre"`            // centre name
	Adresse             string `json:"adresse"`               // street address
	CodePostal          string `json:"code_postal"`           // postal code
	Commune             string `json:"commune"`               // city / commune
	Departement         string `json:"departement"`           // department, e.g. "03 - Allier"
	RegionAdministrative string `json:"region_administrative"` // region, e.g. "Auvergne-Rhône-Alpes"
	Telephone           string `json:"telephone"`
}

// apiResponse is the Opendatasoft v2.1 response envelope.
type apiResponse struct {
	TotalCount int        `json:"total_count"`
	Results    []ctRecord `json:"results"`
}

// UTACFR executes the I.FR.2 sub-technique using data.economie.gouv.fr.
type UTACFR struct {
	graph       kg.KnowledgeGraph
	client      *http.Client
	baseURL     string
	reqInterval time.Duration
	log         *slog.Logger
}

// New constructs a UTACFR executor with the production endpoint.
func New(graph kg.KnowledgeGraph) *UTACFR {
	return NewWithBaseURL(graph, defaultBaseURL, defaultInterval)
}

// NewWithBaseURL constructs a UTACFR executor with a custom base URL and
// request interval (use interval=0 in tests).
func NewWithBaseURL(graph kg.KnowledgeGraph, baseURL string, reqInterval time.Duration) *UTACFR {
	return &UTACFR{
		graph:       graph,
		client:      &http.Client{Timeout: 30 * time.Second},
		baseURL:     baseURL,
		reqInterval: reqInterval,
		log:         slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (u *UTACFR) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (u *UTACFR) Name() string { return subTechName }

// Run fetches all approved CT centres from data.economie.gouv.fr and upserts
// each centre into the KG as an adjacent-signal inspection station entity.
func (u *UTACFR) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: countryFR}

	seen := make(map[string]bool)

	for offset := 0; ; offset += pageSize {
		if ctx.Err() != nil {
			break
		}
		if u.reqInterval > 0 && offset > 0 {
			select {
			case <-ctx.Done():
				goto done
			case <-time.After(u.reqInterval):
			}
		}

		records, err := u.fetchPage(ctx, offset)
		if err != nil {
			u.log.Warn("utac_fr: page fetch error", "offset", offset, "err", err)
			result.Errors++
			break
		}
		if len(records) == 0 {
			break
		}

		u.log.Debug("utac_fr: page fetched", "offset", offset, "count", len(records))

		for _, rec := range records {
			id := rec.NoAgrement
			name := strings.TrimSpace(rec.NomCentre)
			if id == "" || name == "" {
				continue
			}
			if seen[id] {
				continue
			}
			seen[id] = true

			upserted, err := u.upsert(ctx, rec)
			if err != nil {
				u.log.Warn("utac_fr: upsert error", "id", id, "err", err)
				result.Errors++
				continue
			}
			if upserted {
				result.Discovered++
				metrics.DealersTotal.WithLabelValues(familyID, countryFR).Inc()
			} else {
				result.Confirmed++
			}
		}

		if len(records) < pageSize {
			break // last page
		}
	}

done:
	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, countryFR).Observe(result.Duration.Seconds())
	u.log.Info("utac_fr: done",
		"discovered", result.Discovered,
		"confirmed", result.Confirmed,
		"errors", result.Errors,
	)
	return result, nil
}

// HealthCheck verifies that the data.economie.gouv.fr endpoint is reachable.
func (u *UTACFR) HealthCheck(ctx context.Context) error {
	reqURL := u.baseURL + datasetPath + "?limit=1"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", cardexUA)
	resp, err := u.client.Do(req)
	if err != nil {
		return fmt.Errorf("utac_fr health: %w", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("utac_fr health: HTTP %d", resp.StatusCode)
	}
	return nil
}

// ── Fetch ─────────────────────────────────────────────────────────────────────

func (u *UTACFR) fetchPage(ctx context.Context, offset int) ([]ctRecord, error) {
	reqURL := fmt.Sprintf("%s%s?limit=%d&offset=%d&timezone=UTC",
		u.baseURL, datasetPath, pageSize, offset)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return nil, fmt.Errorf("utac_fr fetchPage: build req: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "application/json")

	resp, err := u.client.Do(req)
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return nil, fmt.Errorf("utac_fr fetchPage: http: %w", err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("utac_fr fetchPage: HTTP %d", resp.StatusCode)
	}

	var apiResp apiResponse
	if err := json.NewDecoder(resp.Body).Decode(&apiResp); err != nil {
		return nil, fmt.Errorf("utac_fr fetchPage: decode: %w", err)
	}
	return apiResp.Results, nil
}

// ── KG upsert ─────────────────────────────────────────────────────────────────

func (u *UTACFR) upsert(ctx context.Context, rec ctRecord) (bool, error) {
	now := time.Now().UTC()
	idValue := rec.NoAgrement
	name := strings.TrimSpace(rec.NomCentre)

	existing, err := u.graph.FindDealerByIdentifier(ctx, kg.IdentifierCTStationID, idValue)
	if err != nil {
		return false, fmt.Errorf("utac_fr.upsert find: %w", err)
	}

	isNew := existing == ""
	dealerID := existing
	if isNew {
		dealerID = ulid.Make().String()
	}

	meta := metadataJSON
	if err := u.graph.UpsertDealer(ctx, &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     name,
		NormalizedName:    strings.ToLower(name),
		CountryCode:       countryFR,
		Status:            kg.StatusUnverified,
		ConfidenceScore:   kg.BaseWeights[familyID],
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
		MetadataJSON:      &meta,
	}); err != nil {
		return false, fmt.Errorf("utac_fr.upsert dealer: %w", err)
	}

	if isNew {
		if err := u.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
			IdentifierID:    ulid.Make().String(),
			DealerID:        dealerID,
			IdentifierType:  kg.IdentifierCTStationID,
			IdentifierValue: idValue,
		}); err != nil {
			return false, fmt.Errorf("utac_fr.upsert identifier: %w", err)
		}
	}

	if rec.Adresse != "" || rec.CodePostal != "" || rec.Commune != "" {
		city := strings.TrimSpace(rec.Commune)
		region := strings.TrimSpace(rec.RegionAdministrative)
		// Derive department ISO code from "NN - Name" prefix.
		deptCode := deptISOCode(rec.Departement)
		if err := u.graph.AddLocation(ctx, &kg.DealerLocation{
			LocationID:     ulid.Make().String(),
			DealerID:       dealerID,
			IsPrimary:      true,
			AddressLine1:   ptrIfNotEmpty(strings.TrimSpace(rec.Adresse)),
			PostalCode:     ptrIfNotEmpty(rec.CodePostal),
			City:           ptrIfNotEmpty(city),
			Region:         ptrIfNotEmpty(regionOrDept(region, deptCode)),
			CountryCode:    countryFR,
			SourceFamilies: familyID,
		}); err != nil {
			u.log.Warn("utac_fr: add location error", "centre", name, "err", err)
		}
	}

	if err := u.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
	}); err != nil {
		u.log.Warn("utac_fr: record discovery error", "centre", name, "err", err)
	}

	return isNew, nil
}

// ── Helpers ───────────────────────────────────────────────────────────────────

// deptISOCode extracts the 2-digit department number from a "NN - Name" string
// and converts it to an ISO 3166-2:FR-like sub-region tag (e.g., "FR-03").
func deptISOCode(dept string) string {
	if len(dept) < 2 {
		return ""
	}
	idx := strings.Index(dept, " -")
	if idx <= 0 {
		return ""
	}
	code := strings.TrimSpace(dept[:idx])
	if code == "" {
		return ""
	}
	return "FR-" + code
}

// regionOrDept returns the region ISO tag if available, else the department tag.
func regionOrDept(region, dept string) string {
	if region != "" {
		return region
	}
	return dept
}

func ptrIfNotEmpty(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}
