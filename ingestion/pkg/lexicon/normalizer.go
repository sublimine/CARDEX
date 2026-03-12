package lexicon

import (
	"regexp"
	"strings"
)

// Constantes de estado jurídico inmutable
const (
	StatusMargin     = "REBU / MARGIN_SCHEME"
	StatusDeductible = "VAT_DEDUCTIBLE"
	StatusUnknown    = "PENDING_VERIFICATION"
)

// Compilación estática RE2 para garantizar latencia sub-milisegundo. Inmune a ReDoS.
var (
	// Patrones de Régimen de Bienes Usados (IVA no deducible)
	regexMargin = regexp.MustCompile(`(?i)(§\s*25a|25a\s*ustg|margeregeling|marge auto|iva no deducible|tva non récupérable|vat margin)`)

	// Patrones de IVA Deducible
	regexVat = regexp.MustCompile(`(?i)(mwst\.?\s*ausweisbar|tva récupérable|iva deducible|btw aftrekbaar|vat qualifying)`)
)

// Capa L1: Diccionario Transaccional O(1) en RAM
var featureDictL1 = map[string]string{
	"cuir":       "leather_seats",
	"leder":      "leather_seats",
	"ledersitze": "leather_seats",
	"automatik":  "automatic_transmission",
	"boîte":      "automatic_transmission",
	"automatica": "automatic_transmission",
	"navi":       "navigation_system",
	"gps":        "navigation_system",
}

// NormalizedAsset representa el activo purificado tras Tax Hunter y Lexicon L1.
type NormalizedAsset struct {
	VIN         string          `json:"vin"`
	Price       float64         `json:"price"`
	Currency    string          `json:"currency"`
	LegalStatus string          `json:"legal_status"`
	Features    map[string]bool `json:"features"`
}

// Purify ejecuta el motor Tax Hunter y Lexicon L1 sobre el payload bruto.
func Purify(vin string, price float64, currency string, rawDescription string) NormalizedAsset {
	descLower := strings.ToLower(rawDescription)

	// 1. Tax Hunter: Determinismo Fiscal
	legalStatus := StatusUnknown
	if regexMargin.MatchString(descLower) {
		legalStatus = StatusMargin
	} else if regexVat.MatchString(descLower) {
		legalStatus = StatusDeductible
	}

	// 2. Lexicon L1: Extracción de atributos booleanos
	features := make(map[string]bool)
	tokens := strings.Fields(strings.ReplaceAll(descLower, ",", " "))
	for _, token := range tokens {
		token = strings.Trim(token, ".;!()-")
		if stdFeat, exists := featureDictL1[token]; exists {
			features[stdFeat] = true
		}
	}

	return NormalizedAsset{
		VIN:         vin,
		Price:       price,
		Currency:    currency,
		LegalStatus: legalStatus,
		Features:    features,
	}
}
