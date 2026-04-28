// Package wikidata implements sub-technique B.2 — Wikidata SPARQL query for
// automotive businesses in the 6 target countries.
//
// Strategy: For each country, issue a single SPARQL SELECT against
// https://query.wikidata.org/sparql using the Wikidata Query Service.
// The query finds entities that are instances of a business enterprise
// (Q4830453) in the automotive industry (Q452 = Q190960), scoped to the
// target country via P17.
//
// Optional properties retrieved per entity:
//   - P625: geographic coordinates (WKT Point format: "Point(lon lat)")
//   - P856: official website URL
//   - P3608: EU VAT identification number
//
// Rate limiting: Wikidata SPARQL endpoint requests 1 query per 2 seconds
// between countries to comply with the Wikimedia API etiquette guidelines.
package wikidata

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	defaultSPARQLURL = "https://query.wikidata.org/sparql"
	sparqlTimeout    = 60 * time.Second
	cardexUA         = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
	familyID         = "B"
	subTechID        = "B.2"
	subTechName      = "Wikidata SPARQL — automotive businesses 6 países"
)

// countryQCodes maps ISO 3166-1 alpha-2 codes to Wikidata Q-identifiers.
// These are the Wikidata entities for each of the 6 target countries.
var countryQCodes = map[string]string{
	"DE": "Q183", // Germany
	"FR": "Q142", // France
	"ES": "Q29",  // Spain
	"BE": "Q31",  // Belgium
	"NL": "Q55",  // Netherlands
	"CH": "Q39",  // Switzerland
}

// allCountries is the ordered set of target countries for full-run iteration.
var allCountries = []string{"DE", "FR", "ES", "BE", "NL", "CH"}

// Wikidata executes B.2 SPARQL queries against the Wikidata Query Service.
type Wikidata struct {
	graph   kg.KnowledgeGraph
	client  *http.Client
	baseURL string
	log     *slog.Logger
}

// New creates a Wikidata executor with the production SPARQL endpoint.
func New(graph kg.KnowledgeGraph) *Wikidata {
	return NewWithBaseURL(graph, defaultSPARQLURL)
}

// NewWithBaseURL creates a Wikidata executor with a custom endpoint (for tests).
func NewWithBaseURL(graph kg.KnowledgeGraph, baseURL string) *Wikidata {
	return &Wikidata{
		graph:   graph,
		client:  &http.Client{Timeout: sparqlTimeout},
		baseURL: baseURL,
		log:     slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (w *Wikidata) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (w *Wikidata) Name() string { return subTechName }

// buildSPARQL returns a SPARQL SELECT query for automotive businesses in the
// country identified by the given Wikidata Q-code (e.g. "Q183" for Germany).
//
// Property paths:
//   - P31 / P279* = Q4830453 : instance of (or subclass of) business enterprise
//   - P452 = Q190960         : industry = automotive industry
//   - P17 = <qCode>          : country
//   - P625 (OPTIONAL)        : coordinate location (WKT literal)
//   - P856 (OPTIONAL)        : official website
//   - P3608 (OPTIONAL)       : EU VAT number
func (w *Wikidata) buildSPARQL(qCode string) string {
	return fmt.Sprintf(`SELECT ?dealer ?dealerLabel ?coords ?website ?vatID WHERE {
  ?dealer wdt:P31/wdt:P279* wd:Q4830453;
          wdt:P452 wd:Q190960;
          wdt:P17 wd:%s.
  OPTIONAL { ?dealer wdt:P625 ?coords. }
  OPTIONAL { ?dealer wdt:P856 ?website. }
  OPTIONAL { ?dealer wdt:P3608 ?vatID. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "de,fr,nl,es,en". }
}
LIMIT 5000`, qCode)
}

// RunForCountry executes the SPARQL query for a single country and persists
// all discovered dealers to the KG.
func (w *Wikidata) RunForCountry(ctx context.Context, iso string) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{
		SubTechniqueID: subTechID,
		Country:        iso,
	}

	qCode, ok := countryQCodes[iso]
	if !ok {
		return result, fmt.Errorf("wikidata.RunForCountry: unsupported country %q", iso)
	}

	sparql := w.buildSPARQL(qCode)
	reqURL := w.baseURL + "?query=" + url.QueryEscape(sparql) + "&format=json"

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return result, fmt.Errorf("wikidata.RunForCountry %s: build request: %w", iso, err)
	}
	req.Header.Set("Accept", "application/sparql-results+json")
	req.Header.Set("User-Agent", cardexUA)

	w.log.Info("wikidata: querying", "country", iso, "q_code", qCode)
	resp, err := w.client.Do(req)
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return result, fmt.Errorf("wikidata.RunForCountry %s: http: %w", iso, err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	if resp.StatusCode == http.StatusTooManyRequests {
		return result, fmt.Errorf("wikidata.RunForCountry %s: rate limited (429)", iso)
	}
	if resp.StatusCode != http.StatusOK {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return result, fmt.Errorf("wikidata.RunForCountry %s: HTTP %d: %s",
			iso, resp.StatusCode, string(raw))
	}

	var parsed sparqlResponse
	if err := json.NewDecoder(resp.Body).Decode(&parsed); err != nil {
		return result, fmt.Errorf("wikidata.RunForCountry %s: decode JSON: %w", iso, err)
	}

	for i := range parsed.Results.Bindings {
		b := &parsed.Results.Bindings[i]
		if err := w.upsert(ctx, iso, b); err != nil {
			w.log.Warn("wikidata: upsert error",
				"country", iso, "dealer_uri", b.Dealer.Value, "err", err)
			result.Errors++
			continue
		}
		result.Discovered++
		metrics.DealersTotal.WithLabelValues(familyID, iso).Inc()
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, iso).Observe(result.Duration.Seconds())
	w.log.Info("wikidata: done",
		"country", iso,
		"discovered", result.Discovered,
		"errors", result.Errors,
	)
	return result, nil
}

// Run iterates over all 6 target countries with a 2-second inter-country delay
// to comply with Wikimedia API etiquette (total ~20 s for 6 countries).
func (w *Wikidata) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	combined := &runner.SubTechniqueResult{SubTechniqueID: subTechID}
	for i, iso := range allCountries {
		if ctx.Err() != nil {
			return combined, ctx.Err()
		}
		res, err := w.RunForCountry(ctx, iso)
		if res != nil {
			combined.Discovered += res.Discovered
			combined.Errors += res.Errors
		}
		if err != nil {
			w.log.Warn("wikidata.Run: country error", "country", iso, "err", err)
		}
		// Respect Wikidata rate limit: wait 2 s between country queries.
		if i < len(allCountries)-1 {
			select {
			case <-ctx.Done():
				return combined, ctx.Err()
			case <-time.After(2 * time.Second):
			}
		}
	}
	return combined, nil
}

// upsert writes a single Wikidata binding into the Knowledge Graph.
// Bindings without a label (no dealerLabel value) are skipped.
func (w *Wikidata) upsert(ctx context.Context, iso string, b *sparqlBinding) error {
	// Require a label to produce a usable canonical name.
	label := ""
	if b.DealerLabel != nil {
		label = strings.TrimSpace(b.DealerLabel.Value)
	}
	if label == "" {
		return nil // skip — no usable name
	}

	qid := extractQID(b.Dealer.Value)
	if qid == "" {
		return fmt.Errorf("wikidata: cannot extract QID from URI %q", b.Dealer.Value)
	}

	now := time.Now().UTC()

	existing, err := w.graph.FindDealerByIdentifier(ctx, kg.IdentifierWikidataQID, qid)
	if err != nil {
		return err
	}
	dealerID := ulid.Make().String()
	if existing != "" {
		dealerID = existing
	}

	entity := &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     label,
		NormalizedName:    strings.ToLower(label),
		CountryCode:       iso,
		Status:            kg.StatusUnverified,
		ConfidenceScore:   kg.BaseWeights[familyID],
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}
	if err := w.graph.UpsertDealer(ctx, entity); err != nil {
		return err
	}

	// Primary identifier: Wikidata QID.
	if err := w.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
		IdentifierID:    ulid.Make().String(),
		DealerID:        dealerID,
		IdentifierType:  kg.IdentifierWikidataQID,
		IdentifierValue: qid,
		SourceFamily:    familyID,
		ValidStatus:     "VALID",
	}); err != nil {
		return err
	}

	// Secondary identifier: EU VAT number (when present).
	if b.VatID != nil && b.VatID.Value != "" {
		if err := w.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
			IdentifierID:    ulid.Make().String(),
			DealerID:        dealerID,
			IdentifierType:  kg.IdentifierVAT,
			IdentifierValue: b.VatID.Value,
			SourceFamily:    familyID,
			ValidStatus:     "UNVERIFIED",
		}); err != nil {
			// Non-fatal: identifier may already exist from another family.
			w.log.Warn("wikidata: add VAT identifier", "qid", qid, "err", err)
		}
	}

	// Location — from WKT coordinates when present.
	loc := &kg.DealerLocation{
		LocationID:     ulid.Make().String(),
		DealerID:       dealerID,
		IsPrimary:      true,
		CountryCode:    iso,
		SourceFamilies: familyID,
	}
	if b.Coords != nil && b.Coords.Value != "" {
		lat, lon, err := ParseWKTPoint(b.Coords.Value)
		if err != nil {
			w.log.Warn("wikidata: parse WKT coords", "qid", qid, "raw", b.Coords.Value, "err", err)
		} else {
			loc.Lat = &lat
			loc.Lon = &lon
		}
	}
	// Store website in MetadataJSON when present (KG interface has no AddWebPresence).
	if b.Website != nil && b.Website.Value != "" {
		encoded, _ := json.Marshal(map[string]string{"website": b.Website.Value})
		s := string(encoded)
		entity.MetadataJSON = &s
		// Re-upsert to persist the metadata (idempotent ON CONFLICT).
		if err := w.graph.UpsertDealer(ctx, entity); err != nil {
			w.log.Warn("wikidata: re-upsert with website metadata", "qid", qid, "err", err)
		}
	}
	if err := w.graph.AddLocation(ctx, loc); err != nil {
		return err
	}

	wikidataURL := "https://www.wikidata.org/entity/" + qid
	return w.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		SourceURL:             &wikidataURL,
		SourceRecordID:        &qid,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
	})
}

// HealthCheck issues a minimal SPARQL query (ASK form) to verify the endpoint.
func (w *Wikidata) HealthCheck(ctx context.Context) error {
	probe := `ASK { wd:Q183 wdt:P31 wd:Q6256. }`
	reqURL := w.baseURL + "?query=" + url.QueryEscape(probe) + "&format=json"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "application/sparql-results+json")
	req.Header.Set("User-Agent", cardexUA)
	resp, err := w.client.Do(req)
	if err != nil {
		return fmt.Errorf("wikidata health: %w", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("wikidata health: HTTP %d", resp.StatusCode)
	}
	return nil
}

// ── SPARQL JSON response types ────────────────────────────────────────────────

type sparqlResponse struct {
	Results struct {
		Bindings []sparqlBinding `json:"bindings"`
	} `json:"results"`
}

type sparqlBinding struct {
	Dealer      sparqlValue  `json:"dealer"`
	DealerLabel *sparqlValue `json:"dealerLabel"`
	Coords      *sparqlValue `json:"coords"`
	Website     *sparqlValue `json:"website"`
	VatID       *sparqlValue `json:"vatID"`
}

type sparqlValue struct {
	Type     string `json:"type"`
	Value    string `json:"value"`
	Language string `json:"xml:lang"`
	Datatype string `json:"datatype"`
}

// ── Helpers ───────────────────────────────────────────────────────────────────

// ParseWKTPoint parses a WKT Point literal of the form "Point(lon lat)" and
// returns latitude and longitude as float64 values.
//
// Note: WKT (ISO 19125 / OGC) uses (longitude latitude) order — the X axis
// is longitude and the Y axis is latitude. Wikidata follows this convention.
// Exported for use in tests (TestWikidata_ParseWKT).
func ParseWKTPoint(s string) (lat, lon float64, err error) {
	s = strings.TrimSpace(s)
	// Accept both "Point(...)" and "POINT(...)" capitalisation variants.
	upper := strings.ToUpper(s)
	if !strings.HasPrefix(upper, "POINT(") || !strings.HasSuffix(s, ")") {
		return 0, 0, fmt.Errorf("parseWKTPoint: unexpected format %q", s)
	}
	inner := s[strings.Index(s, "(")+1 : len(s)-1]
	parts := strings.Fields(inner)
	if len(parts) != 2 {
		return 0, 0, fmt.Errorf("parseWKTPoint: expected 2 coordinates, got %d in %q", len(parts), s)
	}
	lon, err = strconv.ParseFloat(parts[0], 64)
	if err != nil {
		return 0, 0, fmt.Errorf("parseWKTPoint: parse longitude %q: %w", parts[0], err)
	}
	lat, err = strconv.ParseFloat(parts[1], 64)
	if err != nil {
		return 0, 0, fmt.Errorf("parseWKTPoint: parse latitude %q: %w", parts[1], err)
	}
	return lat, lon, nil
}

// extractQID extracts the Wikidata QID from a Wikidata entity URI.
// E.g. "http://www.wikidata.org/entity/Q12345" → "Q12345".
func extractQID(uri string) string {
	idx := strings.LastIndex(uri, "/")
	if idx < 0 || idx == len(uri)-1 {
		return ""
	}
	return uri[idx+1:]
}
