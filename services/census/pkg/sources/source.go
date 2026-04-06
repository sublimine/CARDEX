package sources

import (
	"context"
	"time"
)

// FleetRecord represents a single row of government registration statistics.
// Each record says: "In {Country}, there are {Count} vehicles of {Make}/{Year}/{FuelType} registered."
type FleetRecord struct {
	Country     string    // ISO 3166-1 alpha-2
	Make        string    // Normalized to CARDEX canonical form
	Year        int       // Registration year
	FuelType    string    // PETROL, DIESEL, ELECTRIC, HYBRID, LPG, OTHER
	Count       int64     // Number of registered vehicles
	AsOfDate    time.Time // When this data was published
	Source      string    // KBA, RDW, DGT, SDES, DIV, ASTRA
	RawCategory string    // Original category string from source (for audit)
}

// CensusSource is implemented by each country's government data ingestor.
type CensusSource interface {
	ID() string
	Country() string
	Fetch(ctx context.Context) ([]FleetRecord, error)
}

// CanonicalMakes maps variant spellings to a single canonical form.
// Sources use different capitalizations and abbreviations.
var CanonicalMakes = map[string]string{
	// German KBA variants
	"MERCEDES-BENZ":          "Mercedes-Benz",
	"MERCEDES BENZ":          "Mercedes-Benz",
	"MERCEDES":               "Mercedes-Benz",
	"VW":                     "Volkswagen",
	"VOLKSWAGEN":             "Volkswagen",
	"BMW":                    "BMW",
	"AUDI":                   "Audi",
	"OPEL":                   "Opel",
	"FORD":                   "Ford",
	"RENAULT":                "Renault",
	"PEUGEOT":                "Peugeot",
	"CITROEN":                "Citroën",
	"CITROËN":                "Citroën",
	"FIAT":                   "Fiat",
	"TOYOTA":                 "Toyota",
	"HYUNDAI":                "Hyundai",
	"KIA":                    "Kia",
	"SKODA":                  "Skoda",
	"ŠKODA":                  "Skoda",
	"SEAT":                   "SEAT",
	"VOLVO":                  "Volvo",
	"NISSAN":                 "Nissan",
	"MAZDA":                  "Mazda",
	"HONDA":                  "Honda",
	"SUZUKI":                 "Suzuki",
	"DACIA":                  "Dacia",
	"MINI":                   "MINI",
	"SMART":                  "Smart",
	"PORSCHE":                "Porsche",
	"LAND ROVER":             "Land Rover",
	"JAGUAR":                 "Jaguar",
	"ALFA ROMEO":             "Alfa Romeo",
	"TESLA":                  "Tesla",
	"CUPRA":                  "Cupra",
	"DS":                     "DS",
	"DS AUTOMOBILES":         "DS",
	"MITSUBISHI":             "Mitsubishi",
	"SUBARU":                 "Subaru",
	"CHEVROLET":              "Chevrolet",
	"JEEP":                   "Jeep",
	"LEXUS":                  "Lexus",
	"INFINITI":               "Infiniti",
	"MASERATI":               "Maserati",
	"FERRARI":                "Ferrari",
	"LAMBORGHINI":            "Lamborghini",
	"ASTON MARTIN":           "Aston Martin",
	"BENTLEY":                "Bentley",
	"ROLLS-ROYCE":            "Rolls-Royce",
	"ROLLS ROYCE":            "Rolls-Royce",
	"MCLAREN":                "McLaren",
	"BUGATTI":                "Bugatti",
	"LANCIA":                 "Lancia",
	"SAAB":                   "Saab",
	"SSANGYONG":              "SsangYong",
	"POLESTAR":               "Polestar",
	"BYD":                    "BYD",
	"NIO":                    "NIO",
	"XPENG":                  "XPENG",
	"MG":                     "MG",
	"LYNK & CO":              "Lynk & Co",
	"ORA":                    "Ora",
	"AIWAYS":                 "Aiways",
	"CHRYSLER":               "Chrysler",
	"DODGE":                  "Dodge",
	"ISUZU":                  "Isuzu",
	"LADA":                   "Lada",
	"ROVER":                  "Rover",
	"DAEWOO":                 "Daewoo",
	"ABARTH":                 "Abarth",

	// French SDES / Spanish DGT variants
	"VOLKSWAGEN/VW":          "Volkswagen",
	"MERCEDES-BENZ/SMART":    "Mercedes-Benz",

	// Dutch RDW variants
	"MERCEDES-AMG":           "Mercedes-Benz",
	"BMW I":                  "BMW",
	"BMW M":                  "BMW",
	"VOLKSWAGEN BEDRIJFSW.":  "Volkswagen",
	"VOLKSWAGEN BEDRIJFSWAGENS": "Volkswagen",
}

// NormalizeMake returns the canonical make name, or the input uppercased if unknown.
func NormalizeMake(raw string) string {
	// Try exact match first
	if canonical, ok := CanonicalMakes[raw]; ok {
		return canonical
	}
	// Try uppercased
	upper := rawToUpper(raw)
	if canonical, ok := CanonicalMakes[upper]; ok {
		return canonical
	}
	// Return as-is with title case
	return raw
}

func rawToUpper(s string) string {
	b := make([]byte, 0, len(s))
	for i := 0; i < len(s); i++ {
		c := s[i]
		if c >= 'a' && c <= 'z' {
			c -= 32
		}
		b = append(b, c)
	}
	return string(b)
}

// NormalizeFuel maps source-specific fuel type strings to CARDEX canonical types.
func NormalizeFuel(raw string) string {
	upper := rawToUpper(raw)
	switch {
	case contains(upper, "ELEKTRO") || contains(upper, "ELECTRIC") || contains(upper, "BEV") || contains(upper, "ELECTRI"):
		return "ELECTRIC"
	case contains(upper, "HYBRID") || contains(upper, "PHEV") || contains(upper, "HEV"):
		return "HYBRID"
	case contains(upper, "DIESEL") || contains(upper, "GASOIL") || contains(upper, "GAZOLE"):
		return "DIESEL"
	case contains(upper, "BENZIN") || contains(upper, "PETROL") || contains(upper, "GASOLINE") || contains(upper, "ESSENCE") || contains(upper, "GASOLINA"):
		return "PETROL"
	case contains(upper, "LPG") || contains(upper, "GPL"):
		return "LPG"
	case contains(upper, "CNG") || contains(upper, "GAS NATURAL") || contains(upper, "ERDGAS"):
		return "CNG"
	case contains(upper, "HYDROGEN") || contains(upper, "WASSERSTOFF"):
		return "HYDROGEN"
	default:
		return "OTHER"
	}
}

func contains(s, sub string) bool {
	return len(s) >= len(sub) && (s == sub || len(s) > 0 && containsImpl(s, sub))
}

func containsImpl(s, sub string) bool {
	for i := 0; i <= len(s)-len(sub); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
