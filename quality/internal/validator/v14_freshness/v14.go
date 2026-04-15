// Package v14_freshness implements validation strategy V14 — Freshness.
//
// # Rationale
//
// Vehicle listings have a short shelf-life: EU automotive research shows median
// time-to-sale of ~60 days, with 20% of listings removed within 7 days of
// posting. A stale extracted record may correspond to a vehicle already sold or
// repriced.
//
// # Decision rules
//
//   - archive vehicle (metadata["is_archive"]=="true") → INFO (skip: intentionally old)
//   - ExtractedAt is zero → INFO (extraction timestamp absent)
//   - age < 24 h     → PASS
//   - 24 h – 72 h    → INFO  (recent; fine for daily jobs)
//   - 72 h – 7 days  → WARNING ("stale — refresh recommended")
//   - > 7 days       → CRITICAL ("very stale — possible removed listing")
//
// Severity: CRITICAL for very stale; WARNING for moderately stale.
package v14_freshness

import (
	"context"
	"fmt"
	"time"

	"cardex.eu/quality/internal/pipeline"
)

const (
	strategyID   = "V14"
	strategyName = "Freshness"
)

var (
	ageFresh   = 24 * time.Hour
	ageInfo    = 72 * time.Hour
	ageWarning = 7 * 24 * time.Hour
)

// Freshness implements pipeline.Validator for V14.
type Freshness struct {
	now func() time.Time // injectable for deterministic tests
}

// New returns a Freshness validator using real wall-clock time.
func New() *Freshness { return &Freshness{now: time.Now} }

// NewWithClock returns a Freshness validator with a fixed clock for tests.
func NewWithClock(clock func() time.Time) *Freshness { return &Freshness{now: clock} }

func (v *Freshness) ID() string                 { return strategyID }
func (v *Freshness) Name() string               { return strategyName }
func (v *Freshness) Severity() pipeline.Severity { return pipeline.SeverityCritical }

// Validate checks how old the vehicle record is relative to now.
func (v *Freshness) Validate(_ context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error) {
	result := &pipeline.ValidationResult{
		ValidatorID: strategyID,
		VehicleID:   vehicle.InternalID,
		Severity:    pipeline.SeverityInfo,
		Suggested:   make(map[string]string),
		Evidence:    make(map[string]string),
	}

	// Skip archive vehicles.
	if vehicle.Metadata != nil && vehicle.Metadata["is_archive"] == "true" {
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = "archive vehicle — freshness check skipped"
		result.Confidence = 1.0
		return result, nil
	}

	if vehicle.ExtractedAt.IsZero() {
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = "extraction timestamp absent — freshness unknown"
		result.Confidence = 0.0
		return result, nil
	}

	now := v.now()
	age := now.Sub(vehicle.ExtractedAt)

	result.Evidence["extracted_at"] = vehicle.ExtractedAt.UTC().Format(time.RFC3339)
	result.Evidence["age_hours"] = fmt.Sprintf("%.1f", age.Hours())

	switch {
	case age <= ageFresh:
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Confidence = 1.0

	case age <= ageInfo:
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = fmt.Sprintf("%.1f hours old — recent, no action needed", age.Hours())
		result.Confidence = 0.95

	case age <= ageWarning:
		result.Pass = false
		result.Severity = pipeline.SeverityWarning
		result.Issue = fmt.Sprintf("%.0f hours old — stale, refresh recommended", age.Hours())
		result.Confidence = 0.85
		result.Suggested["action"] = "re-extract or verify listing is still live"

	default:
		result.Pass = false
		result.Severity = pipeline.SeverityCritical
		result.Issue = fmt.Sprintf("%.0f hours old (%.1f days) — very stale, possible removed listing",
			age.Hours(), age.Hours()/24)
		result.Confidence = 0.9
		result.Suggested["action"] = "verify listing is still live; consider removing from catalogue"
	}
	return result, nil
}
