// Package renault implements sub-technique H.RENAULT — Renault Group dealer
// locator.
//
// Renault Group brands covered: RENAULT, DACIA, ALPINE.
// Countries: DE, FR, ES, NL, BE, CH (varies by brand — Alpine does not
// operate in BE or CH; see defaultBrandURLs for the active matrix).
//
// Strategy: browser.InterceptXHR + geo-sweep.
//
// Renault Group dealer locator sites are JavaScript SPAs. Each brand fires
// XHR calls to a JSON dealer-search API when the page renders. The geo-sweep
// navigates to "{locatorURL}?zip={postcode}" which is sufficient to trigger
// the search on load for all three brands.
//
// robots.txt constraint: Renault robots.txt explicitly contains
// "Disallow: *dealerId=*". The geo-sweep therefore uses the "zip" postcode
// parameter exclusively — "?zip={postcode}" — which is not blocked by that
// rule. Do NOT switch to "dealerId" or any parameter containing that string.
//
// Alpine is a low-volume brand with fewer dealers; BE and CH have no Alpine
// locator URL and are deferred. XHR captures dealer-search API responses.
//
// For each brand × country, the implementation:
//
//  1. Iterates over the top postcodes for that country (common.CountryPostcodes).
//  2. For each postcode, navigates to "{locatorURL}?zip={postcode}" using
//     browser.InterceptXHR.
//  3. Captures all XHR responses whose URL matches the Renault/Dacia/Alpine
//     API patterns.
//  4. Parses dealer JSON from captured responses via ParseCapture.
//  5. De-duplicates by canonicalID across postcode sweeps within each brand.
//
// Identifier type: OEM_DEALER_ID — value format: "{brand_lower}:{dealerID}".
// ConfidenceContributed: 0.25 (BaseWeights["H"]).
package renault

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
	oemID    = "RENAULT"
	familyID = "H"
)

// defaultBrandURLs maps Renault Group brand → country → dealer locator URL.
// These are the current canonical dealer-finder pages per brand, appended with
// "?zip={postcode}" to trigger automatic dealer search on page load.
//
// NOTE: Renault robots.txt blocks *dealerId=* — the geo-sweep uses ?zip=
// which is not blocked.
//
// Alpine BE and CH are omitted: Alpine has no official dealer locator page
// for those markets as of Sprint 9 research. Deferred to a future sprint.
var defaultBrandURLs = map[string]map[string]string{
	"RENAULT": {
		"DE": "https://www.renault.de/haendler-und-service.html",
		"FR": "https://www.renault.fr/concessionnaires.html",
		"ES": "https://www.renault.es/concesionarios.html",
		"NL": "https://www.renault.nl/dealers.html",
		"BE": "https://www.renault.be/nl/dealers.html",
		"CH": "https://www.renault.ch/de/haendler.html",
	},
	"DACIA": {
		"DE": "https://www.dacia.de/haendler-und-service.html",
		"FR": "https://www.dacia.fr/concessionnaires.html",
		"ES": "https://www.dacia.es/concesionarios.html",
		"NL": "https://www.dacia.nl/dealers.html",
		"BE": "https://www.dacia.be/nl/dealers.html",
		"CH": "https://www.dacia.ch/de/haendler.html",
	},
	"ALPINE": {
		"DE": "https://www.alpinecars.de/handler.html",
		"FR": "https://www.alpinecars.fr/distributeurs.html",
		"ES": "https://www.alpinecars.es/distribuidores.html",
		"NL": "https://www.alpinecars.nl/dealers.html",
		"CH": "https://www.alpinecars.ch/de/handlers.html",
	},
}

// brandOrder defines the canonical sweep order across Renault Group brands.
var brandOrder = []string{"RENAULT", "DACIA", "ALPINE"}

// RENAULTLocator implements the familia_h.OEMLocator interface for the
// Renault Group.
type RENAULTLocator struct {
	graph     kg.KnowledgeGraph
	b         browser.Browser
	brandURLs map[string]map[string]string
	log       *slog.Logger
}

// New creates a RENAULTLocator with production settings.
func New(graph kg.KnowledgeGraph, b browser.Browser) *RENAULTLocator {
	return NewWithURLs(graph, b, defaultBrandURLs)
}

// NewWithURLs creates a RENAULTLocator with a custom brand-URL map (for tests).
func NewWithURLs(graph kg.KnowledgeGraph, b browser.Browser, brandURLs map[string]map[string]string) *RENAULTLocator {
	return &RENAULTLocator{
		graph:     graph,
		b:         b,
		brandURLs: brandURLs,
		log:       slog.Default().With("oem", oemID),
	}
}

// OEMID returns the OEM group identifier.
func (r *RENAULTLocator) OEMID() string { return oemID }

// Run sweeps the Renault Group dealer locator for all brands in the given
// country.
func (r *RENAULTLocator) Run(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	subTechID := fmt.Sprintf("H.RENAULT.%s", country)
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}

	if r.b == nil {
		r.log.Warn("renault: browser not initialised — skipping H.RENAULT", "country", country)
		result.Duration = time.Since(start)
		return result, nil
	}

	postcodes, ok := common.CountryPostcodes[country]
	if !ok {
		r.log.Info("renault: country not configured", "country", country)
		result.Duration = time.Since(start)
		return result, nil
	}

	// IMPORTANT: postcodeParam must be "zip", never "dealerId" — Renault
	// robots.txt explicitly disallows *dealerId=* query parameters.
	xhrFilter := common.DefaultXHRFilter("renault|dacia|alpine|rci")

	for _, brand := range brandOrder {
		if ctx.Err() != nil {
			break
		}
		countryURLs, ok := r.brandURLs[brand]
		if !ok {
			continue
		}
		locatorURL, ok := countryURLs[country]
		if !ok {
			continue
		}
		r.log.Info("renault: sweeping brand", "brand", brand, "country", country, "url", locatorURL)

		brand := brand // capture for closure
		disc, conf, errs := common.SweepBrand(
			ctx,
			r.b,
			brand,
			locatorURL,
			postcodes,
			xhrFilter,
			"zip",
			ParseCapture,
			func(ctx context.Context, b string, d common.GenericDealer, sourceURL string) (bool, error) {
				return r.upsert(ctx, b, d, sourceURL, country)
			},
			r.log,
		)
		result.Discovered += disc
		result.Confirmed += conf
		result.Errors += errs
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, country).Observe(result.Duration.Seconds())
	r.log.Info("renault: done",
		"country", country,
		"discovered", result.Discovered,
		"confirmed", result.Confirmed,
		"errors", result.Errors,
	)
	return result, nil
}

// upsert persists a single dealer from the given brand sweep into the KG.
func (r *RENAULTLocator) upsert(ctx context.Context, brand string, d common.GenericDealer, sourceURL string, country string) (bool, error) {
	dealerKey := strings.ToLower(brand) + ":" + d.CanonicalID()
	cc := d.CountryCode()
	if cc == "" {
		cc = country
	}
	subTechID := "H.RENAULT." + brand + "." + cc
	return common.UpsertDealer(ctx, r.graph, dealerKey, familyID, subTechID, sourceURL, d, r.log)
}

// ParseCapture parses a raw XHR response body from a Renault Group dealer
// locator into GenericDealer records. Passes "dealerships" as an extra
// envelope key in addition to the standard ones, since Renault's API uses
// that envelope name.
func ParseCapture(body []byte) ([]common.GenericDealer, error) {
	return common.ParseResponse(body, "dealerships")
}
