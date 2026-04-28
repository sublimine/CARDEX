// Package rdw_apk implements sub-technique I.NL.1 — RDW APK inspection stations (NL).
//
// The Dutch Vehicle Authority (RDW) publishes the list of all APK-recognised
// (Algemene Periodieke Keuring) inspection stations as Open Data via the
// Socrata Open Data API (SODA):
//
//	https://opendata.rdw.nl/resource/sgfe-77wx.json
//
// Pagination: SODA supports $limit / $offset; we page in batches of 1 000
// until the response is empty.
//
// robots.txt: opendata.rdw.nl serves data under an open government licence
// and does not restrict automated access. SODA endpoints are designed for
// programmatic consumption.
//
// Inspection stations are NOT dealer candidates — they are adjacent signals
// indicating that an operator holds a valid APK authorisation. The KG entity
// is stored with MetadataJSON = {"is_dealer_candidate":false,"entity_type":"inspection_station"}.
//
// Rate limiting: 1 req / 3 s.
// ConfidenceContributed: 0.05 (BaseWeights["I"]).
package rdw_apk

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
	subTechID   = "I.NL.1"
	subTechName = "RDW APK inspection stations (NL)"
	countryNL   = "NL"

	defaultBaseURL     = "https://opendata.rdw.nl"
	defaultDatasetPath = "/resource/sgfe-77wx.json"
	pageSize           = 1000
	defaultReqInterval = 3 * time.Second
	cardexUA           = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"

	// metadataJSON is stored on every inspection station entity.
	metadataJSON = `{"is_dealer_candidate":false,"entity_type":"inspection_station"}`
)

// apkStation mirrors the relevant fields from the RDW SODA dataset sgfe-77wx.
// Field names are snake_case as returned by the Socrata API.
type apkStation struct {
	// Identification
	Erkenningsnummer string `json:"erkenningsnummer_keuringsinstantie"` // APK recognition number
	Volgnummer       string `json:"volgnummer"`                         // sequence number (fallback ID)

	// Name
	Handelsnaam string `json:"handelsnaam"` // trade name

	// Address
	Straat      string `json:"straat"`      // street name
	Huisnummer  string `json:"huisnummer"`  // house number
	Postcode    string `json:"postcode"`    // postal code
	Plaatsnaam  string `json:"plaatsnaam"`  // city
	Gemeente    string `json:"gemeente"`    // municipality (fallback for city)
}

// canonicalID returns the primary identifier: recognition number if set, else Volgnummer.
func (s apkStation) canonicalID() string {
	if s.Erkenningsnummer != "" {
		return s.Erkenningsnummer
	}
	return s.Volgnummer
}

// canonicalName returns the trade name.
func (s apkStation) canonicalName() string { return s.Handelsnaam }

// city returns the best available city field.
func (s apkStation) city() string {
	if s.Plaatsnaam != "" {
		return s.Plaatsnaam
	}
	return s.Gemeente
}

// streetFull concatenates street + house number.
func (s apkStation) streetFull() string {
	if s.Huisnummer != "" {
		return strings.TrimSpace(s.Straat + " " + s.Huisnummer)
	}
	return s.Straat
}

// RDWAPK executes the I.NL.1 sub-technique using the RDW Open Data API.
type RDWAPK struct {
	graph       kg.KnowledgeGraph
	client      *http.Client
	baseURL     string
	reqInterval time.Duration
	log         *slog.Logger
}

// New returns a RDWAPK executor with the production endpoint.
func New(graph kg.KnowledgeGraph) *RDWAPK {
	return NewWithBaseURL(graph, defaultBaseURL, defaultReqInterval)
}

// NewWithBaseURL returns a RDWAPK executor with a custom base URL and interval
// (use interval=0 in tests).
func NewWithBaseURL(graph kg.KnowledgeGraph, baseURL string, reqInterval time.Duration) *RDWAPK {
	return &RDWAPK{
		graph:       graph,
		client:      &http.Client{Timeout: 30 * time.Second},
		baseURL:     baseURL,
		reqInterval: reqInterval,
		log:         slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (r *RDWAPK) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (r *RDWAPK) Name() string { return subTechName }

// Run fetches all RDW APK station pages from the SODA API and upserts each
// station into the KG.
func (r *RDWAPK) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: countryNL}

	seen := make(map[string]bool)

	for offset := 0; ; offset += pageSize {
		if ctx.Err() != nil {
			break
		}

		if r.reqInterval > 0 && offset > 0 {
			select {
			case <-ctx.Done():
				goto done
			case <-time.After(r.reqInterval):
			}
		}

		stations, err := r.fetchPage(ctx, offset)
		if err != nil {
			r.log.Warn("rdw_apk: page fetch error", "offset", offset, "err", err)
			result.Errors++
			break
		}
		if len(stations) == 0 {
			break // end of data
		}

		r.log.Debug("rdw_apk: page fetched", "offset", offset, "count", len(stations))

		for _, st := range stations {
			cid := st.canonicalID()
			if cid == "" || st.canonicalName() == "" {
				continue
			}
			if seen[cid] {
				continue
			}
			seen[cid] = true

			upserted, err := r.upsert(ctx, st)
			if err != nil {
				r.log.Warn("rdw_apk: upsert error", "id", cid, "err", err)
				result.Errors++
				continue
			}
			if upserted {
				result.Discovered++
				metrics.DealersTotal.WithLabelValues(familyID, countryNL).Inc()
			} else {
				result.Confirmed++
			}
		}

		if len(stations) < pageSize {
			break // last page
		}
	}

done:
	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, countryNL).Observe(result.Duration.Seconds())
	r.log.Info("rdw_apk: done",
		"discovered", result.Discovered,
		"confirmed", result.Confirmed,
		"errors", result.Errors,
	)
	return result, nil
}

// HealthCheck verifies that the RDW Open Data endpoint is reachable.
func (r *RDWAPK) HealthCheck(ctx context.Context) error {
	reqURL := r.baseURL + defaultDatasetPath + "?$limit=1"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", cardexUA)
	resp, err := r.client.Do(req)
	if err != nil {
		return fmt.Errorf("rdw_apk health: %w", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("rdw_apk health: HTTP %d", resp.StatusCode)
	}
	return nil
}

// ── SODA fetch ────────────────────────────────────────────────────────────────

// fetchPage fetches a single SODA page at the given offset.
func (r *RDWAPK) fetchPage(ctx context.Context, offset int) ([]apkStation, error) {
	reqURL := fmt.Sprintf("%s%s?$limit=%d&$offset=%d",
		r.baseURL, defaultDatasetPath, pageSize, offset)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return nil, fmt.Errorf("rdw_apk page: build req: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "application/json")

	resp, err := r.client.Do(req)
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return nil, fmt.Errorf("rdw_apk page: http: %w", err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("rdw_apk page: HTTP %d", resp.StatusCode)
	}

	var stations []apkStation
	if err := json.NewDecoder(resp.Body).Decode(&stations); err != nil {
		return nil, fmt.Errorf("rdw_apk page: decode JSON: %w", err)
	}
	return stations, nil
}

// ── KG upsert ─────────────────────────────────────────────────────────────────

func (r *RDWAPK) upsert(ctx context.Context, st apkStation) (bool, error) {
	now := time.Now().UTC()
	idValue := st.canonicalID()
	name := st.canonicalName()

	existing, err := r.graph.FindDealerByIdentifier(ctx, kg.IdentifierAPKStationID, idValue)
	if err != nil {
		return false, fmt.Errorf("rdw_apk.upsert find: %w", err)
	}

	isNew := existing == ""
	dealerID := existing
	if isNew {
		dealerID = ulid.Make().String()
	}

	meta := metadataJSON
	if err := r.graph.UpsertDealer(ctx, &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     name,
		NormalizedName:    strings.ToLower(name),
		CountryCode:       countryNL,
		Status:            kg.StatusUnverified,
		ConfidenceScore:   kg.BaseWeights[familyID],
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
		MetadataJSON:      &meta,
	}); err != nil {
		return false, fmt.Errorf("rdw_apk.upsert dealer: %w", err)
	}

	if isNew {
		if err := r.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
			IdentifierID:    ulid.Make().String(),
			DealerID:        dealerID,
			IdentifierType:  kg.IdentifierAPKStationID,
			IdentifierValue: idValue,
		}); err != nil {
			return false, fmt.Errorf("rdw_apk.upsert identifier: %w", err)
		}
	}

	street := st.streetFull()
	if street != "" || st.Postcode != "" || st.city() != "" {
		if err := r.graph.AddLocation(ctx, &kg.DealerLocation{
			LocationID:     ulid.Make().String(),
			DealerID:       dealerID,
			IsPrimary:      true,
			AddressLine1:   ptrIfNotEmpty(street),
			PostalCode:     ptrIfNotEmpty(st.Postcode),
			City:           ptrIfNotEmpty(st.city()),
			CountryCode:    countryNL,
			SourceFamilies: familyID,
		}); err != nil {
			r.log.Warn("rdw_apk: add location error", "station", name, "err", err)
		}
	}

	if err := r.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
	}); err != nil {
		r.log.Warn("rdw_apk: record discovery error", "station", name, "err", err)
	}

	return isNew, nil
}

// ── Helpers ───────────────────────────────────────────────────────────────────

func ptrIfNotEmpty(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}
