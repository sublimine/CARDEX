package landedcost

import "strings"

// defaultTransportCosts holds vehicle logistics costs in EUR cents for each
// directional country pair. Ported verbatim from innovation/routes/transport.go
// (cardex.eu/routes) to keep landed-cost estimates consistent with the
// disposition optimizer. Basis: enclosed single-vehicle carrier at ~€1.50/km,
// capital-to-capital straight-line × 1.3 road factor. Verify against live
// carrier quotes for production accuracy.
var defaultTransportCosts = map[string]int64{
	// DE (Berlin) hub
	"DE-FR": 75000, "DE-ES": 150000, "DE-NL": 45000, "DE-BE": 50000, "DE-CH": 60000,
	// FR (Paris) hub
	"FR-DE": 75000, "FR-ES": 90000, "FR-NL": 80000, "FR-BE": 35000, "FR-CH": 60000,
	// ES (Madrid) hub
	"ES-DE": 150000, "ES-FR": 90000, "ES-NL": 180000, "ES-BE": 160000, "ES-CH": 170000,
	// NL (Amsterdam) hub
	"NL-DE": 45000, "NL-FR": 80000, "NL-ES": 180000, "NL-BE": 30000, "NL-CH": 85000,
	// BE (Brussels) hub
	"BE-DE": 50000, "BE-FR": 35000, "BE-ES": 160000, "BE-NL": 30000, "BE-CH": 75000,
	// CH (Zurich) hub
	"CH-DE": 60000, "CH-FR": 60000, "CH-ES": 170000, "CH-NL": 85000, "CH-BE": 75000,
}

// unknownRoutePenaltyCents is charged when a corridor is not in the matrix.
const unknownRoutePenaltyCents int64 = 300000 // €3 000

// TransportCost returns the transport cost in EUR cents from one country to
// another. Same-country moves cost 0; unknown corridors return a €3 000 penalty.
func TransportCost(from, to string) int64 {
	if strings.EqualFold(from, to) {
		return 0
	}
	key := strings.ToUpper(from) + "-" + strings.ToUpper(to)
	if cost, ok := defaultTransportCosts[key]; ok {
		return cost
	}
	return unknownRoutePenaltyCents
}
