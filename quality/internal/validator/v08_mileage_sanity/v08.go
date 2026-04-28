// Package v08_mileage_sanity implements validation strategy V08 — Mileage Sanity.
//
// # Heuristics
//
// European private usage averages ~15 000 km/year; fleet ~30 000 km/year.
// V08 uses a 20 000 km/year median as the expected annual rate.
//
// For a vehicle of age A years:
//
//	expected_median  = A × 20 000
//	expected_lower   = expected_median × 0.20  (very-low-mileage private)
//	expected_upper   = expected_median × 2.50  (high-mileage fleet)
//
// Additional hard-limit checks:
//   - mileage > 500 000 km → CRITICAL (data-entry error)
//   - mileage < 100 km AND age > 5 years → CRITICAL (suspiciously low — rollback)
//   - mileage > expected_upper → WARNING
//   - mileage < expected_lower AND age > 2 years → WARNING (low-mileage outlier)
package v08_mileage_sanity

import (
	"context"
	"fmt"
	"time"

	"cardex.eu/quality/internal/pipeline"
)

const (
	strategyID   = "V08"
	strategyName = "Mileage Sanity"

	kmPerYear    = 20_000 // expected annual km (EU median)
	lowerFactor  = 0.20   // floor multiplier
	upperFactor  = 2.50   // ceiling multiplier
	hardMax      = 500_000
	suspiciousKm = 100 // < 100 km on old car → rollback suspicion
)

// MileageSanity implements pipeline.Validator for V08.
type MileageSanity struct {
	nowYear int // injectable for tests; 0 = use real year
}

// New returns a MileageSanity validator using the current year.
func New() *MileageSanity { return &MileageSanity{} }

// NewWithYear returns a MileageSanity validator with a fixed reference year (for tests).
func NewWithYear(year int) *MileageSanity { return &MileageSanity{nowYear: year} }

func (v *MileageSanity) ID() string                 { return strategyID }
func (v *MileageSanity) Name() string               { return strategyName }
func (v *MileageSanity) Severity() pipeline.Severity { return pipeline.SeverityCritical }

// Validate checks the vehicle mileage against year-based heuristics.
func (v *MileageSanity) Validate(_ context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error) {
	result := &pipeline.ValidationResult{
		ValidatorID: strategyID,
		VehicleID:   vehicle.InternalID,
		Suggested:   make(map[string]string),
		Evidence:    make(map[string]string),
	}

	mileage := vehicle.Mileage
	vehicleYear := vehicle.Year
	nowYear := v.nowYear
	if nowYear == 0 {
		nowYear = time.Now().Year()
	}

	result.Evidence["mileage_km"] = fmt.Sprintf("%d", mileage)
	result.Evidence["vehicle_year"] = fmt.Sprintf("%d", vehicleYear)
	result.Evidence["reference_year"] = fmt.Sprintf("%d", nowYear)

	// Skip if we don't have enough info.
	if mileage == 0 && vehicleYear == 0 {
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = "mileage and year both zero — skipped"
		result.Confidence = 1.0
		return result, nil
	}

	// Hard cap.
	if mileage > hardMax {
		result.Pass = false
		result.Severity = pipeline.SeverityCritical
		result.Issue = fmt.Sprintf("mileage %d km exceeds hard cap %d km — likely data-entry error", mileage, hardMax)
		result.Confidence = 1.0
		result.Suggested["Mileage"] = "verify odometer value"
		return result, nil
	}

	// If we have vehicle year, do age-based checks.
	if vehicleYear > 0 {
		age := nowYear - vehicleYear
		if age < 0 {
			age = 0
		}
		result.Evidence["age_years"] = fmt.Sprintf("%d", age)

		// Suspiciously low mileage on old car → possible rollback.
		if mileage > 0 && mileage < suspiciousKm && age > 5 {
			result.Pass = false
			result.Severity = pipeline.SeverityCritical
			result.Issue = fmt.Sprintf("mileage %d km on %d-year-old vehicle is suspiciously low — possible odometer rollback", mileage, age)
			result.Confidence = 0.95
			result.Suggested["action"] = "verify odometer history"
			return result, nil
		}

		if age > 0 && mileage > 0 {
			expectedMedian := age * kmPerYear
			expectedLower := int(float64(expectedMedian) * lowerFactor)
			expectedUpper := int(float64(expectedMedian) * upperFactor)

			result.Evidence["expected_lower_km"] = fmt.Sprintf("%d", expectedLower)
			result.Evidence["expected_median_km"] = fmt.Sprintf("%d", expectedMedian)
			result.Evidence["expected_upper_km"] = fmt.Sprintf("%d", expectedUpper)

			if mileage > expectedUpper {
				result.Pass = false
				result.Severity = pipeline.SeverityWarning
				result.Issue = fmt.Sprintf("mileage %d km exceeds expected upper bound %d km for %d-year-old vehicle", mileage, expectedUpper, age)
				result.Confidence = 0.8
				return result, nil
			}

			if age > 2 && mileage < expectedLower {
				result.Pass = false
				result.Severity = pipeline.SeverityWarning
				result.Issue = fmt.Sprintf("mileage %d km is below expected lower bound %d km for %d-year-old vehicle — verify", mileage, expectedLower, age)
				result.Confidence = 0.7
				return result, nil
			}
		}
	}

	result.Pass = true
	result.Severity = pipeline.SeverityInfo
	result.Confidence = 0.85
	return result, nil
}
