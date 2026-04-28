// Package normalize transforms raw extracted vehicle data into canonical form.
// Normalisation happens after extraction and before persistence.
package normalize

import (
	"strings"
	"unicode"
)

// FuelType maps raw fuel type strings (in any language) to canonical values.
var fuelTypeMap = map[string]string{
	// English
	"petrol": "gasoline", "gasoline": "gasoline", "benzin": "gasoline",
	"gas": "gasoline", "essence": "gasoline", "gasolina": "gasoline",
	"diesel": "diesel", "gazole": "diesel", "gasoil": "diesel",
	"electric": "electric", "électrique": "electric", "eléctrico": "electric",
	"elektro": "electric", "bev": "electric",
	"hybrid": "hybrid", "hybride": "hybrid", "híbrido": "hybrid",
	"phev": "hybrid", "plug-in": "hybrid", "plug in": "hybrid",
	"lpg": "lpg", "gpl": "lpg", "autogas": "lpg",
	"cng": "cng", "gnv": "cng", "erdgas": "cng",
	"hydrogen": "hydrogen", "wasserstoff": "hydrogen", "hydrogène": "hydrogen",
}

// TransmissionMap maps raw transmission strings to canonical values.
var transmissionMap = map[string]string{
	"manual": "manual", "manuell": "manual", "manuelle": "manual", "manuale": "manual",
	"schaltgetriebe": "manual", "mt": "manual",
	"automatic": "automatic", "automatique": "automatic", "automático": "automatic",
	"automatik": "automatic", "at": "automatic", "auto": "automatic",
	"dsg": "automatic", "cvt": "automatic", "s tronic": "automatic",
	"semi-automatic": "semi-automatic", "semi auto": "semi-automatic",
	"semi-automatique": "semi-automatic", "robotized": "semi-automatic",
}

// BodyTypeMap maps raw body type strings to canonical values.
var bodyTypeMap = map[string]string{
	"sedan": "sedan", "berline": "sedan", "limousine": "sedan", "berlina": "sedan",
	"saloon": "sedan",
	"hatchback": "hatchback", "hayon": "hatchback", "compacto": "hatchback",
	"suv": "suv", "crossover": "suv", "4x4": "suv", "tout-terrain": "suv",
	"geländewagen": "suv",
	"estate": "estate", "break": "estate", "kombi": "estate", "variant": "estate",
	"touring": "estate", "sw": "estate",
	"coupe": "coupe", "coupé": "coupe", "sports": "coupe",
	"convertible": "convertible", "cabriolet": "convertible", "cabrio": "convertible",
	"roadster": "convertible", "spider": "convertible", "spyder": "convertible",
	"van": "van", "minivan": "van", "mpv": "van", "monospace": "van",
	"pickup": "pickup", "pick-up": "pickup", "truck": "pickup",
}

// NormalizeFuelType returns the canonical fuel type for raw, or raw if unknown.
func NormalizeFuelType(raw string) string {
	key := strings.ToLower(strings.TrimSpace(raw))
	if canon, ok := fuelTypeMap[key]; ok {
		return canon
	}
	// Partial match: check if any key is contained in the raw string.
	for k, v := range fuelTypeMap {
		if strings.Contains(key, k) {
			return v
		}
	}
	return raw
}

// NormalizeTransmission returns the canonical transmission for raw, or raw if unknown.
func NormalizeTransmission(raw string) string {
	key := strings.ToLower(strings.TrimSpace(raw))
	if canon, ok := transmissionMap[key]; ok {
		return canon
	}
	for k, v := range transmissionMap {
		if strings.Contains(key, k) {
			return v
		}
	}
	return raw
}

// NormalizeBodyType returns the canonical body type for raw, or raw if unknown.
func NormalizeBodyType(raw string) string {
	key := strings.ToLower(strings.TrimSpace(raw))
	if canon, ok := bodyTypeMap[key]; ok {
		return canon
	}
	for k, v := range bodyTypeMap {
		if strings.Contains(key, k) {
			return v
		}
	}
	return raw
}

// NormalizeMake capitalises the first letter of each word for make/model fields.
func NormalizeMake(raw string) string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return raw
	}
	return strings.Title(strings.ToLower(raw)) //nolint:staticcheck // Title is fine for EU car names
}

// NormalizeVIN upper-cases and strips whitespace from a VIN.
func NormalizeVIN(raw string) string {
	var b strings.Builder
	for _, r := range strings.ToUpper(raw) {
		if !unicode.IsSpace(r) {
			b.WriteRune(r)
		}
	}
	s := b.String()
	if len(s) != 17 {
		return "" // non-standard VIN — drop rather than store invalid
	}
	return s
}

// NormalizeCurrency upper-cases an ISO 4217 currency code.
func NormalizeCurrency(raw string) string {
	return strings.ToUpper(strings.TrimSpace(raw))
}
