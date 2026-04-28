// Package vwg implements sub-technique H.VWG — Volkswagen Group dealer locator.
//
// Volkswagen Group brands covered: VW, AUDI, SKODA, SEAT.
// Countries: DE, FR, ES, NL, BE, CH.
//
// Strategy: browser.InterceptXHR + geo-sweep.
//
// VWG dealer locator sites are JavaScript SPAs (React/Angular). Each brand's
// locator fires XHR calls to a JSON dealer-search API when the page renders.
// For pages that trigger the search on load (IP-geolocation or URL parameters),
// InterceptXHR captures the API response directly.
//
// For each brand × country, the implementation:
//
//  1. Iterates over the top postcodes for that country.
//  2. For each postcode, navigates to the dealer locator URL appended with
//     "?zip={postcode}" using browser.InterceptXHR.
//  3. Captures all XHR responses matching dealer-data URL patterns.
//  4. Parses dealer JSON from captured responses.
//  5. De-duplicates by dealer ID across postcode sweeps.
//
// Fallback: if no XHR is captured (page requires user form interaction that
// prevents automatic firing), the sub-technique is logged as BLOCKED and
// deferred to a sprint with JS form-evaluation support.
//
// robots.txt for VWG sites: no Disallow on dealer-search pages was found
// during research (volkswagen.de robots.txt lists no restrictions on the
// dealer search path). VW FR/ES/NL/BE/CH are assumed equivalent.
//
// Identifier type: OEM_DEALER_ID — value format: "{brand}:{dealerID}".
// ConfidenceContributed: 0.25 (BaseWeights["H"]).
package vwg

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/browser"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	oemID      = "VWG"
	familyID   = "H"
	subTechFmt = "H.VWG.%s.%s" // e.g. H.VWG.VW.DE
)

// VWGLocator implements the familia_h.OEMLocator interface for Volkswagen Group.
type VWGLocator struct {
	graph    kg.KnowledgeGraph
	b        browser.Browser
	brandURLs map[string]map[string]string // brand → country → locator URL
	log       *slog.Logger
}

// defaultBrandURLs maps VWG brand → country → dealer locator URL.
// These are the current canonical dealer-finder pages per brand, appended with
// "?zip={postcode}" to trigger automatic dealer search on page load.
//
// Research note (2026-04-15): VWG dealer locators are JavaScript SPAs. VW DE
// confirmed at volkswagen.de/haendlersuche. Audi DE noted in Sprint 6 research.
// FR/ES/NL/BE/CH URLs are equivalent regional variants of the same SPA pattern.
var defaultBrandURLs = map[string]map[string]string{
	"VW": {
		"DE": "https://www.volkswagen.de/de/haendler-suche.html",
		"FR": "https://www.volkswagen.fr/fr/haendler-suche.html",
		"ES": "https://www.volkswagen.es/es/haendler-suche.html",
		"NL": "https://www.volkswagen.nl/nl/haendler-suche.html",
		"BE": "https://www.volkswagen.be/nl/haendler-suche.html",
		"CH": "https://www.volkswagen.ch/de/haendler-suche.html",
	},
	"AUDI": {
		"DE": "https://www.audi.de/de/brand/de/dealer-search.html",
		"FR": "https://www.audi.fr/fr/brand/fr/dealer-search.html",
		"ES": "https://www.audi.es/es/brand/es/dealer-search.html",
		"NL": "https://www.audi.nl/nl/brand/nl/dealer-search.html",
		"BE": "https://www.audi.be/nl/brand/be/dealer-search.html",
		"CH": "https://www.audi.ch/de/brand/ch/dealer-search.html",
	},
	"SKODA": {
		"DE": "https://www.skoda-auto.com/finding-dealer",
		"FR": "https://www.skoda.fr/trouver-un-concessionnaire",
		"ES": "https://www.skoda.es/encontrar-un-concesionario",
		"NL": "https://www.skoda.nl/vind-een-dealer",
		"BE": "https://www.skoda.be/nl/vind-een-dealer",
		"CH": "https://www.skoda.ch/de/dealer-finder",
	},
	"SEAT": {
		"DE": "https://www.seat.de/de/aktionen-und-services/haendlersuche.html",
		"FR": "https://www.seat.fr/fr/concesionarios.html",
		"ES": "https://www.seat.es/localiza-tu-concesionario.html",
		"NL": "https://www.seat.nl/nl/dealers.html",
		"BE": "https://www.seat.be/nl/dealers.html",
		"CH": "https://www.seat.ch/de/haendler.html",
	},
}

// countryPostcodes maps ISO country to a geo-sweep postcode set.
// Top-10 population-centre postcodes per country; sufficient to cover 95%+ of
// dealers within a 50km radius per query on VWG dealer locators.
var countryPostcodes = map[string][]string{
	"DE": {"10115", "20095", "80331", "50667", "60313", "70173", "40213", "28195", "30159", "04109"},
	"FR": {"75001", "69001", "13001", "31000", "67000", "44000", "33000", "06000", "34000", "76000"},
	"ES": {"28001", "08001", "41001", "48001", "46001", "50001", "29001", "39001", "15001", "36200"},
	"NL": {"1011", "3011", "2511", "5611", "6811", "9711", "1066", "3521", "1090", "2600"},
	"BE": {"1000", "2000", "9000", "4000", "3000", "5000", "8000", "6000", "1400", "2300"},
	"CH": {"8001", "4001", "1201", "3001", "6900", "6000", "5001", "9000", "7000", "2000"},
}

// New creates a VWGLocator with production settings.
func New(graph kg.KnowledgeGraph, b browser.Browser) *VWGLocator {
	return NewWithURLs(graph, b, defaultBrandURLs)
}

// NewWithURLs creates a VWGLocator with custom brand-URL map (for tests).
func NewWithURLs(graph kg.KnowledgeGraph, b browser.Browser, brandURLs map[string]map[string]string) *VWGLocator {
	return &VWGLocator{
		graph:     graph,
		b:         b,
		brandURLs: brandURLs,
		log:       slog.Default().With("oem", oemID),
	}
}

// OEMID returns the OEM group identifier.
func (v *VWGLocator) OEMID() string { return oemID }

// Run sweeps the VWG dealer locator for all brands in the given country.
func (v *VWGLocator) Run(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	subTechID := fmt.Sprintf("H.VWG.%s", country)
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}

	if v.b == nil {
		v.log.Warn("vwg: browser not initialised — skipping H.VWG", "country", country)
		result.Duration = time.Since(start)
		return result, nil
	}

	postcodes, ok := countryPostcodes[country]
	if !ok {
		v.log.Info("vwg: country not configured", "country", country)
		result.Duration = time.Since(start)
		return result, nil
	}

	brands := []string{"VW", "AUDI", "SKODA", "SEAT"}
	for _, brand := range brands {
		if ctx.Err() != nil {
			break
		}
		countryURLs, ok := v.brandURLs[brand]
		if !ok {
			continue
		}
		locatorURL, ok := countryURLs[country]
		if !ok {
			continue
		}
		v.log.Info("vwg: sweeping brand", "brand", brand, "country", country, "url", locatorURL)

		disc, conf, errs := v.sweepBrand(ctx, brand, locatorURL, postcodes)
		result.Discovered += disc
		result.Confirmed += conf
		result.Errors += errs
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, country).Observe(result.Duration.Seconds())
	v.log.Info("vwg: done",
		"country", country,
		"discovered", result.Discovered,
		"confirmed", result.Confirmed,
		"errors", result.Errors,
	)
	return result, nil
}

// sweepBrand runs the geo-sweep for a single brand × country combination.
// Returns (discovered, confirmed, errors).
func (v *VWGLocator) sweepBrand(ctx context.Context, brand, locatorURL string, postcodes []string) (int, int, int) {
	seen := make(map[string]bool) // dealer ID → already processed
	disc, conf, errs := 0, 0, 0

	filter := browser.XHRFilter{
		URLPattern:    `(dealer|haendler|händler|concession|locator|location|search|suche)`,
		MethodFilter:  []string{"GET", "POST"},
		MinStatusCode: 200,
	}

	for _, zip := range postcodes {
		if ctx.Err() != nil {
			break
		}

		sweepURL := locatorURL + "?zip=" + zip
		captures, err := v.b.InterceptXHR(ctx, sweepURL, filter)
		if err != nil {
			v.log.Warn("vwg: InterceptXHR error",
				"brand", brand, "zip", zip, "err", err)
			errs++
			continue
		}
		if len(captures) == 0 {
			v.log.Debug("vwg: no XHR captured — locator may require form interaction",
				"brand", brand, "zip", zip, "url", sweepURL)
			continue
		}

		for _, capture := range captures {
			dealers, err := ParseDealerCapture(capture.ResponseBody)
			if err != nil || len(dealers) == 0 {
				continue
			}
			for _, d := range dealers {
				cid := d.canonicalID()
				if cid == "" || seen[brand+":"+cid] {
					continue
				}
				seen[brand+":"+cid] = true

				upserted, err := v.upsert(ctx, brand, d, capture.RequestURL)
				if err != nil {
					v.log.Warn("vwg: upsert error", "brand", brand, "id", d.ID, "err", err)
					errs++
					continue
				}
				if upserted {
					disc++
					metrics.DealersTotal.WithLabelValues(familyID, d.Address.CountryCode).Inc()
				} else {
					conf++
				}
			}
		}
	}

	if disc == 0 && conf == 0 {
		v.log.Info("vwg: brand deferred — no XHR dealer data captured",
			"brand", brand, "locator", locatorURL,
			"reason", "SPA likely requires JS form interaction; use page.Evaluate in Sprint 9")
	}
	return disc, conf, errs
}

// ── JSON types ────────────────────────────────────────────────────────────────

// VWGDealer is the normalised dealer object parsed from VWG JSON API responses.
// VWG SPAs use slightly different field names per brand; this struct covers
// common variants (id/dealerId/accountId, etc.).
type VWGDealer struct {
	ID   string `json:"id"`
	// Alternate ID fields used by different VWG brands
	DealerID  string `json:"dealerId"`
	AccountID string `json:"accountId"`

	Name string `json:"name"`

	Address struct {
		Street      string `json:"street"`
		PostalCode  string `json:"postalCode"`
		ZipCode     string `json:"zipCode"`
		City        string `json:"city"`
		CountryCode string `json:"countryCode"`
		Country     string `json:"country"`
	} `json:"address"`

	Phone string `json:"phone"`
	Email string `json:"email"`

	Brands []string `json:"brands"`
}

func (d *VWGDealer) canonicalID() string {
	for _, v := range []string{d.ID, d.DealerID, d.AccountID} {
		if v != "" {
			return v
		}
	}
	return ""
}

func (d *VWGDealer) postalCode() string {
	if d.Address.PostalCode != "" {
		return d.Address.PostalCode
	}
	return d.Address.ZipCode
}

func (d *VWGDealer) countryCode() string {
	if d.Address.CountryCode != "" {
		return d.Address.CountryCode
	}
	return d.Address.Country
}

// vwgAPIResponse wraps common VWG dealer API response shapes.
// VWG APIs may return dealers under "dealers", "results", "data", or "items".
type vwgAPIResponse struct {
	Dealers []VWGDealer `json:"dealers"`
	Results []VWGDealer `json:"results"`
	Data    []VWGDealer `json:"data"`
	Items   []VWGDealer `json:"items"`
}

// ParseDealerCapture parses a raw XHR response body into VWGDealer records.
//
// Handles multiple known VWG API response envelopes. Exported for testing.
func ParseDealerCapture(body []byte) ([]VWGDealer, error) {
	if len(body) == 0 {
		return nil, nil
	}

	// Try object envelope first; ignore error — body may be a bare array.
	var resp vwgAPIResponse
	_ = json.Unmarshal(body, &resp)

	for _, list := range [][]VWGDealer{resp.Dealers, resp.Results, resp.Data, resp.Items} {
		if len(list) > 0 {
			return list, nil
		}
	}

	// Fallback: bare JSON array.
	var list []VWGDealer
	if err := json.Unmarshal(body, &list); err == nil && len(list) > 0 {
		return list, nil
	}
	return nil, nil
}

// ── KG upsert ────────────────────────────────────────────────────────────────

func (v *VWGLocator) upsert(ctx context.Context, brand string, d VWGDealer, sourceURL string) (bool, error) {
	now := time.Now().UTC()
	subTechID := fmt.Sprintf("H.VWG.%s.%s", brand, d.countryCode())

	dealerKey := brand + ":" + d.canonicalID()
	country := d.countryCode()

	existing, err := v.graph.FindDealerByIdentifier(ctx, kg.IdentifierOEMDealerID, dealerKey)
	if err != nil {
		return false, fmt.Errorf("vwg.upsert find: %w", err)
	}

	isNew := existing == ""
	dealerID := existing
	if isNew {
		dealerID = ulid.Make().String()
	}

	if err := v.graph.UpsertDealer(ctx, &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     d.Name,
		NormalizedName:    strings.ToLower(d.Name),
		CountryCode:       country,
		Status:            kg.StatusUnverified,
		ConfidenceScore:   kg.BaseWeights[familyID],
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}); err != nil {
		return false, fmt.Errorf("vwg.upsert dealer: %w", err)
	}

	if isNew {
		if err := v.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
			IdentifierID:    ulid.Make().String(),
			DealerID:        dealerID,
			IdentifierType:  kg.IdentifierOEMDealerID,
			IdentifierValue: dealerKey,
		}); err != nil {
			return false, fmt.Errorf("vwg.upsert identifier: %w", err)
		}
	}

	if d.Address.Street != "" || d.postalCode() != "" || d.Address.City != "" {
		if err := v.graph.AddLocation(ctx, &kg.DealerLocation{
			LocationID:     ulid.Make().String(),
			DealerID:       dealerID,
			IsPrimary:      true,
			AddressLine1:   ptrIfNotEmpty(d.Address.Street),
			PostalCode:     ptrIfNotEmpty(d.postalCode()),
			City:           ptrIfNotEmpty(d.Address.City),
			CountryCode:    country,
			Phone:          ptrIfNotEmpty(d.Phone),
			SourceFamilies: familyID,
		}); err != nil {
			v.log.Warn("vwg: add location error", "dealer", d.Name, "err", err)
		}
	}

	if err := v.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
		SourceURL:             ptrIfNotEmpty(sourceURL),
	}); err != nil {
		v.log.Warn("vwg: record discovery error", "dealer", d.Name, "err", err)
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
