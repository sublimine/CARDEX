// Package osm implements sub-technique B.1 — OpenStreetMap Overpass API
// geocartografía de dealers para los 6 países objetivo.
//
// Strategy: POST a single Overpass QL query per country using the
// area["ISO3166-1"=...] filter with all automotive-relevant OSM tags.
// Results are persisted incrementally to the KG.
//
// Rate limiting: Overpass API requests one query per 10 seconds to stay
// below the public rate limit of the overpass-api.de endpoint.
//
// Tags queried per element:
//   - shop ~ car|motorcycle|caravan|trailer|truck
//   - craft = car_repair
//   - office = automotive
//   - amenity = car_rental
package osm

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	defaultOverpassURL = "https://overpass-api.de/api/interpreter"
	// overpassHTTPTimeout: 300s query timeout + 30s network buffer.
	overpassHTTPTimeout = 330 * time.Second
	cardexUA            = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
	familyID            = "B"
	subTechID           = "B.1"
	subTechName         = "OSM Overpass API — geocartografía de dealers"
)

// allCountries is the ordered set of ISO 3166-1 alpha-2 codes for the 6 target markets.
var allCountries = []string{"DE", "FR", "ES", "BE", "NL", "CH"}


// Overpass executes B.1 sub-technique queries against the Overpass API.
type Overpass struct {
	graph   kg.KnowledgeGraph
	client  *http.Client
	baseURL string
	log     *slog.Logger
}

// New creates an Overpass executor with the production endpoint.
func New(graph kg.KnowledgeGraph) *Overpass {
	return NewWithBaseURL(graph, defaultOverpassURL)
}

// NewWithBaseURL creates an Overpass executor with a custom endpoint (for tests).
func NewWithBaseURL(graph kg.KnowledgeGraph, baseURL string) *Overpass {
	return &Overpass{
		graph:   graph,
		client:  &http.Client{Timeout: overpassHTTPTimeout},
		baseURL: baseURL,
		log:     slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (op *Overpass) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (op *Overpass) Name() string { return subTechName }

// buildQuery returns an Overpass QL query string for a single country.
// The query uses the standard ISO 3166-1 alpha-2 code as the area filter
// and fetches all nodes/ways/relations with automotive-relevant tags.
func (op *Overpass) buildQuery(iso string) string {
	return fmt.Sprintf(
		`[out:json][timeout:300];
area["ISO3166-1"="%s"]->.searchArea;
(
  nwr["shop"~"car|motorcycle|caravan|trailer|truck"](area.searchArea);
  nwr["craft"="car_repair"](area.searchArea);
  nwr["office"="automotive"](area.searchArea);
  nwr["amenity"="car_rental"](area.searchArea);
);
out center tags;`,
		iso,
	)
}

// queryEncode percent-encodes a query string for an application/x-www-form-urlencoded
// POST body. Uses url.QueryEscape — NOT strings.ReplaceAll — to correctly handle
// all special characters (brackets, quotes, semicolons, equals signs, etc.).
func queryEncode(q string) string {
	return url.QueryEscape(q)
}

// RunForCountry executes the Overpass query for a single country and persists
// all discovered dealers to the KG. Returns a SubTechniqueResult with counts
// of newly upserted dealers and errors encountered.
func (op *Overpass) RunForCountry(ctx context.Context, iso string) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{
		SubTechniqueID: subTechID,
		Country:        iso,
	}

	q := op.buildQuery(iso)
	body := "data=" + queryEncode(q)

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, op.baseURL,
		strings.NewReader(body))
	if err != nil {
		return result, fmt.Errorf("overpass.RunForCountry %s: build request: %w", iso, err)
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("User-Agent", cardexUA)

	op.log.Info("overpass: querying", "country", iso)
	resp, err := op.client.Do(req)
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return result, fmt.Errorf("overpass.RunForCountry %s: http: %w", iso, err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	if resp.StatusCode == http.StatusTooManyRequests {
		return result, fmt.Errorf("overpass.RunForCountry %s: rate limited (429)", iso)
	}
	if resp.StatusCode != http.StatusOK {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return result, fmt.Errorf("overpass.RunForCountry %s: HTTP %d: %s",
			iso, resp.StatusCode, string(raw))
	}

	var parsed overpassResponse
	if err := json.NewDecoder(resp.Body).Decode(&parsed); err != nil {
		return result, fmt.Errorf("overpass.RunForCountry %s: decode JSON: %w", iso, err)
	}

	for i := range parsed.Elements {
		el := &parsed.Elements[i]
		upserted, err := op.upsert(ctx, iso, el)
		if err != nil {
			op.log.Warn("overpass: upsert error",
				"country", iso, "osm_id", osmID(el), "err", err)
			result.Errors++
			continue
		}
		if upserted {
			result.Discovered++
			metrics.DealersTotal.WithLabelValues(familyID, iso).Inc()
		}
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, iso).Observe(result.Duration.Seconds())
	op.log.Info("overpass: done",
		"country", iso,
		"discovered", result.Discovered,
		"errors", result.Errors,
	)
	return result, nil
}

// Run iterates over all 6 target countries with a 10-second inter-country delay
// to stay within the Overpass API rate limits (1 request per 10 s).
func (op *Overpass) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	combined := &runner.SubTechniqueResult{SubTechniqueID: subTechID}
	for i, iso := range allCountries {
		if ctx.Err() != nil {
			return combined, ctx.Err()
		}
		res, err := op.RunForCountry(ctx, iso)
		if res != nil {
			combined.Discovered += res.Discovered
			combined.Errors += res.Errors
		}
		if err != nil {
			op.log.Warn("overpass.Run: country error", "country", iso, "err", err)
		}
		// Respect Overpass rate limit: wait 10 s between country queries.
		if i < len(allCountries)-1 {
			select {
			case <-ctx.Done():
				return combined, ctx.Err()
			case <-time.After(10 * time.Second):
			}
		}
	}
	return combined, nil
}

// upsert writes a single OSM element into the Knowledge Graph.
// Returns (false, nil) when the element is skipped due to a missing name tag.
// Returns (true, nil) on successful upsert.
// Returns (false, err) on a KG write error.
func (op *Overpass) upsert(ctx context.Context, iso string, el *overpassElement) (bool, error) {
	name := firstNonEmpty(
		el.Tags["name"],
		el.Tags["operator"],
		el.Tags["brand"],
	)
	if name == "" {
		return false, nil // skip silently — no name = no actionable dealer entity
	}

	id := osmID(el)
	now := time.Now().UTC()

	existing, err := op.graph.FindDealerByIdentifier(ctx, kg.IdentifierOSMID, id)
	if err != nil {
		return false, err
	}
	dealerID := ulid.Make().String()
	if existing != "" {
		dealerID = existing
	}

	entity := &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     name,
		NormalizedName:    normalize(name),
		CountryCode:       iso,
		Status:            kg.StatusUnverified,
		ConfidenceScore:   kg.BaseWeights[familyID],
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}
	if err := op.graph.UpsertDealer(ctx, entity); err != nil {
		return false, err
	}

	if err := op.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
		IdentifierID:    ulid.Make().String(),
		DealerID:        dealerID,
		IdentifierType:  kg.IdentifierOSMID,
		IdentifierValue: id,
		SourceFamily:    familyID,
		ValidStatus:     "VALID",
	}); err != nil {
		return false, err
	}

	// Location — build from coordinates (node direct / way|relation via center)
	// and any addr:* tags present.
	loc := &kg.DealerLocation{
		LocationID:     ulid.Make().String(),
		DealerID:       dealerID,
		IsPrimary:      true,
		CountryCode:    iso,
		SourceFamilies: familyID,
	}
	if lat, lon, ok := coordsOf(el); ok {
		loc.Lat = &lat
		loc.Lon = &lon
	}
	loc.PostalCode = ptrIfNotEmpty(el.Tags["addr:postcode"])
	loc.City = ptrIfNotEmpty(el.Tags["addr:city"])
	if street := el.Tags["addr:street"]; street != "" {
		line := street
		if h := el.Tags["addr:housenumber"]; h != "" {
			line = street + " " + h
		}
		loc.AddressLine1 = &line
	}
	if err := op.graph.AddLocation(ctx, loc); err != nil {
		return false, err
	}

	srcID := id
	if err := op.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		SourceRecordID:        &srcID,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
	}); err != nil {
		return false, err
	}

	return true, nil
}

// HealthCheck sends a minimal Overpass query to verify API availability.
func (op *Overpass) HealthCheck(ctx context.Context) error {
	probe := `[out:json][timeout:10];node(1);out;`
	body := "data=" + queryEncode(probe)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, op.baseURL,
		strings.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("User-Agent", cardexUA)
	resp, err := op.client.Do(req)
	if err != nil {
		return fmt.Errorf("overpass health: %w", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("overpass health: HTTP %d", resp.StatusCode)
	}
	return nil
}

// ── JSON response types ───────────────────────────────────────────────────────

type overpassResponse struct {
	Elements []overpassElement `json:"elements"`
}

type overpassElement struct {
	Type   string            `json:"type"`
	ID     int64             `json:"id"`
	Lat    float64           `json:"lat"`
	Lon    float64           `json:"lon"`
	Center *overpassCenter   `json:"center"`
	Tags   map[string]string `json:"tags"`
}

type overpassCenter struct {
	Lat float64 `json:"lat"`
	Lon float64 `json:"lon"`
}

// ── Helpers ───────────────────────────────────────────────────────────────────

// osmID returns the canonical OSM element identifier string.
// Nodes use the "node/ID" format; ways and relations use "way/ID" and "relation/ID".
func osmID(el *overpassElement) string {
	return fmt.Sprintf("%s/%d", el.Type, el.ID)
}

// coordsOf extracts geographic coordinates from an OSM element.
// Node elements carry lat/lon directly; way and relation elements carry
// coordinates in the "center" object (requires "out center" in the query).
func coordsOf(el *overpassElement) (lat, lon float64, ok bool) {
	if el.Type == "node" && (el.Lat != 0 || el.Lon != 0) {
		return el.Lat, el.Lon, true
	}
	if el.Center != nil && (el.Center.Lat != 0 || el.Center.Lon != 0) {
		return el.Center.Lat, el.Center.Lon, true
	}
	return 0, 0, false
}

// firstNonEmpty returns the first non-empty string from the argument list.
func firstNonEmpty(ss ...string) string {
	for _, s := range ss {
		if s != "" {
			return s
		}
	}
	return ""
}

// normalize returns the lowercase form of s for use as normalized_name.
func normalize(s string) string {
	return strings.ToLower(s)
}

// ptrIfNotEmpty returns a pointer to s when s is non-empty, otherwise nil.
func ptrIfNotEmpty(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}
