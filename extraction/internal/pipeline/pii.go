// PII sanitizer — strips personal data from VehicleRaw free-text fields
// before persistence, reducing GDPR Art. 6 exposure.
//
// Scope: AdditionalFields string values only.
// Structured facts (VIN, Make, Model, Year, Price…) are never touched.
// Approach: regex-first, no external NLP dependency.
package pipeline

import (
	"regexp"
	"strings"
)

// piiPatterns are applied to every free-text string value.
var piiPatterns = []*regexp.Regexp{
	// RFC-5322 email (simplified, avoids catastrophic backtracking).
	// Case-insensitive only on the domain TLD part.
	regexp.MustCompile(`[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}`),

	// International phone numbers — must start with country code (+XX or 00XX)
	// so bare VINs and year/power numbers are not matched.
	// Formats: +33 1 23 45 67 89 | +34 91 234 56 78 | 0033 1 23 45 67 89
	regexp.MustCompile(`(?:\+\d{1,3}|00\d{1,3})[\s\-.]?\(?\d{1,4}\)?(?:[\s\-.]?\d{2,5}){2,5}`),

	// Salesperson name patterns: "Contact: Firstname Lastname"
	// Note: NO (?i) flag — label must appear in its standard capitalisation
	// so that "contact info here" (all lowercase) is NOT matched.
	// Handles DE/FR/ES/NL/EN label variants in title case.
	regexp.MustCompile(`(?:Contact|Vendeur|Verkäufer|Vendedor|Verkoper|Ansprechpartner|Conseiller|Consultor)\s*:?\s*[A-ZÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖÙÚÛÜ][a-zàáâãäåæçèéêëìíîïðñòóôõöùúûü]+(?:\s+[A-ZÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖÙÚÛÜ][a-zàáâãäåæçèéêëìíîïðñòóôõöùúûü]+)*`),
}

const piiRedact = "[REDACTED]"

func sanitizePIIString(s string) (string, bool) {
	changed := false
	for _, re := range piiPatterns {
		if re.MatchString(s) {
			s = re.ReplaceAllString(s, piiRedact)
			changed = true
		}
	}
	return s, changed
}

// SanitizeVehicle removes PII from AdditionalFields of v in-place.
// Returns the number of fields modified.
func SanitizeVehicle(v *VehicleRaw) int {
	if v == nil {
		return 0
	}
	modified := 0
	for k, val := range v.AdditionalFields {
		s, ok := val.(string)
		if !ok {
			continue
		}
		cleaned, changed := sanitizePIIString(s)
		if changed {
			v.AdditionalFields[k] = cleaned
			modified++
		}
	}
	return modified
}

// SanitizeVehicles applies SanitizeVehicle to every vehicle in the slice.
// Returns total number of field mutations across all vehicles.
func SanitizeVehicles(vehicles []*VehicleRaw) int {
	total := 0
	for _, v := range vehicles {
		total += SanitizeVehicle(v)
	}
	return total
}

// TruncateVINForLog returns the VIN with the last 4 characters masked —
// safe to include in structured log fields.
// e.g. "WVW ZZZ1JZ3W000001" → "WVW ZZZ1JZ3W****"
func TruncateVINForLog(vin string) string {
	vin = strings.TrimSpace(vin)
	if len(vin) <= 4 {
		return strings.Repeat("*", len(vin))
	}
	return vin[:len(vin)-4] + "****"
}
