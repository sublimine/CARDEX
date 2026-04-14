// Package mercedes implements sub-technique H.MERCEDES — Mercedes-Benz dealer locator.
//
// Mercedes-Benz dealer locator is a React SPA with DDoS protection
// (mercedes-benz.de robots.txt timed out in Sprint 6). browser.InterceptXHR
// captures the backend dealer-search API responses. The API typically returns
// a "dealerships" envelope.
//
// Countries covered: DE, FR, ES, NL, BE, CH.
//
// Strategy: browser.InterceptXHR + geo-sweep using common.SweepBrand.
//
// For each country the implementation:
//
//  1. Iterates over the top postcodes for that country (common.CountryPostcodes).
//  2. For each postcode, navigates to "{locatorURL}?zip={postcode}" via
//     browser.InterceptXHR.
//  3. Captures XHR responses matching mercedes/mb/retailer/outlet URL patterns.
//  4. Parses dealer JSON from captured responses (dealerships envelope).
//  5. De-duplicates by dealer ID across postcode sweeps.
//
// Identifier type: OEM_DEALER_ID — value format: "mercedes:{dealerID}".
// ConfidenceContributed: 0.25 (BaseWeights["H"]).
package mercedes

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"cardex.eu/discovery/internal/browser"
	"cardex.eu/discovery/internal/families/familia_h/common"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	oemID    = "MERCEDES"
	familyID = "H"
)

// defaultBrandURLs maps Mercedes-Benz brand → country → dealer locator URL.
var defaultBrandURLs = map[string]map[string]string{
	"MERCEDES": {
		"DE": "https://www.mercedes-benz.de/passengercars/mercedes-benz-cars/dealer-search.html",
		"FR": "https://www.mercedes-benz.fr/voitures-particulieres/dealer-search.html",
		"ES": "https://www.mercedes-benz.es/coches-particulares/dealer-search.html",
		"NL": "https://www.mercedes-benz.nl/personenwagens/dealer-search.html",
		"BE": "https://www.mercedes-benz.be/nl/personenwagens/dealer-search.html",
		"CH": "https://www.mercedes-benz.ch/de/personenwagen/dealer-search.html",
	},
}

// MercedesLocator implements the familia_h.OEMLocator interface for Mercedes-Benz.
type MercedesLocator struct {
	graph     kg.KnowledgeGraph
	b         browser.Browser
	brandURLs map[string]map[string]string
	log       *slog.Logger
}

// New creates a MercedesLocator with production settings.
func New(graph kg.KnowledgeGraph, b browser.Browser) *MercedesLocator {
	return NewWithURLs(graph, b, defaultBrandURLs)
}

// NewWithURLs creates a MercedesLocator with a custom brand-URL map (for tests).
func NewWithURLs(graph kg.KnowledgeGraph, b browser.Browser, brandURLs map[string]map[string]string) *MercedesLocator {
	return &MercedesLocator{
		graph:     graph,
		b:         b,
		brandURLs: brandURLs,
		log:       slog.Default().With("oem", oemID),
	}
}

// OEMID returns the OEM identifier.
func (l *MercedesLocator) OEMID() string { return oemID }

// Run sweeps the Mercedes-Benz dealer locator for the given country.
func (l *MercedesLocator) Run(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	subTechID := fmt.Sprintf("H.MERCEDES.%s", country)
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}

	if l.b == nil {
		l.log.Warn("mercedes: browser not initialised — skipping", "country", country)
		result.Duration = time.Since(start)
		return result, nil
	}

	postcodes, ok := common.CountryPostcodes[country]
	if !ok {
		l.log.Info("mercedes: country not configured", "country", country)
		result.Duration = time.Since(start)
		return result, nil
	}

	brands := []string{"MERCEDES"}
	filter := common.DefaultXHRFilter("mercedes", "mb", "retailer", "outlet")

	for _, brand := range brands {
		if ctx.Err() != nil {
			break
		}
		countryURLs, ok := l.brandURLs[brand]
		if !ok {
			continue
		}
		locatorURL, ok := countryURLs[country]
		if !ok {
			continue
		}

		l.log.Info("mercedes: sweeping brand", "brand", brand, "country", country)
		disc, conf, errs := common.SweepBrand(ctx, l.b, brand, locatorURL,
			postcodes, filter, "zip", ParseCapture, l.upsert, l.log)
		result.Discovered += disc
		result.Confirmed += conf
		result.Errors += errs
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, country).Observe(result.Duration.Seconds())
	l.log.Info("mercedes: done", "country", country, "discovered", result.Discovered)
	return result, nil
}

// upsert persists a single GenericDealer to the knowledge graph.
func (l *MercedesLocator) upsert(ctx context.Context, brand string, d common.GenericDealer, sourceURL string) (bool, error) {
	dealerKey := strings.ToLower(brand) + ":" + d.CanonicalID()
	country := d.CountryCode()
	subTechID := fmt.Sprintf("H.MERCEDES.%s.%s", brand, country)
	return common.UpsertDealer(ctx, l.graph, dealerKey, familyID, subTechID, sourceURL, d, l.log)
}

// ParseCapture extracts GenericDealer records from a raw Mercedes XHR response.
// Mercedes wraps dealer records in a "dealerships" envelope.
func ParseCapture(body []byte) ([]common.GenericDealer, error) {
	return common.ParseResponse(body, "dealerships")
}
