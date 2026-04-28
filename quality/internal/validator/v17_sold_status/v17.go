// Package v17_sold_status implements validation strategy V17 — Sold/Withdrawn Detection.
//
// # Strategy
//
// A vehicle listing that has been sold or withdrawn should not remain in the active
// catalogue. This validator detects sold/unavailable states by:
//
//  1. HTTP 410 Gone response on SourceURL → CRITICAL (permanently withdrawn).
//  2. HTML keyword scan in the fetched page body (6 languages).
//  3. schema.org ItemAvailability markup check for Discontinued/SoldOut.
//
// Any positive signal causes a CRITICAL failure — the vehicle should be immediately
// removed from the publish queue.
//
// # Keyword lists (per language)
//
//   - EN: "sold", "no longer available", "withdrawn", "this listing has ended", "listing expired"
//   - DE: "verkauft", "nicht mehr verfügbar", "dieses fahrzeug wurde verkauft"
//   - FR: "vendu", "non disponible", "annonce expirée", "ce véhicule est vendu"
//   - ES: "vendido", "no disponible", "anuncio caducado"
//   - NL: "verkocht", "niet meer beschikbaar", "advertentie verlopen"
//   - IT: "venduto", "non disponibile", "annuncio scaduto"
//
// # Dependency injection
//
// NewWithClient() accepts *http.Client for test injection via httptest.NewServer.
package v17_sold_status

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"cardex.eu/quality/internal/pipeline"
)

const (
	strategyID   = "V17"
	strategyName = "Sold/Withdrawn Detection"

	defaultTimeout = 15 * time.Second
	maxBodyBytes   = 512 * 1024 // 512 KB is enough for keyword scan
)

// soldKeywords maps language code to keywords that indicate a sold/unavailable listing.
var soldKeywords = []string{
	// English
	"sold", "no longer available", "withdrawn", "this listing has ended", "listing expired",
	"vehicle sold", "item sold",
	// German
	"verkauft", "nicht mehr verfügbar", "dieses fahrzeug wurde verkauft", "angebot abgelaufen",
	// French
	"vendu", "non disponible", "annonce expirée", "ce véhicule est vendu",
	// Spanish
	"vendido", "no disponible", "anuncio caducado",
	// Dutch
	"verkocht", "niet meer beschikbaar", "advertentie verlopen",
	// Italian
	"venduto", "non disponibile", "annuncio scaduto",
}

// schemaOrgUnavailable are schema.org ItemAvailability values indicating sold/withdrawn.
var schemaOrgUnavailable = []string{
	`"availability":"http://schema.org/Discontinued"`,
	`"availability":"https://schema.org/Discontinued"`,
	`"availability":"http://schema.org/SoldOut"`,
	`"availability":"https://schema.org/SoldOut"`,
	`"availability":"http://schema.org/OutOfStock"`,
	`"availability":"https://schema.org/OutOfStock"`,
	// lowercase variants
	`"availability": "http://schema.org/Discontinued"`,
	`"availability": "https://schema.org/Discontinued"`,
	`"availability": "http://schema.org/SoldOut"`,
	`"availability": "https://schema.org/SoldOut"`,
}

// SoldDetector implements pipeline.Validator for V17.
type SoldDetector struct {
	client *http.Client
}

// New returns a SoldDetector with a default HTTP client.
func New() *SoldDetector {
	return NewWithClient(&http.Client{Timeout: defaultTimeout})
}

// NewWithClient returns a SoldDetector using the given HTTP client.
func NewWithClient(client *http.Client) *SoldDetector {
	return &SoldDetector{client: client}
}

func (v *SoldDetector) ID() string                  { return strategyID }
func (v *SoldDetector) Name() string                { return strategyName }
func (v *SoldDetector) Severity() pipeline.Severity { return pipeline.SeverityCritical }

// Validate fetches the source URL and checks for sold/withdrawn signals.
func (v *SoldDetector) Validate(ctx context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error) {
	result := &pipeline.ValidationResult{
		ValidatorID: strategyID,
		VehicleID:   vehicle.InternalID,
		Severity:    pipeline.SeverityInfo,
		Suggested:   make(map[string]string),
		Evidence:    make(map[string]string),
	}

	sourceURL := strings.TrimSpace(vehicle.SourceURL)
	if sourceURL == "" {
		result.Pass = true
		result.Issue = "no SourceURL to check"
		result.Confidence = 1.0
		return result, nil
	}

	result.Evidence["source_url"] = sourceURL

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, sourceURL, nil)
	if err != nil {
		result.Pass = true
		result.Issue = "could not build request: " + err.Error()
		result.Confidence = 0.0
		return result, nil
	}
	req.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
	req.Header.Set("Accept-Language", "de,fr,en;q=0.8,nl,es,it;q=0.5")

	resp, err := v.client.Do(req)
	if err != nil {
		// Network/DNS error — soft fail (could be transient)
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = "request error (transient?): " + err.Error()
		result.Confidence = 0.0
		return result, nil
	}
	defer resp.Body.Close()

	result.Evidence["http_status"] = fmt.Sprintf("%d", resp.StatusCode)

	// HTTP 410 = permanently gone.
	if resp.StatusCode == http.StatusGone {
		result.Pass = false
		result.Severity = pipeline.SeverityCritical
		result.Issue = "listing returned HTTP 410 — permanently withdrawn"
		result.Confidence = 1.0
		result.Suggested["action"] = "remove vehicle from active catalogue immediately"
		return result, nil
	}

	// Non-200 non-410 → handled by V10 (liveness); skip sold detection.
	if resp.StatusCode != http.StatusOK {
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = fmt.Sprintf("HTTP %d — liveness checked by V10; no sold signal", resp.StatusCode)
		result.Confidence = 0.7
		return result, nil
	}

	// Read body (capped).
	lr := io.LimitReader(resp.Body, maxBodyBytes)
	bodyBytes, err := io.ReadAll(lr)
	if err != nil {
		result.Pass = true
		result.Issue = "body read error: " + err.Error()
		result.Confidence = 0.0
		return result, nil
	}

	bodyLower := strings.ToLower(string(bodyBytes))

	// 1. schema.org ItemAvailability check (look for compact JSON-LD patterns).
	for _, schema := range schemaOrgUnavailable {
		if strings.Contains(strings.ToLower(bodyLower), strings.ToLower(schema)) {
			result.Pass = false
			result.Severity = pipeline.SeverityCritical
			result.Issue = fmt.Sprintf("schema.org ItemAvailability signals sold/withdrawn: %s", schema)
			result.Confidence = 0.98
			result.Evidence["schema_match"] = schema
			result.Suggested["action"] = "remove vehicle from active catalogue immediately"
			return result, nil
		}
	}

	// 2. Keyword scan.
	for _, kw := range soldKeywords {
		if strings.Contains(bodyLower, kw) {
			result.Pass = false
			result.Severity = pipeline.SeverityCritical
			result.Issue = fmt.Sprintf("listing page contains sold/withdrawn keyword: %q", kw)
			result.Confidence = 0.88
			result.Evidence["keyword_match"] = kw
			result.Suggested["action"] = "verify listing status and remove if sold"
			return result, nil
		}
	}

	result.Pass = true
	result.Confidence = 0.9
	return result, nil
}
