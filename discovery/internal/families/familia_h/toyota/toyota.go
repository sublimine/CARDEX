// Package toyota implements sub-technique H.TOYOTA — Toyota / Lexus dealer locator.
//
// Toyota robots.txt (toyota.de) explicitly blocks `*?dealer=*` and
// `*?dealerId=*` query parameters. The geo-sweep uses `?zip={postcode}` which
// is not blocked. Toyota sometimes nests dealer data in a `result.dealers`
// structure; ParseCapture handles both the nested and flat response formats.
//
// Brands covered: TOYOTA, LEXUS.
// Countries: DE, FR, ES, NL, BE, CH.
//
// Strategy: browser.InterceptXHR + geo-sweep using common.SweepBrand.
//
// For each brand × country the implementation:
//
//  1. Iterates over the top postcodes for that country (common.CountryPostcodes).
//  2. For each postcode, navigates to "{locatorURL}?zip={postcode}" via
//     browser.InterceptXHR.
//  3. Captures XHR responses matching toyota/lexus/t-api/dealer-list URL patterns.
//  4. Parses dealer JSON — tries flat envelopes first, then result.dealers nesting.
//  5. De-duplicates by dealer ID across postcode sweeps.
//
// Identifier type: OEM_DEALER_ID — value format: "toyota:{dealerID}" or "lexus:{dealerID}".
// ConfidenceContributed: 0.25 (BaseWeights["H"]).
package toyota

import (
	"context"
	"encoding/json"
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
	oemID    = "TOYOTA"
	familyID = "H"
)

// defaultBrandURLs maps Toyota Group brand → country → dealer locator URL.
// Note: Toyota DE robots.txt explicitly blocks ?dealer=* and ?dealerId=*.
// The geo-sweep appends ?zip={postcode} which is not blocked.
var defaultBrandURLs = map[string]map[string]string{
	"TOYOTA": {
		"DE": "https://www.toyota.de/haendlersuche",
		"FR": "https://www.toyota.fr/trouver-un-concessionnaire",
		"ES": "https://www.toyota.es/buscar-concesionario",
		"NL": "https://www.toyota.nl/dealer-zoeken",
		"BE": "https://www.toyota.be/nl/dealer-zoeken",
		"CH": "https://www.toyota.ch/de/haendlersuche",
	},
	"LEXUS": {
		"DE": "https://www.lexus.de/lexus-kaufen/handler-finden",
		"FR": "https://www.lexus.fr/trouver-un-distributeur",
		"ES": "https://www.lexus.es/encontrar-un-distribuidor",
		"NL": "https://www.lexus.nl/vind-een-distributeur",
		"BE": "https://www.lexus.be/nl/vind-een-distributeur",
		"CH": "https://www.lexus.ch/de/haendler-finden",
	},
}

// ToyotaLocator implements the familia_h.OEMLocator interface for Toyota Group.
type ToyotaLocator struct {
	graph     kg.KnowledgeGraph
	b         browser.Browser
	brandURLs map[string]map[string]string
	log       *slog.Logger
}

// New creates a ToyotaLocator with production settings.
func New(graph kg.KnowledgeGraph, b browser.Browser) *ToyotaLocator {
	return NewWithURLs(graph, b, defaultBrandURLs)
}

// NewWithURLs creates a ToyotaLocator with a custom brand-URL map (for tests).
func NewWithURLs(graph kg.KnowledgeGraph, b browser.Browser, brandURLs map[string]map[string]string) *ToyotaLocator {
	return &ToyotaLocator{
		graph:     graph,
		b:         b,
		brandURLs: brandURLs,
		log:       slog.Default().With("oem", oemID),
	}
}

// OEMID returns the OEM identifier.
func (l *ToyotaLocator) OEMID() string { return oemID }

// Run sweeps the Toyota / Lexus dealer locator for the given country.
func (l *ToyotaLocator) Run(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	subTechID := fmt.Sprintf("H.TOYOTA.%s", country)
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}

	if l.b == nil {
		l.log.Warn("toyota: browser not initialised — skipping", "country", country)
		result.Duration = time.Since(start)
		return result, nil
	}

	postcodes, ok := common.CountryPostcodes[country]
	if !ok {
		l.log.Info("toyota: country not configured", "country", country)
		result.Duration = time.Since(start)
		return result, nil
	}

	brands := []string{"TOYOTA", "LEXUS"}
	filter := common.DefaultXHRFilter("toyota", "lexus", "t-api", "dealer-list")

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

		l.log.Info("toyota: sweeping brand", "brand", brand, "country", country)
		disc, conf, errs := common.SweepBrand(ctx, l.b, brand, locatorURL,
			postcodes, filter, "zip", ParseCapture, l.upsert, l.log)
		result.Discovered += disc
		result.Confirmed += conf
		result.Errors += errs
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, country).Observe(result.Duration.Seconds())
	l.log.Info("toyota: done", "country", country, "discovered", result.Discovered)
	return result, nil
}

// upsert persists a single GenericDealer to the knowledge graph.
func (l *ToyotaLocator) upsert(ctx context.Context, brand string, d common.GenericDealer, sourceURL string) (bool, error) {
	dealerKey := strings.ToLower(brand) + ":" + d.CanonicalID()
	country := d.CountryCode()
	subTechID := fmt.Sprintf("H.TOYOTA.%s.%s", brand, country)
	return common.UpsertDealer(ctx, l.graph, dealerKey, familyID, subTechID, sourceURL, d, l.log)
}

// toyotaNestedWrapper covers Toyota's result.dealers nesting pattern.
type toyotaNestedWrapper struct {
	Result struct {
		Dealers []common.GenericDealer `json:"dealers"`
	} `json:"result"`
}

// ParseCapture extracts GenericDealer records from a raw Toyota/Lexus XHR response.
//
// Toyota APIs sometimes nest dealer data in a "result.dealers" structure.
// This function tries the standard flat envelopes first (via common.ParseResponse),
// then falls back to the nested result.dealers format.
func ParseCapture(body []byte) ([]common.GenericDealer, error) {
	// Try standard envelopes first.
	if dealers, err := common.ParseResponse(body); err == nil && len(dealers) > 0 {
		return dealers, nil
	}
	// Toyota wraps in result.dealers.
	var wrapper toyotaNestedWrapper
	if err := json.Unmarshal(body, &wrapper); err == nil && len(wrapper.Result.Dealers) > 0 {
		return wrapper.Result.Dealers, nil
	}
	return nil, nil
}
