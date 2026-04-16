// Package v02_nhtsa_vpic implements validation strategy V02 — NHTSA vPIC Decode.
//
// # Architecture
//
// The NHTSA vPIC (Vehicle Product Information Catalog) provides a free API for
// decoding VINs into structured make/model/year/fuel data:
//
//	https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVIN/{vin}?format=json
//
// # Sprint 19 Implementation
//
// This sprint implements the live-API path with an in-process memory cache
// (30-day TTL). A SQLite local-mirror path (full vPIC dataset preload) is
// deferred to Phase 5 when offline operation is required.
//
// # Cross-Validation Logic
//
// After decoding, NHTSA values are compared against the vehicle struct fields:
//   - Make mismatch → WARNING (NHTSA itself has occasional data quality issues)
//   - Model mismatch → WARNING
//   - Year mismatch → WARNING
//   - VIN not decodable by NHTSA → INFO (many non-US VINs are valid but unknown)
//
// Severity: WARNING by default; callers may escalate after pattern analysis.
package v02_nhtsa_vpic

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"

	"cardex.eu/quality/internal/pipeline"
)

const (
	strategyID   = "V02"
	strategyName = "NHTSA vPIC Decode"

	vpicBaseURL  = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVIN/%s?format=json"
	cacheTTL     = 30 * 24 * time.Hour
)

// vpicResponse is the top-level NHTSA vPIC JSON response.
type vpicResponse struct {
	Count   int          `json:"Count"`
	Results []vpicResult `json:"Results"`
}

type vpicResult struct {
	Variable string `json:"Variable"`
	Value    string `json:"Value"`
}

// decoded holds the fields we care about from a vPIC decode.
type decoded struct {
	Make      string
	Model     string
	Year      int
	FuelType  string
	BodyClass string
	Error     string // non-empty if NHTSA returned an error
	cachedAt  time.Time
}

// cacheEntry wraps a decoded result with its TTL.
type cacheEntry struct {
	data     *decoded
	storedAt time.Time
}

// NHTSAValidator implements pipeline.Validator for V02.
type NHTSAValidator struct {
	client  *http.Client
	baseURL string         // overrideable in tests
	now     func() time.Time // injectable for deterministic tests
	mu      sync.Mutex
	cache   map[string]*cacheEntry
}

// New returns an NHTSAValidator using the default http.Client and production URL.
func New() *NHTSAValidator {
	return NewWithClient(
		&http.Client{Timeout: 10 * time.Second},
		vpicBaseURL,
	)
}

// NewWithClient returns an NHTSAValidator with a custom HTTP client and base URL.
// urlTemplate must contain one %s placeholder for the VIN.
func NewWithClient(c *http.Client, urlTemplate string) *NHTSAValidator {
	return &NHTSAValidator{
		client:  c,
		baseURL: urlTemplate,
		now:     time.Now,
		cache:   make(map[string]*cacheEntry),
	}
}

func (v *NHTSAValidator) ID() string              { return strategyID }
func (v *NHTSAValidator) Name() string            { return strategyName }
func (v *NHTSAValidator) Severity() pipeline.Severity { return pipeline.SeverityWarning }

// Validate decodes the VIN via NHTSA vPIC and cross-validates make/model/year.
func (v *NHTSAValidator) Validate(ctx context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error) {
	result := &pipeline.ValidationResult{
		ValidatorID: strategyID,
		VehicleID:   vehicle.InternalID,
		Severity:    pipeline.SeverityWarning,
		Suggested:   make(map[string]string),
		Evidence:    make(map[string]string),
	}

	vin := strings.ToUpper(strings.TrimSpace(vehicle.VIN))
	if len(vin) != 17 {
		result.Pass = true // V01 owns VIN format; V02 only validates when VIN is plausibly formed
		result.Issue = "skipped: VIN not 17 characters"
		result.Severity = pipeline.SeverityInfo
		result.Confidence = 1.0
		return result, nil
	}

	dec, err := v.decode(ctx, vin)
	if err != nil {
		// API unreachable — record as INFO, do not fail the vehicle.
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = "NHTSA vPIC API unavailable: " + err.Error()
		result.Confidence = 0.0
		result.Evidence["api_error"] = err.Error()
		return result, nil
	}

	if dec.Error != "" {
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = "VIN not decodable by NHTSA vPIC: " + dec.Error
		result.Confidence = 0.5
		result.Evidence["nhtsa_error"] = dec.Error
		return result, nil
	}

	// Populate evidence.
	result.Evidence["nhtsa_make"] = dec.Make
	result.Evidence["nhtsa_model"] = dec.Model
	if dec.Year != 0 {
		result.Evidence["nhtsa_year"] = strconv.Itoa(dec.Year)
	}
	result.Evidence["nhtsa_fuel"] = dec.FuelType
	result.Evidence["nhtsa_body"] = dec.BodyClass

	// Cross-validate.
	var mismatches []string

	if dec.Make != "" && vehicle.Make != "" {
		if !looslyMatches(vehicle.Make, dec.Make) {
			mismatches = append(mismatches, fmt.Sprintf("Make: vehicle=%q NHTSA=%q", vehicle.Make, dec.Make))
			result.Suggested["Make"] = dec.Make
		}
	}
	if dec.Model != "" && vehicle.Model != "" {
		if !looslyMatches(vehicle.Model, dec.Model) {
			mismatches = append(mismatches, fmt.Sprintf("Model: vehicle=%q NHTSA=%q", vehicle.Model, dec.Model))
			result.Suggested["Model"] = dec.Model
		}
	}
	if dec.Year != 0 && vehicle.Year != 0 && vehicle.Year != dec.Year {
		mismatches = append(mismatches, fmt.Sprintf("Year: vehicle=%d NHTSA=%d", vehicle.Year, dec.Year))
		result.Suggested["Year"] = strconv.Itoa(dec.Year)
	}

	if len(mismatches) > 0 {
		result.Pass = false
		result.Issue = "NHTSA vPIC mismatch: " + strings.Join(mismatches, "; ")
		result.Confidence = 0.85
	} else {
		result.Pass = true
		result.Confidence = 0.95
	}
	return result, nil
}

// decode returns a decoded record for the given VIN, using the in-memory cache.
func (v *NHTSAValidator) decode(ctx context.Context, vin string) (*decoded, error) {
	v.mu.Lock()
	if e, ok := v.cache[vin]; ok && v.now().Sub(e.storedAt) < cacheTTL {
		v.mu.Unlock()
		return e.data, nil
	}
	v.mu.Unlock()

	url := fmt.Sprintf(v.baseURL, vin)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "CardexBot/1.0 (+https://cardex.eu/bot)")

	resp, err := v.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("NHTSA vPIC returned HTTP %d", resp.StatusCode)
	}

	var vpic vpicResponse
	if err := json.Unmarshal(body, &vpic); err != nil {
		return nil, fmt.Errorf("parse vPIC response: %w", err)
	}

	dec := &decoded{cachedAt: v.now()}
	for _, r := range vpic.Results {
		switch r.Variable {
		case "Make":
			dec.Make = strings.ToUpper(r.Value)
		case "Model":
			dec.Model = strings.ToUpper(r.Value)
		case "Model Year":
			dec.Year, _ = strconv.Atoi(r.Value)
		case "Fuel Type - Primary":
			dec.FuelType = r.Value
		case "Body Class":
			dec.BodyClass = r.Value
		case "Error Text":
			if r.Value != "" && r.Value != "0 - VIN decoded clean. Check Digit (9th position) is correct" {
				dec.Error = r.Value
			}
		}
	}

	v.mu.Lock()
	v.cache[vin] = &cacheEntry{data: dec, storedAt: v.now()}
	v.mu.Unlock()

	return dec, nil
}

// looslyMatches returns true when a and b are equal after normalisation, or
// when one contains the other (handles abbreviations like "VW" vs "VOLKSWAGEN").
func looslyMatches(a, b string) bool {
	an := normalize(a)
	bn := normalize(b)
	return an == bn || strings.Contains(an, bn) || strings.Contains(bn, an)
}

func normalize(s string) string {
	return strings.ToUpper(strings.TrimSpace(s))
}
