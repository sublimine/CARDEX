// Package v13_completeness implements validation strategy V13 — Metadata Completeness Score.
//
// # Scoring
//
//	Field         Points  Rationale
//	─────────────────────────────────
//	VIN             20    unique identifier; critical for B2B trading
//	PriceEUR        15    non-zero price required for marketplace
//	Make            10    fundamental classification
//	Model           10    fundamental classification
//	Year            10    fundamental classification
//	Mileage         10    key valuation factor
//	Photos (≥3)     10    buyer engagement metric
//	Fuel             5    powertrain search filter
//	Transmission     5    powertrain search filter
//	Title            5    human-readable headline
//	──────────────────────
//	Total           100
//
// # Thresholds
//
//   - score ≥ 80 → PASS (high quality)
//   - score 50–79 → INFO (acceptable for wholesale)
//   - score < 50 → WARNING (low quality — manual review recommended)
package v13_completeness

import (
	"context"
	"fmt"
	"strings"

	"cardex.eu/quality/internal/pipeline"
)

const (
	strategyID   = "V13"
	strategyName = "Metadata Completeness Score"

	thresholdPass    = 80
	thresholdAccept  = 50
)

// field describes a single scored field.
type field struct {
	name   string
	points int
	check  func(*pipeline.Vehicle) bool
}

var scoreFields = []field{
	{"VIN", 20, func(v *pipeline.Vehicle) bool { return len(strings.TrimSpace(v.VIN)) == 17 }},
	{"PriceEUR", 15, func(v *pipeline.Vehicle) bool { return v.PriceEUR > 0 }},
	{"Make", 10, func(v *pipeline.Vehicle) bool { return strings.TrimSpace(v.Make) != "" }},
	{"Model", 10, func(v *pipeline.Vehicle) bool { return strings.TrimSpace(v.Model) != "" }},
	{"Year", 10, func(v *pipeline.Vehicle) bool { return v.Year > 1900 }},
	{"Mileage", 10, func(v *pipeline.Vehicle) bool { return v.Mileage > 0 }},
	{"Photos", 10, func(v *pipeline.Vehicle) bool { return len(v.PhotoURLs) >= 3 }},
	{"Fuel", 5, func(v *pipeline.Vehicle) bool { return strings.TrimSpace(v.Fuel) != "" }},
	{"Transmission", 5, func(v *pipeline.Vehicle) bool { return strings.TrimSpace(v.Transmission) != "" }},
	{"Title", 5, func(v *pipeline.Vehicle) bool { return strings.TrimSpace(v.Title) != "" }},
}

// Completeness implements pipeline.Validator for V13.
type Completeness struct{}

// New returns a Completeness validator.
func New() *Completeness { return &Completeness{} }

func (v *Completeness) ID() string                 { return strategyID }
func (v *Completeness) Name() string               { return strategyName }
func (v *Completeness) Severity() pipeline.Severity { return pipeline.SeverityWarning }

// Validate scores each field and returns a completeness summary.
func (v *Completeness) Validate(_ context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error) {
	result := &pipeline.ValidationResult{
		ValidatorID: strategyID,
		VehicleID:   vehicle.InternalID,
		Suggested:   make(map[string]string),
		Evidence:    make(map[string]string),
	}

	score := 0
	var missing []string

	for _, f := range scoreFields {
		if f.check(vehicle) {
			score += f.points
			result.Evidence[f.name] = "present"
		} else {
			missing = append(missing, fmt.Sprintf("%s (%d pts)", f.name, f.points))
			result.Evidence[f.name] = "missing"
		}
	}

	result.Evidence["score"] = fmt.Sprintf("%d/100", score)

	switch {
	case score >= thresholdPass:
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Confidence = float64(score) / 100.0

	case score >= thresholdAccept:
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = fmt.Sprintf("completeness score %d/100 — acceptable for wholesale", score)
		result.Confidence = float64(score) / 100.0
		if len(missing) > 0 {
			result.Suggested["fields_to_add"] = strings.Join(missing, ", ")
		}

	default:
		result.Pass = false
		result.Severity = pipeline.SeverityWarning
		result.Issue = fmt.Sprintf("completeness score %d/100 — below threshold %d; missing: %s",
			score, thresholdAccept, strings.Join(missing, ", "))
		result.Confidence = float64(score) / 100.0
		result.Suggested["fields_to_add"] = strings.Join(missing, ", ")
	}
	return result, nil
}
