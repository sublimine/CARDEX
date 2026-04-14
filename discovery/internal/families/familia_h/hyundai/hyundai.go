// Package hyundai implements sub-technique H.HYUNDAI — Hyundai / Kia dealer locator.
//
// Hyundai DE had TLS certificate error on robots.txt in Sprint 6. The browser
// module handles TLS errors gracefully (Playwright ignores cert errors).
// Hyundai and Kia share corporate ownership (Hyundai Motor Group) but operate
// separate dealer networks with independent locator sites.
//
// Brands covered: HYUNDAI, KIA.
// Countries: DE, FR, ES, NL, BE, CH.
//
// Strategy: browser.InterceptXHR + geo-sweep using common.SweepBrand.
//
// For each brand × country the implementation:
//
//  1. Iterates over the top postcodes for that country (common.CountryPostcodes).
//  2. For each postcode, navigates to "{locatorURL}?zip={postcode}" via
//     browser.InterceptXHR.
//  3. Captures XHR responses matching hyundai/kia/hmc URL patterns.
//  4. Parses dealer JSON from captured responses (standard envelopes).
//  5. De-duplicates by dealer ID across postcode sweeps.
//
// Identifier type: OEM_DEALER_ID — value format: "hyundai:{dealerID}" or "kia:{dealerID}".
// ConfidenceContributed: 0.25 (BaseWeights["H"]).
package hyundai

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
	oemID    = "HYUNDAI"
	familyID = "H"
)

// defaultBrandURLs maps Hyundai Motor Group brand → country → dealer locator URL.
var defaultBrandURLs = map[string]map[string]string{
	"HYUNDAI": {
		"DE": "https://www.hyundai.de/haendlersuche",
		"FR": "https://www.hyundai.fr/recherche-concessionnaire",
		"ES": "https://www.hyundai.es/buscar-concesionario",
		"NL": "https://www.hyundai.nl/dealers",
		"BE": "https://www.hyundai.be/nl/dealers",
		"CH": "https://www.hyundai.ch/de/haendlersuche",
	},
	"KIA": {
		"DE": "https://www.kia.com/de/services/find-a-dealer.html",
		"FR": "https://www.kia.com/fr/services/trouver-un-concessionnaire.html",
		"ES": "https://www.kia.com/es/services/buscar-concesionario.html",
		"NL": "https://www.kia.com/nl/services/vind-een-dealer.html",
		"BE": "https://www.kia.com/be-nl/services/vind-een-dealer.html",
		"CH": "https://www.kia.com/ch-de/services/haendler-finden.html",
	},
}

// HyundaiLocator implements the familia_h.OEMLocator interface for Hyundai Motor Group.
type HyundaiLocator struct {
	graph     kg.KnowledgeGraph
	b         browser.Browser
	brandURLs map[string]map[string]string
	log       *slog.Logger
}

// New creates a HyundaiLocator with production settings.
func New(graph kg.KnowledgeGraph, b browser.Browser) *HyundaiLocator {
	return NewWithURLs(graph, b, defaultBrandURLs)
}

// NewWithURLs creates a HyundaiLocator with a custom brand-URL map (for tests).
func NewWithURLs(graph kg.KnowledgeGraph, b browser.Browser, brandURLs map[string]map[string]string) *HyundaiLocator {
	return &HyundaiLocator{
		graph:     graph,
		b:         b,
		brandURLs: brandURLs,
		log:       slog.Default().With("oem", oemID),
	}
}

// OEMID returns the OEM identifier.
func (l *HyundaiLocator) OEMID() string { return oemID }

// Run sweeps the Hyundai / Kia dealer locator for the given country.
func (l *HyundaiLocator) Run(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	subTechID := fmt.Sprintf("H.HYUNDAI.%s", country)
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}

	if l.b == nil {
		l.log.Warn("hyundai: browser not initialised — skipping", "country", country)
		result.Duration = time.Since(start)
		return result, nil
	}

	postcodes, ok := common.CountryPostcodes[country]
	if !ok {
		l.log.Info("hyundai: country not configured", "country", country)
		result.Duration = time.Since(start)
		return result, nil
	}

	brands := []string{"HYUNDAI", "KIA"}
	filter := common.DefaultXHRFilter("hyundai", "kia", "hmc")

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

		l.log.Info("hyundai: sweeping brand", "brand", brand, "country", country)
		disc, conf, errs := common.SweepBrand(ctx, l.b, brand, locatorURL,
			postcodes, filter, "zip", ParseCapture, l.upsert, l.log)
		result.Discovered += disc
		result.Confirmed += conf
		result.Errors += errs
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, country).Observe(result.Duration.Seconds())
	l.log.Info("hyundai: done", "country", country, "discovered", result.Discovered)
	return result, nil
}

// upsert persists a single GenericDealer to the knowledge graph.
func (l *HyundaiLocator) upsert(ctx context.Context, brand string, d common.GenericDealer, sourceURL string) (bool, error) {
	dealerKey := strings.ToLower(brand) + ":" + d.CanonicalID()
	country := d.CountryCode()
	subTechID := fmt.Sprintf("H.HYUNDAI.%s.%s", brand, country)
	return common.UpsertDealer(ctx, l.graph, dealerKey, familyID, subTechID, sourceURL, d, l.log)
}

// ParseCapture extracts GenericDealer records from a raw Hyundai/Kia XHR response.
func ParseCapture(body []byte) ([]common.GenericDealer, error) {
	return common.ParseResponse(body)
}
