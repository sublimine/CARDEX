// Package v06_photo_count implements validation strategy V06 — Photo Count.
//
// # Rationale
//
// Photo count is a strong proxy for listing quality. Aggregate data from
// European automotive marketplaces shows:
//
//	0 photos   → listing unusable; buyers skip entirely
//	1–2 photos → stock placeholder or incomplete upload
//	3–5 photos → acceptable for wholesale/B2B distribution
//	6+  photos → premium listing quality; highest buyer conversion
//
// Severity escalation:
//   - 0 photos → CRITICAL (blocks publication)
//   - 1–2 photos → WARNING
//   - 3–5 photos → INFO (acceptable)
//   - 6+ photos → PASS
package v06_photo_count

import (
	"context"
	"fmt"
	"strconv"

	"cardex.eu/quality/internal/pipeline"
)

const (
	strategyID   = "V06"
	strategyName = "Photo Count"

	thresholdCritical = 0 // 0 photos → CRITICAL
	thresholdWarning  = 3 // <3 photos → WARNING
	thresholdInfo     = 6 // <6 photos → INFO (acceptable wholesale)
)

// PhotoCount implements pipeline.Validator for V06.
type PhotoCount struct{}

// New returns a PhotoCount validator.
func New() *PhotoCount { return &PhotoCount{} }

func (v *PhotoCount) ID() string                 { return strategyID }
func (v *PhotoCount) Name() string               { return strategyName }
func (v *PhotoCount) Severity() pipeline.Severity { return pipeline.SeverityCritical }

// Validate checks the number of photo URLs on the vehicle.
func (v *PhotoCount) Validate(_ context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error) {
	n := len(vehicle.PhotoURLs)

	result := &pipeline.ValidationResult{
		ValidatorID: strategyID,
		VehicleID:   vehicle.InternalID,
		Suggested:   make(map[string]string),
		Evidence: map[string]string{
			"photo_count": strconv.Itoa(n),
		},
	}

	switch {
	case n == thresholdCritical:
		result.Pass = false
		result.Severity = pipeline.SeverityCritical
		result.Issue = "no photos — listing unusable for buyers"
		result.Confidence = 1.0
		result.Suggested["action"] = "upload at least 6 vehicle photos"

	case n < thresholdWarning:
		result.Pass = false
		result.Severity = pipeline.SeverityWarning
		result.Issue = fmt.Sprintf("only %d photo(s) — possible stock placeholder (min 3 recommended)", n)
		result.Confidence = 1.0
		result.Suggested["action"] = fmt.Sprintf("upload %d more photo(s) to reach minimum quality", thresholdWarning-n)

	case n < thresholdInfo:
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = fmt.Sprintf("%d photos — acceptable for wholesale; premium listings need 6+", n)
		result.Confidence = 1.0

	default:
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Confidence = 1.0
	}
	return result, nil
}
