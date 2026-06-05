// Package landedcost computes the total cross-border acquisition cost of a used
// vehicle moved between two CARDEX countries: vehicle price + transport + VAT +
// registration tax + administrative/homologation fees.
//
// Money is handled in EUR cents (int64) to avoid floating-point drift; JSON
// outputs expose rounded EUR floats.
//
// VAT logic is kept consistent with cardex.eu/tax (innovation/tax_engine). The
// registration-tax layer (Spain IEDMT, Netherlands BPM, France malus, Belgium
// BIV/TMC, Switzerland auto tax) is the genuine addition — see registration.go.
// Indicative rate tables are clearly marked and must be reviewed annually.
package landedcost

import "math"

// adminFeesCents is a flat estimate of registration/homologation administrative
// costs per destination country (plates, inspection, paperwork). Indicative.
var adminFeesCents = map[string]int64{
	"DE": 15000, // €150 Zulassung + plates
	"FR": 25000, // €250 carte grise admin + quitus fiscal
	"ES": 10000, // €100 matriculación + ITV
	"NL": 15000, // €150 RDW registration + keuring
	"BE": 12000, // €120 DIV registration + keuring
	"CH": 40000, // €400 customs clearance + MFK inspection
}

const defaultAdminFeesCents int64 = 15000

// Breakdown is the itemized landed-cost result. EUR fields are rounded to cents.
type Breakdown struct {
	FromCountry        string  `json:"from_country"`
	ToCountry          string  `json:"to_country"`
	VehiclePriceEUR    float64 `json:"vehicle_price_eur"`
	TransportEUR       float64 `json:"transport_eur"`
	VATEUR             float64 `json:"vat_eur"`
	VATNote            string  `json:"vat_note"`
	RegistrationTaxEUR float64 `json:"registration_tax_eur"`
	RegistrationMethod string  `json:"registration_method"`
	RegistrationNote   string  `json:"registration_note"`
	AdminFeesEUR       float64 `json:"admin_fees_eur"`
	TotalLandedCostEUR float64 `json:"total_landed_cost_eur"`
	IsNewVehicle       bool    `json:"is_new_vehicle"`
}

// Compute returns the full landed-cost breakdown for moving a vehicle from
// fromCountry to toCountry. opts tunes country-specific behavior (e.g. BE region).
func Compute(fromCountry, toCountry string, v Vehicle, opts RegistrationOptions) Breakdown {
	transport := TransportCost(fromCountry, toCountry)
	newVeh := IsNewVehicle(v.AgeMonths, v.Km)
	vatCents, vatNote := VATCost(fromCountry, toCountry, v.PriceCents, newVeh)
	reg := RegistrationTax(toCountry, v, opts)
	admin := adminFeesFor(toCountry)

	total := v.PriceCents + transport + vatCents + reg.TaxCents + admin

	return Breakdown{
		FromCountry:        normCountry(fromCountry),
		ToCountry:          normCountry(toCountry),
		VehiclePriceEUR:    centsToEUR(v.PriceCents),
		TransportEUR:       centsToEUR(transport),
		VATEUR:             centsToEUR(vatCents),
		VATNote:            vatNote,
		RegistrationTaxEUR: centsToEUR(reg.TaxCents),
		RegistrationMethod: reg.Method,
		RegistrationNote:   reg.Note,
		AdminFeesEUR:       centsToEUR(admin),
		TotalLandedCostEUR: centsToEUR(total),
		IsNewVehicle:       newVeh,
	}
}

// adminFeesFor returns the admin fee for a destination, or the default.
func adminFeesFor(country string) int64 {
	if c, ok := adminFeesCents[normCountry(country)]; ok {
		return c
	}
	return defaultAdminFeesCents
}

// --- money helpers ---

// pctOfCents returns frac (a fraction, e.g. 0.0475) of a cents amount, rounded.
func pctOfCents(cents int64, frac float64) int64 {
	return int64(math.Round(float64(cents) * frac))
}

// centsToEUR converts cents to a EUR float rounded to 2 decimals.
func centsToEUR(cents int64) float64 {
	return math.Round(float64(cents)) / 100.0
}

// normCountry upper-cases a country code.
func normCountry(c string) string {
	if len(c) == 2 {
		return string([]byte{upper(c[0]), upper(c[1])})
	}
	return c
}

func upper(b byte) byte {
	if b >= 'a' && b <= 'z' {
		return b - 32
	}
	return b
}
