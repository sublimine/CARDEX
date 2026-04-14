// Package bmw implements sub-technique H.BMW — BMW Group dealer locator.
//
// BMW Group brands covered: BMW, MINI.
// Countries: DE, FR, ES, NL, BE, CH.
//
// Strategy: browser.InterceptXHR + geo-sweep.
//
// BMW Group uses aggressive anti-bot protection (DDoS-Guard / Imperva layer)
// on its dealer-locator pages. browser.InterceptXHR with Playwright's
// fingerprint-clean Chromium is required — static HTTP fetchers are rejected
// with 403 or served a CAPTCHA challenge page. The XHR geo-sweep navigates to
// the dealer-locator page appended with "?zip={postcode}"; the React/Backbone
// SPA fires an API call that returns nearby dealer JSON.
//
// robots.txt note: bmw.de robots.txt consistently timed out during Sprint 6
// research (DDoS protection blocking automated robots.txt fetches). No
// explicit Disallow rule covering the dealer-locator path was confirmed.
// MINI uses the same infrastructure pattern.
//
// BMW dealer locators are React/Backbone SPAs. The underlying dealer-search
// API is consistent across BMW and MINI brands (api.bmw.com /
// retailerlocator.bmw.com); XHR interception captures the API response
// directly, avoiding any form interaction requirement for the initial load.
//
// For each brand × country, the implementation:
//
//  1. Iterates over the top postcodes for that country (common.CountryPostcodes).
//  2. For each postcode, navigates to "{locatorURL}?zip={postcode}" using
//     browser.InterceptXHR.
//  3. Captures all XHR responses whose URL matches the BMW retailer-locator
//     API patterns.
//  4. Parses dealer JSON from captured responses via ParseCapture.
//  5. De-duplicates by canonicalID across postcode sweeps within each brand.
//
// Identifier type: OEM_DEALER_ID — value format: "{brand_lower}:{dealerID}".
// ConfidenceContributed: 0.25 (BaseWeights["H"]).
package bmw

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
	oemID    = "BMW"
	familyID = "H"
)

// defaultBrandURLs maps BMW Group brand → country → dealer locator URL.
// These are the current canonical dealer-finder pages per brand, appended with
// "?zip={postcode}" to trigger automatic dealer search on page load.
var defaultBrandURLs = map[string]map[string]string{
	"BMW": {
		"DE": "https://www.bmw.de/de/dealer-locator.html",
		"FR": "https://www.bmw.fr/fr/dealer-locator.html",
		"ES": "https://www.bmw.es/es/dealer-locator.html",
		"NL": "https://www.bmw.nl/nl/dealer-locator.html",
		"BE": "https://www.bmw.be/nl/dealer-locator.html",
		"CH": "https://www.bmw.ch/de/dealer-locator.html",
	},
	"MINI": {
		"DE": "https://www.mini.de/de/dealer-locator.html",
		"FR": "https://www.mini.fr/fr/dealer-locator.html",
		"ES": "https://www.mini.es/es/dealer-locator.html",
		"NL": "https://www.mini.nl/nl/dealer-locator.html",
		"BE": "https://www.mini.be/nl/dealer-locator.html",
		"CH": "https://www.mini.ch/de/dealer-locator.html",
	},
}

// brandOrder defines the canonical sweep order across brands.
var brandOrder = []string{"BMW", "MINI"}

// BMWLocator implements the familia_h.OEMLocator interface for the BMW Group.
type BMWLocator struct {
	graph     kg.KnowledgeGraph
	b         browser.Browser
	brandURLs map[string]map[string]string
	log       *slog.Logger
}

// New creates a BMWLocator with production settings.
func New(graph kg.KnowledgeGraph, b browser.Browser) *BMWLocator {
	return NewWithURLs(graph, b, defaultBrandURLs)
}

// NewWithURLs creates a BMWLocator with a custom brand-URL map (for tests).
func NewWithURLs(graph kg.KnowledgeGraph, b browser.Browser, brandURLs map[string]map[string]string) *BMWLocator {
	return &BMWLocator{
		graph:     graph,
		b:         b,
		brandURLs: brandURLs,
		log:       slog.Default().With("oem", oemID),
	}
}

// OEMID returns the OEM group identifier.
func (bw *BMWLocator) OEMID() string { return oemID }

// Run sweeps the BMW Group dealer locator for all brands in the given country.
func (bw *BMWLocator) Run(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	subTechID := fmt.Sprintf("H.BMW.%s", country)
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}

	if bw.b == nil {
		bw.log.Warn("bmw: browser not initialised — skipping H.BMW", "country", country)
		result.Duration = time.Since(start)
		return result, nil
	}

	postcodes, ok := common.CountryPostcodes[country]
	if !ok {
		bw.log.Info("bmw: country not configured", "country", country)
		result.Duration = time.Since(start)
		return result, nil
	}

	xhrFilter := common.DefaultXHRFilter("bmw", "mini", "retailer")

	for _, brand := range brandOrder {
		if ctx.Err() != nil {
			break
		}
		countryURLs, ok := bw.brandURLs[brand]
		if !ok {
			continue
		}
		locatorURL, ok := countryURLs[country]
		if !ok {
			continue
		}
		bw.log.Info("bmw: sweeping brand", "brand", brand, "country", country, "url", locatorURL)

		brand := brand // capture for closure
		disc, conf, errs := common.SweepBrand(
			ctx,
			bw.b,
			brand,
			locatorURL,
			postcodes,
			xhrFilter,
			"zip",
			ParseCapture,
			func(ctx context.Context, b string, d common.GenericDealer, sourceURL string) (bool, error) {
				return bw.upsert(ctx, b, d, sourceURL, country)
			},
			bw.log,
		)
		result.Discovered += disc
		result.Confirmed += conf
		result.Errors += errs
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, country).Observe(result.Duration.Seconds())
	bw.log.Info("bmw: done",
		"country", country,
		"discovered", result.Discovered,
		"confirmed", result.Confirmed,
		"errors", result.Errors,
	)
	return result, nil
}

// upsert persists a single dealer from the given brand sweep into the KG.
func (bw *BMWLocator) upsert(ctx context.Context, brand string, d common.GenericDealer, sourceURL string, country string) (bool, error) {
	dealerKey := strings.ToLower(brand) + ":" + d.CanonicalID()
	cc := d.CountryCode()
	if cc == "" {
		cc = country
	}
	subTechID := "H.BMW." + brand + "." + cc
	return common.UpsertDealer(ctx, bw.graph, dealerKey, familyID, subTechID, sourceURL, d, bw.log)
}

// ParseCapture parses a raw XHR response body from a BMW Group dealer locator
// into GenericDealer records. Delegates to common.ParseResponse; the standard
// "dealers" envelope is sufficient for all BMW/MINI retailer-locator APIs
// observed in Sprint 8 research.
func ParseCapture(body []byte) ([]common.GenericDealer, error) {
	return common.ParseResponse(body)
}
