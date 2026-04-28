// Package common provides shared helpers for all Family H OEM dealer-locator
// sub-techniques.
//
// Every OEM adapter in familia_h/{oem}/ is built on three primitives:
//
//  1. CountryPostcodes — top-10 population-centre postcodes per country,
//     shared across all geo-sweeps.
//
//  2. ParseResponse — a flexible JSON parser that handles the common OEM API
//     response shapes (dealers/dealerships/results/data/items/locations/points
//     envelope keys, plus bare arrays and extra custom keys).
//
//  3. SweepBrand — the postcode geo-sweep loop: iterate postcodes, call
//     browser.InterceptXHR, parse dealers, de-duplicate, upsert via callback.
//
// Each OEM adapter only needs to supply brand × country URL maps, an XHR
// filter pattern, and a thin ParseCapture wrapper (which may call ParseResponse
// directly or add OEM-specific pre-processing).
package common

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/url"
	"strings"
	"time"

	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/browser"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
)

// CountryPostcodes maps ISO-3166-1 alpha-2 country codes to top-10
// population-centre postcodes. Geo-sweep with these 10 postcodes covers
// 90%+ of OEM dealers within typical 50 km search radii.
var CountryPostcodes = map[string][]string{
	"DE": {"10115", "20095", "80331", "50667", "60313", "70173", "40213", "28195", "30159", "04109"},
	"FR": {"75001", "69001", "13001", "31000", "67000", "44000", "33000", "06000", "34000", "76000"},
	"ES": {"28001", "08001", "41001", "48001", "46001", "50001", "29001", "39001", "15001", "36200"},
	"NL": {"1011", "3011", "2511", "5611", "6811", "9711", "1066", "3521", "1090", "2600"},
	"BE": {"1000", "2000", "9000", "4000", "3000", "5000", "8000", "6000", "1400", "2300"},
	"CH": {"8001", "4001", "1201", "3001", "6900", "6000", "5001", "9000", "7000", "2000"},
}

// GenericDealer is the normalised dealer record shared across all OEM JSON
// API responses. It covers field-name variants observed across VWG, BMW,
// Mercedes, Toyota, Hyundai, Renault, Ford, and Stellantis platforms.
type GenericDealer struct {
	// ID field variants — different OEMs use different key names.
	ID           string `json:"id"`
	DealerID     string `json:"dealerId"`
	DealerCode   string `json:"dealerCode"`
	Code         string `json:"code"`
	SiteID       string `json:"siteId"`
	DealershipID string `json:"dealershipId"`
	AccountID    string `json:"accountId"`

	// Name field variants.
	Name        string `json:"name"`
	DealerName  string `json:"dealerName"`
	CompanyName string `json:"companyName"`

	// Address — nested object covering postal-code field variants.
	Address struct {
		Street      string `json:"street"`
		PostalCode  string `json:"postalCode"`
		ZipCode     string `json:"zipCode"`
		Zip         string `json:"zip"`
		City        string `json:"city"`
		CountryCode string `json:"countryCode"`
		Country     string `json:"country"`
	} `json:"address"`

	Phone   string `json:"phone"`
	Email   string `json:"email"`
	Website string `json:"website"`
	URL     string `json:"url"`
}

// CanonicalID returns the first non-empty ID field across all known variants.
func (d *GenericDealer) CanonicalID() string {
	for _, v := range []string{d.ID, d.DealerID, d.DealerCode, d.Code, d.SiteID, d.DealershipID, d.AccountID} {
		if v != "" {
			return v
		}
	}
	return ""
}

// CanonicalName returns the first non-empty name field.
func (d *GenericDealer) CanonicalName() string {
	for _, v := range []string{d.Name, d.DealerName, d.CompanyName} {
		if v != "" {
			return v
		}
	}
	return ""
}

// PostalCode returns the first non-empty postal code field.
func (d *GenericDealer) PostalCode() string {
	for _, v := range []string{d.Address.PostalCode, d.Address.ZipCode, d.Address.Zip} {
		if v != "" {
			return v
		}
	}
	return ""
}

// CountryCode returns the first non-empty country code field.
func (d *GenericDealer) CountryCode() string {
	if d.Address.CountryCode != "" {
		return d.Address.CountryCode
	}
	return d.Address.Country
}

// WebsiteURL returns the first non-empty website URL.
func (d *GenericDealer) WebsiteURL() string {
	if d.Website != "" {
		return d.Website
	}
	return d.URL
}

// ─── JSON parsing ─────────────────────────────────────────────────────────────

// oemAPIResponse covers all standard OEM dealer API response envelopes.
type oemAPIResponse struct {
	Dealers     []GenericDealer `json:"dealers"`
	Dealerships []GenericDealer `json:"dealerships"`
	Results     []GenericDealer `json:"results"`
	Data        []GenericDealer `json:"data"`
	Items       []GenericDealer `json:"items"`
	Locations   []GenericDealer `json:"locations"`
	Points      []GenericDealer `json:"points"`
}

// ParseResponse extracts GenericDealer records from a raw XHR response body.
//
// Tries the standard envelopes (dealers, dealerships, results, data, items,
// locations, points) plus any extraKeys supplied by the caller.
// Falls back to a bare JSON array. Returns (nil, nil) if body is empty or no
// dealers found — this is not an error; the caller should check len(result).
func ParseResponse(body []byte, extraKeys ...string) ([]GenericDealer, error) {
	if len(body) == 0 {
		return nil, nil
	}

	// Try standard object envelope; ignore error — body may be a bare array.
	var resp oemAPIResponse
	_ = json.Unmarshal(body, &resp)

	for _, list := range [][]GenericDealer{
		resp.Dealers, resp.Dealerships, resp.Results,
		resp.Data, resp.Items, resp.Locations, resp.Points,
	} {
		if len(list) > 0 {
			return list, nil
		}
	}

	// Try caller-supplied extra envelope keys.
	if len(extraKeys) > 0 {
		var rawMap map[string]json.RawMessage
		if err := json.Unmarshal(body, &rawMap); err == nil {
			for _, key := range extraKeys {
				if val, ok := rawMap[key]; ok {
					var dealers []GenericDealer
					if err2 := json.Unmarshal(val, &dealers); err2 == nil && len(dealers) > 0 {
						return dealers, nil
					}
				}
			}
		}
	}

	// Bare array fallback.
	var list []GenericDealer
	if err := json.Unmarshal(body, &list); err == nil && len(list) > 0 {
		return list, nil
	}

	return nil, nil
}

// DefaultXHRFilter returns a browser.XHRFilter that matches the URL patterns
// commonly used by OEM dealer-locator backend APIs. Pass extra patterns to
// broaden the match for OEMs with non-standard URL shapes.
func DefaultXHRFilter(extraPatterns ...string) browser.XHRFilter {
	base := `(dealer|haendler|h[äa]ndler|concession|locator|location|network|point[s]?|garage|retailer|showroom|service[-_]?center)`
	if len(extraPatterns) > 0 {
		base = base + "|" + strings.Join(extraPatterns, "|")
	}
	return browser.XHRFilter{
		URLPattern:    base,
		MethodFilter:  []string{"GET", "POST"},
		MinStatusCode: 200,
	}
}

// ─── Geo-sweep ────────────────────────────────────────────────────────────────

// SweepBrand performs the postcode geo-sweep for a single brand × locator URL.
//
// For each postcode in postcodes it navigates to "{locatorURL}?{postcodeParam}={pc}"
// using browser.InterceptXHR, parses captured responses with parseFn, de-duplicates
// by brand+canonicalID, and calls upsertFn for each new/confirmed dealer.
// Returns (discovered, confirmed, errors).
//
// postcodeParam defaults to "zip" if empty.
// A log message at Info level is emitted if no XHR data was captured (i.e., the
// locator SPA requires JS form interaction not triggered by URL parameters).
func SweepBrand(
	ctx context.Context,
	b browser.Browser,
	brand, locatorURL string,
	postcodes []string,
	xhrFilter browser.XHRFilter,
	postcodeParam string,
	parseFn func([]byte) ([]GenericDealer, error),
	upsertFn func(ctx context.Context, brand string, d GenericDealer, sourceURL string) (bool, error),
	log *slog.Logger,
) (disc, conf, errs int) {
	if postcodeParam == "" {
		postcodeParam = "zip"
	}

	seen := make(map[string]bool) // "brand:dealerID" → already processed

	for _, pc := range postcodes {
		if ctx.Err() != nil {
			break
		}

		sweepURL := locatorURL + "?" + postcodeParam + "=" + pc
		captures, err := b.InterceptXHR(ctx, sweepURL, xhrFilter)
		if err != nil {
			log.Warn("common.SweepBrand: InterceptXHR error",
				"brand", brand, "postcode", pc, "err", err)
			errs++
			continue
		}
		if len(captures) == 0 {
			log.Debug("common.SweepBrand: no XHR captured",
				"brand", brand, "postcode", pc, "url", sweepURL)
			continue
		}

		for _, capture := range captures {
			dealers, parseErr := parseFn(capture.ResponseBody)
			if parseErr != nil || len(dealers) == 0 {
				continue
			}
			for _, d := range dealers {
				cid := d.CanonicalID()
				if cid == "" || seen[brand+":"+cid] {
					continue
				}
				seen[brand+":"+cid] = true

				upserted, upsertErr := upsertFn(ctx, brand, d, capture.RequestURL)
				if upsertErr != nil {
					log.Warn("common.SweepBrand: upsert error",
						"brand", brand, "id", cid, "err", upsertErr)
					errs++
					continue
				}
				if upserted {
					disc++
				} else {
					conf++
				}
			}
		}
	}

	if disc == 0 && conf == 0 && errs == 0 {
		log.Info("common.SweepBrand: no data captured — may require JS form interaction",
			"brand", brand, "locator", locatorURL,
			"deferred", "Sprint 10: page.Evaluate / form interaction support")
	}
	return disc, conf, errs
}

// ─── KG upsert ───────────────────────────────────────────────────────────────

// UpsertDealer performs the standard KG upsert for an OEM GenericDealer.
//
// dealerKey is the full OEM_DEALER_ID value (e.g. "peugeot:FR-001234").
// familyID is "H", subTechID is e.g. "H.STELLANTIS.PEUGEOT.FR".
// A new ULID dealer_id is allocated when the dealer is first seen; subsequent
// calls confirm it (returning isNew=false).
func UpsertDealer(
	ctx context.Context,
	graph kg.KnowledgeGraph,
	dealerKey, familyID, subTechID, sourceURL string,
	d GenericDealer,
	log *slog.Logger,
) (bool, error) {
	now := time.Now().UTC()
	country := d.CountryCode()
	name := d.CanonicalName()
	if name == "" {
		return false, nil // skip nameless dealers silently
	}

	existing, err := graph.FindDealerByIdentifier(ctx, kg.IdentifierOEMDealerID, dealerKey)
	if err != nil {
		return false, fmt.Errorf("common.UpsertDealer find: %w", err)
	}

	isNew := existing == ""
	dealerID := existing
	if isNew {
		dealerID = ulid.Make().String()
	}

	if err := graph.UpsertDealer(ctx, &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     name,
		NormalizedName:    strings.ToLower(name),
		CountryCode:       country,
		Status:            kg.StatusUnverified,
		ConfidenceScore:   kg.BaseWeights[familyID],
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}); err != nil {
		return false, fmt.Errorf("common.UpsertDealer dealer: %w", err)
	}

	if isNew {
		if err := graph.AddIdentifier(ctx, &kg.DealerIdentifier{
			IdentifierID:    ulid.Make().String(),
			DealerID:        dealerID,
			IdentifierType:  kg.IdentifierOEMDealerID,
			IdentifierValue: dealerKey,
		}); err != nil {
			return false, fmt.Errorf("common.UpsertDealer identifier: %w", err)
		}
	}

	street := strings.TrimSpace(d.Address.Street)
	if street != "" || d.PostalCode() != "" || d.Address.City != "" {
		if err := graph.AddLocation(ctx, &kg.DealerLocation{
			LocationID:     ulid.Make().String(),
			DealerID:       dealerID,
			IsPrimary:      true,
			AddressLine1:   PtrIfNotEmpty(street),
			PostalCode:     PtrIfNotEmpty(d.PostalCode()),
			City:           PtrIfNotEmpty(d.Address.City),
			CountryCode:    country,
			Phone:          PtrIfNotEmpty(d.Phone),
			SourceFamilies: familyID,
		}); err != nil {
			log.Warn("common.UpsertDealer location error", "dealer", name, "err", err)
		}
	}

	if ws := d.WebsiteURL(); ws != "" {
		if dom := ExtractDomain(ws); dom != "" {
			if err := graph.UpsertWebPresence(ctx, &kg.DealerWebPresence{
				WebID:                ulid.Make().String(),
				DealerID:             dealerID,
				Domain:               dom,
				URLRoot:              ws,
				DiscoveredByFamilies: familyID,
			}); err != nil {
				log.Warn("common.UpsertDealer web presence error", "domain", dom, "err", err)
			}
		}
	}

	if err := graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
		SourceURL:             PtrIfNotEmpty(sourceURL),
	}); err != nil {
		log.Warn("common.UpsertDealer discovery error", "dealer", name, "err", err)
	}

	if isNew {
		metrics.DealersTotal.WithLabelValues(familyID, country).Inc()
	}

	return isNew, nil
}

// ─── Small helpers ────────────────────────────────────────────────────────────

// PtrIfNotEmpty returns a pointer to s, or nil if s is empty.
func PtrIfNotEmpty(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

// ExtractDomain returns the hostname without the www. prefix from a URL string.
// Returns empty string if rawURL cannot be parsed.
func ExtractDomain(rawURL string) string {
	if !strings.Contains(rawURL, "://") {
		rawURL = "https://" + rawURL
	}
	u, err := url.Parse(rawURL)
	if err != nil || u.Host == "" {
		return ""
	}
	return strings.TrimPrefix(u.Host, "www.")
}
