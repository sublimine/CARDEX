// Package ford implements sub-technique H.FORD — Ford dealer locator.
//
// Ford brands covered: FORD (single brand).
// Countries: DE, FR, ES, NL, BE, CH.
//
// Strategy: browser.InterceptXHR + geo-sweep.
//
// Ford dealer locator consistently timed out during Sprint 6 research
// (CDN / bot-protection). The browser.InterceptXHR approach using
// Playwright's headless Chromium should bypass CDN challenges that block
// plain HTTP requests. XHR geo-sweep navigates to
// "{locatorURL}?zip={postcode}" and captures dealer JSON responses.
//
// If Cloudflare or similar bot protection requires CAPTCHA resolution,
// individual country combinations are deferred — the adapter logs a
// per-postcode warning and continues.
//
// For each brand × country, the implementation:
//
//  1. Iterates over the top postcodes for that country (common.CountryPostcodes).
//  2. For each postcode, navigates to "{locatorURL}?zip={postcode}" using
//     browser.InterceptXHR.
//  3. Captures all XHR responses whose URL matches the Ford/dealer-search
//     API patterns.
//  4. Parses dealer JSON from captured responses via ParseCapture.
//  5. De-duplicates by canonicalID across postcode sweeps.
//
// Identifier type: OEM_DEALER_ID — value format: "{brand_lower}:{dealerID}".
// ConfidenceContributed: 0.25 (BaseWeights["H"]).
package ford

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
	oemID    = "FORD"
	familyID = "H"
)

// defaultBrandURLs maps Ford brand → country → dealer locator URL.
// These are the current canonical dealer-finder pages, appended with
// "?zip={postcode}" to trigger automatic dealer search on page load.
var defaultBrandURLs = map[string]map[string]string{
	"FORD": {
		"DE": "https://www.ford.de/haendlersuche",
		"FR": "https://www.ford.fr/trouver-un-concessionnaire",
		"ES": "https://www.ford.es/buscar-concesionario",
		"NL": "https://www.ford.nl/dealer-zoeken",
		"BE": "https://www.ford.be/nl/dealer-zoeken",
		"CH": "https://www.ford.ch/de/haendlersuche",
	},
}

// brandOrder defines the canonical sweep order. Ford is a single-brand OEM.
var brandOrder = []string{"FORD"}

// FORDLocator implements the familia_h.OEMLocator interface for Ford.
type FORDLocator struct {
	graph     kg.KnowledgeGraph
	b         browser.Browser
	brandURLs map[string]map[string]string
	log       *slog.Logger
}

// New creates a FORDLocator with production settings.
func New(graph kg.KnowledgeGraph, b browser.Browser) *FORDLocator {
	return NewWithURLs(graph, b, defaultBrandURLs)
}

// NewWithURLs creates a FORDLocator with a custom brand-URL map (for tests).
func NewWithURLs(graph kg.KnowledgeGraph, b browser.Browser, brandURLs map[string]map[string]string) *FORDLocator {
	return &FORDLocator{
		graph:     graph,
		b:         b,
		brandURLs: brandURLs,
		log:       slog.Default().With("oem", oemID),
	}
}

// OEMID returns the OEM group identifier.
func (f *FORDLocator) OEMID() string { return oemID }

// Run sweeps the Ford dealer locator for the given country.
func (f *FORDLocator) Run(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	subTechID := fmt.Sprintf("H.FORD.%s", country)
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}

	if f.b == nil {
		f.log.Warn("ford: browser not initialised — skipping H.FORD", "country", country)
		result.Duration = time.Since(start)
		return result, nil
	}

	postcodes, ok := common.CountryPostcodes[country]
	if !ok {
		f.log.Info("ford: country not configured", "country", country)
		result.Duration = time.Since(start)
		return result, nil
	}

	xhrFilter := common.DefaultXHRFilter("ford|dealer-search|dealer-locator|fdl")

	for _, brand := range brandOrder {
		if ctx.Err() != nil {
			break
		}
		countryURLs, ok := f.brandURLs[brand]
		if !ok {
			continue
		}
		locatorURL, ok := countryURLs[country]
		if !ok {
			continue
		}
		f.log.Info("ford: sweeping brand", "brand", brand, "country", country, "url", locatorURL)

		brand := brand // capture for closure
		disc, conf, errs := common.SweepBrand(
			ctx,
			f.b,
			brand,
			locatorURL,
			postcodes,
			xhrFilter,
			"zip",
			ParseCapture,
			func(ctx context.Context, b string, d common.GenericDealer, sourceURL string) (bool, error) {
				return f.upsert(ctx, b, d, sourceURL, country)
			},
			f.log,
		)
		result.Discovered += disc
		result.Confirmed += conf
		result.Errors += errs
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, country).Observe(result.Duration.Seconds())
	f.log.Info("ford: done",
		"country", country,
		"discovered", result.Discovered,
		"confirmed", result.Confirmed,
		"errors", result.Errors,
	)
	return result, nil
}

// upsert persists a single dealer from the given brand sweep into the KG.
func (f *FORDLocator) upsert(ctx context.Context, brand string, d common.GenericDealer, sourceURL string, country string) (bool, error) {
	dealerKey := strings.ToLower(brand) + ":" + d.CanonicalID()
	cc := d.CountryCode()
	if cc == "" {
		cc = country
	}
	subTechID := "H.FORD." + brand + "." + cc
	return common.UpsertDealer(ctx, f.graph, dealerKey, familyID, subTechID, sourceURL, d, f.log)
}

// ParseCapture parses a raw XHR response body from a Ford dealer locator into
// GenericDealer records. Delegates to common.ParseResponse with the standard
// envelope keys (dealers, results, data, items, etc.).
func ParseCapture(body []byte) ([]common.GenericDealer, error) {
	return common.ParseResponse(body)
}
