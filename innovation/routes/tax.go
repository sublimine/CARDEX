package routes

import (
	"fmt"
	"strings"
)

// TaxEngine computes the irrecoverable VAT/customs cost for a cross-border
// vehicle transaction. The "irrecoverable" part is what matters for net profit:
// intra-EU reverse charge has a cash cost of €0 for a VAT-registered B2B buyer.
type TaxEngine interface {
	VATCost(fromCountry, toCountry string, vehiclePriceCents int64) (int64, error)
}

// euCountries is the EU subset of the 6-country matrix.
var euCountries = map[string]bool{
	"DE": true, "FR": true, "ES": true, "BE": true, "NL": true,
}

// nationalVATRates mirrors cardex.eu/tax.NationalVATRates.
var nationalVATRates = map[string]float64{
	"DE": 0.19,
	"FR": 0.20,
	"ES": 0.21,
	"BE": 0.21,
	"NL": 0.21,
	"CH": 0.081,
}

// chCustomsFixedCents is the fixed customs clearance fee (documentation,
// broker, T1 transit) for an EU→CH vehicle import. This does not include
// Swiss import duty (currently €0 for passenger cars under FTA CH-EU 2002).
const chCustomsFixedCents = 50000 // €500

// DefaultTaxEngine implements TaxEngine using the same logic as cardex.eu/tax.
//
// Rules:
//   - Same country:          €0  (no cross-border VAT event)
//   - EU → EU (used B2B):    €0  (Art. 20/138 reverse charge, valid VAT IDs assumed)
//   - EU → CH:               Swiss MWST 8.1% on import value + €500 fixed customs
//   - CH → EU:               destination EU VAT on import value + €400 customs
type DefaultTaxEngine struct{}

// VATCost returns the irrecoverable cash VAT/customs cost in EUR cents.
func (e *DefaultTaxEngine) VATCost(fromCountry, toCountry string, vehiclePriceCents int64) (int64, error) {
	from := strings.ToUpper(fromCountry)
	to := strings.ToUpper(toCountry)

	if from == to {
		return 0, nil
	}

	fromEU := euCountries[from]
	toEU := euCountries[to]

	switch {
	case fromEU && toEU:
		// Intra-EU B2B used vehicle: reverse charge → buyer deducts, cash cost = 0.
		return 0, nil

	case fromEU && to == "CH":
		// Export from EU to Switzerland:
		//   - Swiss MWST at 8.1% applies on the customs value (invoice price).
		//   - VAT is recoverable for a Swiss VAT-registered dealer: net cash = 0 in theory.
		//   - In practice, cash-flow impact + risk of non-recovery = treated as partial cost.
		//   - We model the import VAT as irrecoverable (conservative) + fixed customs.
		vatAmount := int64(float64(vehiclePriceCents) * nationalVATRates["CH"])
		return vatAmount + chCustomsFixedCents, nil

	case from == "CH" && toEU:
		// Import from CH to EU:
		//   - Destination EU VAT applies on customs value.
		//   - Fixed customs clearance €400.
		rate, ok := nationalVATRates[to]
		if !ok {
			return 0, fmt.Errorf("unknown EU country %q", to)
		}
		vatAmount := int64(float64(vehiclePriceCents) * rate)
		return vatAmount + 40000, nil

	default:
		return 0, fmt.Errorf("unsupported country pair: %s → %s", from, to)
	}
}

// NewDefaultTaxEngine returns a DefaultTaxEngine ready for use.
func NewDefaultTaxEngine() TaxEngine { return &DefaultTaxEngine{} }
