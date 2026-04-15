// Package v09_year_consistency implements validation strategy V09 — Year Consistency.
//
// # Checks
//
//  1. Hard-limit: year < 1900 → CRITICAL (invalid year)
//  2. Hard-limit: year > currentYear+1 → CRITICAL (impossible future year)
//  3. year == currentYear+1 → WARNING (model-year confusion — valid but unusual)
//  4. Title year: parse the first 4-digit number in [1900, currentYear+2] from
//     vehicle.Title; if found and mismatches vehicle.Year → WARNING
//  5. NHTSA year (stored in vehicle.Metadata["nhtsa_year"]): mismatch → WARNING
//
// Severity: CRITICAL for impossible years; WARNING for likely confusion.
package v09_year_consistency

import (
	"context"
	"fmt"
	"regexp"
	"strconv"
	"strings"
	"time"

	"cardex.eu/quality/internal/pipeline"
)

const (
	strategyID   = "V09"
	strategyName = "Year Consistency"

	minValidYear = 1900
)

var yearRE = regexp.MustCompile(`\b(1[9][0-9]{2}|2[0-9]{3})\b`)

// YearConsistency implements pipeline.Validator for V09.
type YearConsistency struct {
	nowYear int // injectable for tests; 0 = real year
}

// New returns a YearConsistency validator using the current year.
func New() *YearConsistency { return &YearConsistency{} }

// NewWithYear returns a YearConsistency validator with a fixed reference year.
func NewWithYear(year int) *YearConsistency { return &YearConsistency{nowYear: year} }

func (v *YearConsistency) ID() string                 { return strategyID }
func (v *YearConsistency) Name() string               { return strategyName }
func (v *YearConsistency) Severity() pipeline.Severity { return pipeline.SeverityCritical }

// Validate checks the vehicle year for consistency.
func (v *YearConsistency) Validate(_ context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error) {
	result := &pipeline.ValidationResult{
		ValidatorID: strategyID,
		VehicleID:   vehicle.InternalID,
		Severity:    pipeline.SeverityWarning,
		Suggested:   make(map[string]string),
		Evidence:    make(map[string]string),
	}

	nowYear := v.nowYear
	if nowYear == 0 {
		nowYear = time.Now().Year()
	}

	year := vehicle.Year
	result.Evidence["vehicle_year"] = fmt.Sprintf("%d", year)
	result.Evidence["current_year"] = fmt.Sprintf("%d", nowYear)

	// Skip if year is unset.
	if year == 0 {
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = "year not set — skipped"
		result.Confidence = 1.0
		return result, nil
	}

	// 1. Hard lower bound.
	if year < minValidYear {
		result.Pass = false
		result.Severity = pipeline.SeverityCritical
		result.Issue = fmt.Sprintf("year %d is below minimum valid year %d", year, minValidYear)
		result.Confidence = 1.0
		result.Suggested["Year"] = "verify vehicle year"
		return result, nil
	}

	// 2. Hard upper bound.
	if year > nowYear+1 {
		result.Pass = false
		result.Severity = pipeline.SeverityCritical
		result.Issue = fmt.Sprintf("year %d is in the future (current: %d)", year, nowYear)
		result.Confidence = 1.0
		result.Suggested["Year"] = fmt.Sprintf("year cannot exceed %d", nowYear+1)
		return result, nil
	}

	var warnings []string

	// 3. One-year model-year ahead.
	if year == nowYear+1 {
		warnings = append(warnings, fmt.Sprintf("year %d is one year ahead — model year confusion", year))
	}

	// 4. Title year cross-check.
	if titleYear := extractYearFromTitle(vehicle.Title, nowYear); titleYear > 0 && titleYear != year {
		warnings = append(warnings, fmt.Sprintf("title year %d mismatches extracted year %d", titleYear, year))
		result.Evidence["title_year"] = fmt.Sprintf("%d", titleYear)
		result.Suggested["Year"] = fmt.Sprintf("title suggests year %d — verify", titleYear)
	}

	// 5. NHTSA year from metadata.
	if vehicle.Metadata != nil {
		if nhtsaYearStr := vehicle.Metadata["nhtsa_year"]; nhtsaYearStr != "" {
			nhtsaYear, err := strconv.Atoi(nhtsaYearStr)
			if err == nil && nhtsaYear != year {
				warnings = append(warnings, fmt.Sprintf("NHTSA decoded year %d mismatches vehicle year %d", nhtsaYear, year))
				result.Evidence["nhtsa_year"] = nhtsaYearStr
			}
		}
	}

	if len(warnings) > 0 {
		result.Pass = false
		result.Severity = pipeline.SeverityWarning
		result.Issue = strings.Join(warnings, "; ")
		result.Confidence = 0.8
		return result, nil
	}

	result.Pass = true
	result.Severity = pipeline.SeverityInfo
	result.Confidence = 1.0
	return result, nil
}

// extractYearFromTitle finds the most plausible year in the raw title string.
// Returns 0 if none found or ambiguous.
func extractYearFromTitle(title string, nowYear int) int {
	if title == "" {
		return 0
	}
	matches := yearRE.FindAllString(title, -1)
	if len(matches) == 0 {
		return 0
	}
	// Use the first year that falls in [1980, nowYear+2].
	for _, m := range matches {
		y, _ := strconv.Atoi(m)
		if y >= 1980 && y <= nowYear+2 {
			return y
		}
	}
	return 0
}
