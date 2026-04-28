package syndication

import (
	"fmt"
	"strings"
)

// FormatPrice returns a human-readable price string (€12,500).
func FormatPrice(cents int64, currency string) string {
	eur := float64(cents) / 100.0
	if currency == "" {
		currency = "EUR"
	}
	switch currency {
	case "EUR":
		return fmt.Sprintf("€%.0f", eur)
	case "CHF":
		return fmt.Sprintf("CHF %.0f", eur)
	default:
		return fmt.Sprintf("%.0f %s", eur, currency)
	}
}

// NormaliseFuelType maps internal fuel_type values to platform-neutral labels.
func NormaliseFuelType(raw string) string {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "electric":
		return "electric"
	case "hybrid_plugin", "plug_in_hybrid":
		return "hybrid_plugin"
	case "hybrid":
		return "hybrid"
	case "diesel":
		return "diesel"
	case "petrol", "gasoline", "benzin":
		return "petrol"
	case "lpg":
		return "lpg"
	case "cng":
		return "cng"
	case "hydrogen":
		return "hydrogen"
	default:
		return raw
	}
}

// TruncatePhotos returns at most max URLs from the slice.
func TruncatePhotos(urls []string, max int) []string {
	if len(urls) <= max {
		return urls
	}
	return urls[:max]
}

// NormaliseTransmission maps internal values to "manual" or "automatic".
func NormaliseTransmission(raw string) string {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "automatic", "auto", "dct", "dsg", "cvt", "tiptronic":
		return "automatic"
	default:
		return "manual"
	}
}

// SanitiseVATID strips spaces and normalises a VAT ID string.
func SanitiseVATID(raw string) string {
	return strings.ToUpper(strings.ReplaceAll(strings.TrimSpace(raw), " ", ""))
}
