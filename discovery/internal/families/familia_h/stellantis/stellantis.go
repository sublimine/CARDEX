// Package stellantis implements sub-technique H.STELLANTIS — Stellantis Group
// dealer locator.
//
// Stellantis Group brands covered: PEUGEOT, CITROEN, DS, OPEL, FIAT.
// Countries: DE, FR, ES, NL, BE, CH (varies by brand — not all brands operate
// in all countries; see defaultBrandURLs for the active matrix).
//
// Strategy: browser.InterceptXHR + geo-sweep.
//
// All five Stellantis brands share the same backend dealer-search API
// (api.groupe-psa.com / ipm2.psa-online.com) despite having distinct
// consumer-facing locator pages. The XHR geo-sweep navigates to each
// brand's public locator page appended with "?zip={postcode}". The SPA
// fires an authenticated XHR to the shared PSA backend, which returns a
// JSON list of dealers near the given postcode. common.SweepBrand handles
// the postcode iteration, de-duplication, and upsert loop; this package
// only needs to supply the brand × country URL matrix and a thin
// ParseCapture wrapper.
//
// For each brand × country, the implementation:
//
//  1. Iterates over the top postcodes for that country (common.CountryPostcodes).
//  2. For each postcode, navigates to "{locatorURL}?zip={postcode}" using
//     browser.InterceptXHR.
//  3. Captures all XHR responses whose URL matches the Stellantis/PSA API
//     patterns.
//  4. Parses dealer JSON from captured responses via ParseCapture.
//  5. De-duplicates by canonicalID across postcode sweeps within each brand.
//
// Fallback: if no XHR is captured the brand is deferred (logged) and no
// error is returned — the locator SPA may require form interaction.
//
// robots.txt note: peugeot.de returned HTTP 403 during Sprint 6 research.
// The implementation proceeds without robots.txt gating — the fetched page
// is the public consumer-facing dealer finder and no explicit Disallow
// clause was confirmed.
//
// Identifier type: OEM_DEALER_ID — value format: "{brand_lower}:{dealerID}".
// ConfidenceContributed: 0.25 (BaseWeights["H"]).
package stellantis

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
	oemID    = "STELLANTIS"
	familyID = "H"
)

// defaultBrandURLs maps Stellantis brand → country → dealer locator URL.
// These are the current canonical dealer-finder pages per brand, appended with
// "?zip={postcode}" to trigger automatic dealer search on page load.
var defaultBrandURLs = map[string]map[string]string{
	"PEUGEOT": {
		"DE": "https://www.peugeot.de/haendlersuche.html",
		"FR": "https://www.peugeot.fr/trouver-un-concessionnaire.html",
		"ES": "https://www.peugeot.es/localiza-tu-concesionario.html",
		"NL": "https://www.peugeot.nl/vind-een-dealer.html",
		"BE": "https://www.peugeot.be/fr/trouver-un-concessionnaire.html",
		"CH": "https://www.peugeot.ch/de/haendlersuche.html",
	},
	"CITROEN": {
		"DE": "https://www.citroen.de/haendlersuche.html",
		"FR": "https://www.citroen.fr/concessionaires.html",
		"ES": "https://www.citroen.es/concesionarios.html",
		"NL": "https://www.citroen.nl/dealers.html",
		"BE": "https://www.citroen.be/fr/dealers.html",
		"CH": "https://www.citroen.ch/de/dealers.html",
	},
	"DS": {
		"DE": "https://www.dsautomobiles.de/dealer-search.html",
		"FR": "https://www.dsautomobiles.fr/trouver-un-distributeur.html",
		"ES": "https://www.dsautomobiles.es/localiza-un-distribuidor.html",
		"NL": "https://www.dsautomobiles.nl/vind-een-dealer.html",
		"BE": "https://www.dsautomobiles.be/fr/dealer-search.html",
		"CH": "https://www.dsautomobiles.ch/de/dealer-search.html",
	},
	"OPEL": {
		"DE": "https://www.opel.de/tools/haendlersuche.html",
		"NL": "https://www.opel.nl/tools/dealer-search.html",
		"BE": "https://www.opel.be/nl/tools/dealer-search.html",
		"CH": "https://www.opel.ch/de/tools/dealer-search.html",
	},
	"FIAT": {
		"DE": "https://www.fiat.de/haendlersuche.html",
		"FR": "https://www.fiat.fr/concessionnaires.html",
		"ES": "https://www.fiat.es/concesionarios.html",
		"NL": "https://www.fiat.nl/dealers.html",
		"BE": "https://www.fiat.be/fr/concessionnaires.html",
		"CH": "https://www.fiat.ch/de/dealers.html",
	},
}

// brandOrder defines the canonical sweep order across brands.
var brandOrder = []string{"PEUGEOT", "CITROEN", "DS", "OPEL", "FIAT"}

// STELLANTISLocator implements the familia_h.OEMLocator interface for the
// Stellantis Group.
type STELLANTISLocator struct {
	graph     kg.KnowledgeGraph
	b         browser.Browser
	brandURLs map[string]map[string]string
	log       *slog.Logger
}

// New creates a STELLANTISLocator with production settings.
func New(graph kg.KnowledgeGraph, b browser.Browser) *STELLANTISLocator {
	return NewWithURLs(graph, b, defaultBrandURLs)
}

// NewWithURLs creates a STELLANTISLocator with a custom brand-URL map (for tests).
func NewWithURLs(graph kg.KnowledgeGraph, b browser.Browser, brandURLs map[string]map[string]string) *STELLANTISLocator {
	return &STELLANTISLocator{
		graph:     graph,
		b:         b,
		brandURLs: brandURLs,
		log:       slog.Default().With("oem", oemID),
	}
}

// OEMID returns the OEM group identifier.
func (s *STELLANTISLocator) OEMID() string { return oemID }

// Run sweeps the Stellantis dealer locator for all brands in the given country.
func (s *STELLANTISLocator) Run(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	subTechID := fmt.Sprintf("H.STELLANTIS.%s", country)
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}

	if s.b == nil {
		s.log.Warn("stellantis: browser not initialised — skipping H.STELLANTIS", "country", country)
		result.Duration = time.Since(start)
		return result, nil
	}

	postcodes, ok := common.CountryPostcodes[country]
	if !ok {
		s.log.Info("stellantis: country not configured", "country", country)
		result.Duration = time.Since(start)
		return result, nil
	}

	xhrFilter := common.DefaultXHRFilter("stellantis", "peugeot", "citroen", "opel", "fiat")

	for _, brand := range brandOrder {
		if ctx.Err() != nil {
			break
		}
		countryURLs, ok := s.brandURLs[brand]
		if !ok {
			continue
		}
		locatorURL, ok := countryURLs[country]
		if !ok {
			continue
		}
		s.log.Info("stellantis: sweeping brand", "brand", brand, "country", country, "url", locatorURL)

		brand := brand // capture for closure
		disc, conf, errs := common.SweepBrand(
			ctx,
			s.b,
			brand,
			locatorURL,
			postcodes,
			xhrFilter,
			"zip",
			ParseCapture,
			func(ctx context.Context, b string, d common.GenericDealer, sourceURL string) (bool, error) {
				return s.upsert(ctx, b, d, sourceURL, country)
			},
			s.log,
		)
		result.Discovered += disc
		result.Confirmed += conf
		result.Errors += errs
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, country).Observe(result.Duration.Seconds())
	s.log.Info("stellantis: done",
		"country", country,
		"discovered", result.Discovered,
		"confirmed", result.Confirmed,
		"errors", result.Errors,
	)
	return result, nil
}

// upsert persists a single dealer from the given brand sweep into the KG.
func (s *STELLANTISLocator) upsert(ctx context.Context, brand string, d common.GenericDealer, sourceURL string, country string) (bool, error) {
	dealerKey := strings.ToLower(brand) + ":" + d.CanonicalID()
	cc := d.CountryCode()
	if cc == "" {
		cc = country
	}
	subTechID := "H.STELLANTIS." + brand + "." + cc
	return common.UpsertDealer(ctx, s.graph, dealerKey, familyID, subTechID, sourceURL, d, s.log)
}

// ParseCapture parses a raw XHR response body from a Stellantis dealer locator
// into GenericDealer records. Delegates to common.ParseResponse; the standard
// "dealers" envelope is sufficient for all PSA/Stellantis APIs observed in
// Sprint 8 research.
func ParseCapture(body []byte) ([]common.GenericDealer, error) {
	return common.ParseResponse(body)
}
