// Package v01_vin_checksum implements validation strategy V01 — VIN Checksum.
//
// # Standard
//
// ISO 3779 / FMVSS 115 defines the 17-character Vehicle Identification Number.
// Position 9 (zero-indexed: index 8) carries a check digit computed from the
// other 16 characters using a transliteration table, positional weights, and
// modulo-11 arithmetic.
//
// # Algorithm
//
//  1. Validate length == 17 and absence of forbidden letters I, O, Q.
//  2. Transliterate each character to a numeric value (A=1…Z=9 with gaps).
//  3. Multiply each numeric value by its positional weight.
//  4. Sum all products; compute sum mod 11.
//  5. If result == 10, check digit must be 'X'; otherwise it is the digit itself.
//  6. Compare with the actual character at index 8.
//
// Severity: CRITICAL — a VIN with an invalid check digit is almost certainly
// a data entry error, OCR artifact, or fraudulent identifier.
package v01_vin_checksum

import (
	"context"
	"strings"

	"cardex.eu/quality/internal/pipeline"
)

const (
	strategyID   = "V01"
	strategyName = "VIN Checksum (ISO 3779)"
)

// transliteration maps each allowed VIN character to its numeric value.
// Characters I (9), O (15), Q (17) are excluded from valid VINs.
var transliteration = map[byte]int{
	'0': 0, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
	'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6, 'G': 7, 'H': 8,
	'J': 1, 'K': 2, 'L': 3, 'M': 4, 'N': 5, 'P': 7, 'R': 9,
	'S': 2, 'T': 3, 'U': 4, 'V': 5, 'W': 6, 'X': 7, 'Y': 8, 'Z': 9,
}

// weights are the positional multipliers for each of the 17 VIN positions.
var weights = [17]int{8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2}

// VINChecksum implements pipeline.Validator for V01.
type VINChecksum struct{}

// New returns a VINChecksum validator.
func New() *VINChecksum { return &VINChecksum{} }

func (v *VINChecksum) ID() string              { return strategyID }
func (v *VINChecksum) Name() string            { return strategyName }
func (v *VINChecksum) Severity() pipeline.Severity { return pipeline.SeverityCritical }

// Validate checks the VIN check-digit per ISO 3779.
func (v *VINChecksum) Validate(_ context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error) {
	result := &pipeline.ValidationResult{
		ValidatorID: strategyID,
		VehicleID:   vehicle.InternalID,
		Severity:    pipeline.SeverityCritical,
		Suggested:   make(map[string]string),
		Evidence:    make(map[string]string),
	}

	vin := strings.ToUpper(strings.TrimSpace(vehicle.VIN))

	// Length check.
	if len(vin) != 17 {
		result.Pass = false
		result.Issue = "VIN must be exactly 17 characters"
		result.Confidence = 1.0
		result.Suggested["VIN"] = "verify and correct the VIN"
		return result, nil
	}

	// Forbidden character check.
	for _, ch := range vin {
		if ch == 'I' || ch == 'O' || ch == 'Q' {
			result.Pass = false
			result.Issue = "VIN contains forbidden character: " + string(ch)
			result.Confidence = 1.0
			result.Suggested["VIN"] = "remove or replace I, O, Q characters"
			return result, nil
		}
	}

	// Transliteration + weighted sum.
	sum := 0
	for i := 0; i < 17; i++ {
		if i == 8 {
			continue // skip check-digit position in sum
		}
		val, ok := transliteration[vin[i]]
		if !ok {
			result.Pass = false
			result.Issue = "VIN contains unrecognised character at position " + string(rune('0'+i+1))
			result.Confidence = 1.0
			return result, nil
		}
		sum += val * weights[i]
	}

	rem := sum % 11
	var expectedCheckDigit byte
	if rem == 10 {
		expectedCheckDigit = 'X'
	} else {
		expectedCheckDigit = byte('0' + rem)
	}

	actual := vin[8]
	result.Evidence["vin"] = vin
	result.Evidence["check_digit_expected"] = string(expectedCheckDigit)
	result.Evidence["check_digit_actual"] = string(actual)
	result.Evidence["weighted_sum"] = strings.TrimSpace(strings.Replace(string(rune('0'+rem)), "\x00", "", -1))

	if actual != expectedCheckDigit {
		result.Pass = false
		result.Issue = "VIN check digit mismatch: expected " + string(expectedCheckDigit) + " at position 9, got " + string(actual)
		result.Confidence = 1.0
		result.Suggested["VIN"] = "fix typo in VIN — check digit should be " + string(expectedCheckDigit)
		return result, nil
	}

	result.Pass = true
	result.Confidence = 1.0
	return result, nil
}
