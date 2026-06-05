package landedcost

import "strings"

// NationalVATRates is the standard VAT rate per country, as a fraction.
//
// Mirrors cardex.eu/tax NationalVATRates (innovation/tax_engine/rules.go) so the
// two engines never diverge. CH is the Swiss MWST rate (8.1% since 2024). These
// change by national budget — verify annually (usually effective 1 January).
var NationalVATRates = map[string]float64{
	"DE": 0.19,
	"FR": 0.20,
	"ES": 0.21,
	"BE": 0.21,
	"NL": 0.21,
	"CH": 0.081,
}

// euCountries is the set of EU member states CARDEX covers (CH is not EU).
var euCountries = map[string]bool{
	"DE": true, "FR": true, "ES": true, "BE": true, "NL": true,
}

// IsEU reports whether a country code is an EU member CARDEX covers.
func IsEU(country string) bool { return euCountries[strings.ToUpper(country)] }

// EU "new means of transport" thresholds (VAT Directive Art. 2(2)(b)): a vehicle
// is "new" if not older than 6 months OR with no more than 6 000 km. New
// vehicles owe destination-country VAT on intra-EU acquisition.
const (
	newVehicleMaxAgeMonths = 6
	newVehicleMaxKm        = 6000
)

// IsNewVehicle applies the Art. 2(2)(b) test. Zero values are treated as unknown
// (not triggering the rule).
func IsNewVehicle(ageMonths, km int) bool {
	if ageMonths > 0 && ageMonths <= newVehicleMaxAgeMonths {
		return true
	}
	if km > 0 && km <= newVehicleMaxKm {
		return true
	}
	return false
}

// VATCost returns the additional VAT cash cost (EUR cents) of moving a vehicle
// from one country to another, plus a human explanation.
//
// Model (dealer/importer perspective — the *added* irrecoverable VAT):
//   - Intra-EU, used vehicle  → 0 (margin scheme / B2B reverse charge; VAT, if any,
//     is already embedded in the listing price and recoverable for VAT-registered
//     dealers). Consistent with cardex.eu/routes DefaultTaxEngine.
//   - Intra-EU, new vehicle   → destination-country VAT on the full price.
//   - EU → CH                 → Swiss import VAT (MWST 8.1%).
//   - CH → EU                 → destination-country import VAT on the full price.
func VATCost(from, to string, priceCents int64, newVehicle bool) (int64, string) {
	from = strings.ToUpper(from)
	to = strings.ToUpper(to)
	switch {
	case IsEU(from) && IsEU(to):
		if newVehicle {
			return pctOfCents(priceCents, NationalVATRates[to]),
				"Intra-EU new vehicle: destination VAT due on full price"
		}
		return 0, "Intra-EU used vehicle: margin scheme / B2B reverse charge (no added VAT)"
	case IsEU(from) && to == "CH":
		return pctOfCents(priceCents, NationalVATRates["CH"]),
			"Import to Switzerland: import VAT (MWST 8.1%)"
	case from == "CH" && IsEU(to):
		return pctOfCents(priceCents, NationalVATRates[to]),
			"Import from Switzerland to EU: destination import VAT on full price"
	default:
		return 0, "VAT not modeled for this corridor"
	}
}
