// Package v19_currency implements validation strategy V19 — Currency/EUR Consistency.
//
// # Strategy
//
// All prices in the Cardex catalogue are normalised to EUR by the extraction
// pipeline. This validator checks for common conversion errors and data anomalies:
//
//  1. Zero price → CRITICAL (field is required for any monetised listing).
//  2. Price > 1,000,000 EUR → WARNING (likely a data-entry/unit error; possible CHF/SEK/CZK not converted).
//  3. Switzerland (CH): prices are commonly listed in CHF (≈ 1.05× EUR).
//     If SourceCountry=CH and PriceEUR ≥ 1000, add an INFO note reminding
//     operators to verify the EUR conversion was applied correctly.
//  4. Negative price → CRITICAL (impossible value).
//
// # Rationale for CH flag
//
// The EUR/CHF rate is historically close to 1.0 (±10%) which means a CHF price
// can slip through without a conversion step and look plausible. This INFO note
// prompts a human review for high-value Swiss listings.
package v19_currency

import (
	"context"
	"fmt"
	"strings"

	"cardex.eu/quality/internal/pipeline"
)

const (
	strategyID   = "V19"
	strategyName = "Currency/EUR Consistency"

	maxPriceEUR         = 1_000_000 // prices above this are flagged WARNING
	chfConversionMinEUR = 1_000     // CH vehicles above this get an INFO note
)

// CurrencyCheck implements pipeline.Validator for V19.
type CurrencyCheck struct{}

// New returns a CurrencyCheck validator.
func New() *CurrencyCheck { return &CurrencyCheck{} }

func (v *CurrencyCheck) ID() string                  { return strategyID }
func (v *CurrencyCheck) Name() string                { return strategyName }
func (v *CurrencyCheck) Severity() pipeline.Severity { return pipeline.SeverityCritical }

// Validate checks price for zero, negative, unrealistic, or currency-conversion anomalies.
func (v *CurrencyCheck) Validate(_ context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error) {
	result := &pipeline.ValidationResult{
		ValidatorID: strategyID,
		VehicleID:   vehicle.InternalID,
		Severity:    pipeline.SeverityInfo,
		Suggested:   make(map[string]string),
		Evidence:    make(map[string]string),
	}

	price := vehicle.PriceEUR
	result.Evidence["price_eur"] = fmt.Sprintf("%d", price)
	result.Evidence["source_country"] = vehicle.SourceCountry

	// 1. Negative price — impossible.
	if price < 0 {
		result.Pass = false
		result.Severity = pipeline.SeverityCritical
		result.Issue = fmt.Sprintf("price is negative (%d EUR) — data error", price)
		result.Confidence = 1.0
		result.Suggested["PriceEUR"] = "correct price to a positive value"
		return result, nil
	}

	// 2. Zero price — required field.
	if price == 0 {
		result.Pass = false
		result.Severity = pipeline.SeverityCritical
		result.Issue = "price is zero — required field for monetised listings"
		result.Confidence = 1.0
		result.Suggested["PriceEUR"] = "set the correct EUR price"
		return result, nil
	}

	// 3. Above hard cap → likely unit error (e.g. CHF/SEK price not converted).
	if price > maxPriceEUR {
		result.Pass = false
		result.Severity = pipeline.SeverityWarning
		result.Issue = fmt.Sprintf("price %d EUR exceeds 1,000,000 — possible currency not converted or data-entry error", price)
		result.Confidence = 0.85
		result.Suggested["action"] = "verify currency conversion; common issue with CHF, SEK, CZK sources"
		return result, nil
	}

	// 4. CH-specific EUR/CHF note (INFO only — does not fail the vehicle).
	if strings.ToUpper(vehicle.SourceCountry) == "CH" && price >= chfConversionMinEUR {
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = fmt.Sprintf("Swiss listing (CH) priced at %d EUR — verify CHF→EUR conversion was applied (rate ≈ 1.05)", price)
		result.Confidence = 0.8
		result.Evidence["chf_note"] = "true"
		result.Suggested["action"] = "confirm extraction pipeline applied CHF→EUR conversion"
		return result, nil
	}

	result.Pass = true
	result.Confidence = 1.0
	return result, nil
}
