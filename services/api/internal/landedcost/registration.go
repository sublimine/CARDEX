package landedcost

import (
	"fmt"
	"math"
	"strings"
)

// Fuel is a normalized fuel category used by registration-tax formulas.
type Fuel string

const (
	FuelPetrol   Fuel = "PETROL"
	FuelDiesel   Fuel = "DIESEL"
	FuelElectric Fuel = "ELECTRIC"
	FuelHybrid   Fuel = "HYBRID"
	FuelLPG      Fuel = "LPG"
	FuelCNG      Fuel = "CNG"
	FuelUnknown  Fuel = ""
)

// NormalizeFuel maps a free-text fuel string to a Fuel category.
func NormalizeFuel(s string) Fuel {
	s = strings.ToLower(strings.TrimSpace(s))
	switch {
	case s == "":
		return FuelUnknown
	case strings.Contains(s, "elect") || s == "ev" || s == "bev":
		return FuelElectric
	case strings.Contains(s, "hybrid") || s == "phev" || s == "hev":
		return FuelHybrid
	case strings.Contains(s, "diesel") || strings.Contains(s, "gasoil") || strings.Contains(s, "tdi"):
		return FuelDiesel
	case strings.Contains(s, "lpg") || strings.Contains(s, "gpl"):
		return FuelLPG
	case strings.Contains(s, "cng") || strings.Contains(s, "gnc"):
		return FuelCNG
	case strings.Contains(s, "petrol") || strings.Contains(s, "gasol") ||
		strings.Contains(s, "benz") || strings.Contains(s, "essence") || strings.Contains(s, "tsi"):
		return FuelPetrol
	default:
		return FuelPetrol
	}
}

// Vehicle is the input to registration-tax and landed-cost calculations.
type Vehicle struct {
	// PriceCents is the listing/purchase price in EUR cents.
	PriceCents int64
	// CO2gkm is WLTP CO2 emissions in g/km (0 = unknown).
	CO2gkm int
	// Fuel is the fuel category.
	Fuel Fuel
	// AgeMonths is months since first registration (0 = unknown).
	AgeMonths int
	// Km is odometer reading in kilometers (0 = unknown), used for the EU
	// "new means of transport" VAT test.
	Km int
	// PowerKW is engine power in kilowatts (0 = unknown).
	PowerKW int
}

// RegistrationResult is a single country's one-time registration-tax outcome.
type RegistrationResult struct {
	Country string `json:"country"`
	// TaxCents is the one-time registration / CO2 tax in EUR cents.
	TaxCents int64 `json:"tax_cents"`
	// Method names the scheme applied (e.g. "ES_IEDMT", "NL_BPM").
	Method string `json:"method"`
	// Note explains the calculation and any caveats.
	Note string `json:"note"`
}

// BERegion selects which Belgian regional registration-tax scheme to apply.
type BERegion string

const (
	BEFlanders BERegion = "FLANDERS"
	BEWallonia BERegion = "WALLONIA"
	BEBrussels BERegion = "BRUSSELS"
)

// RegistrationOptions tunes country-specific behavior.
type RegistrationOptions struct {
	// BERegion selects the Belgian scheme (default Flanders).
	BERegion BERegion
}

// RegistrationTax computes the one-time registration tax owed when registering a
// vehicle in destCountry. Schemes:
//   - DE: none for intra-EU transfers (annual Kfz-Steuer is recurring, excluded).
//   - ES: IEDMT (CO2 bands) — precise, stable bands.
//   - CH: federal automobile tax 4% on import value — precise.
//   - NL: BPM (CO2 brackets + diesel surcharge − age depreciation) — indicative model.
//   - FR: CO2 malus (with used-vehicle abatement) — indicative model.
//   - BE: BIV/TMC (Flanders CO2 formula or Wallonia/Brussels power table) — indicative model.
//
// Indicative models implement the correct *mechanism* with documented rate tables
// that must be reviewed against official sources annually (changes usually take
// effect 1 January).
func RegistrationTax(destCountry string, v Vehicle, opts RegistrationOptions) RegistrationResult {
	c := strings.ToUpper(destCountry)
	switch c {
	case "DE":
		return RegistrationResult{Country: c, TaxCents: 0, Method: "DE_NONE",
			Note: "No one-time registration tax for intra-EU transfers; annual Kfz-Steuer is recurring and excluded from landed cost."}
	case "ES":
		return esIEDMT(c, v)
	case "NL":
		return nlBPM(c, v)
	case "FR":
		return frMalus(c, v)
	case "BE":
		return beRegistration(c, v, opts.BERegion)
	case "CH":
		return chImportTax(c, v)
	default:
		return RegistrationResult{Country: c, TaxCents: 0, Method: "UNKNOWN",
			Note: "Registration tax not modeled for this country."}
	}
}

// --- Spain: IEDMT (Impuesto Especial sobre Determinados Medios de Transporte) ---
//
// CO2-band rates applied to the taxable value (mainland; Canarias/Ceuta differ).
// Bands are stable across years. For used vehicles the official base uses BOE
// depreciation tables; here the rate is applied to the provided market value,
// which is a close approximation for a used listing price.
func esIEDMT(c string, v Vehicle) RegistrationResult {
	var rate float64
	switch {
	case v.CO2gkm <= 120:
		rate = 0.0
	case v.CO2gkm <= 160:
		rate = 0.0475
	case v.CO2gkm <= 200:
		rate = 0.0975
	default:
		rate = 0.1475
	}
	note := fmt.Sprintf("IEDMT %.2f%% (CO2 %d g/km band) on value", rate*100, v.CO2gkm)
	if v.CO2gkm == 0 {
		note = "IEDMT 0% — CO2 unknown, assumed lowest band; verify emissions"
	}
	return RegistrationResult{Country: c, TaxCents: pctOfCents(v.PriceCents, rate), Method: "ES_IEDMT", Note: note}
}

// --- Switzerland: federal automobile tax on import ---
//
// 4% automobile tax (Automobilsteuer) on the import value. Import VAT (8.1%) is
// handled by the VAT layer; cantonal road tax is recurring and excluded.
func chImportTax(c string, v Vehicle) RegistrationResult {
	tax := pctOfCents(v.PriceCents, 0.04)
	return RegistrationResult{Country: c, TaxCents: tax, Method: "CH_AUTO_TAX",
		Note: "Swiss federal automobile tax 4% on import value (import VAT handled separately; customs duty by weight not included)."}
}

// --- Netherlands: BPM ---
//
// BPM = fixed base + progressive CO2 bracket tariff (+ diesel surcharge),
// reduced by an age-based depreciation fraction for used imports. Bracket/base
// figures below are indicative 2025 values — VERIFY against the Belastingdienst
// BPM tariff table; they change annually.
var nlBPMBaseCents int64 = 44000 // €440 fixed component (indicative 2025)

// nlBPMBracket is a marginal CO2 bracket: grams up to Upper are charged RateCents/g.
type nlBPMBracket struct {
	Upper     int   // inclusive upper CO2 g/km bound for this bracket
	RateCents int64 // EUR cents per g/km within the bracket
}

var nlBPMBrackets = []nlBPMBracket{
	{Upper: 79, RateCents: 200},              // €2/g
	{Upper: 101, RateCents: 7800},            // €78/g
	{Upper: 144, RateCents: 17000},           // €170/g
	{Upper: 157, RateCents: 28000},           // €280/g
	{Upper: math.MaxInt32, RateCents: 56100}, // €561/g
}

// nlDieselSurchargePerGCents applies above the diesel threshold.
const (
	nlDieselThreshold        = 70
	nlDieselSurchargePerGram = 10918 // €109.18 per g/km above threshold (indicative 2025)
)

func nlBPM(c string, v Vehicle) RegistrationResult {
	if v.Fuel == FuelElectric {
		return RegistrationResult{Country: c, TaxCents: 0, Method: "NL_BPM",
			Note: "BPM €0 — fully electric vehicles are exempt."}
	}
	gross := nlBPMBaseCents
	prev := 0
	for _, b := range nlBPMBrackets {
		if v.CO2gkm <= prev {
			break
		}
		upper := b.Upper
		if v.CO2gkm < upper {
			upper = v.CO2gkm
		}
		grams := int64(upper - prev)
		gross += grams * b.RateCents
		prev = b.Upper
	}
	if v.Fuel == FuelDiesel && v.CO2gkm > nlDieselThreshold {
		gross += int64(v.CO2gkm-nlDieselThreshold) * nlDieselSurchargePerGram
	}

	remaining := depreciationRemaining(v.AgeMonths)
	tax := int64(math.Round(float64(gross) * remaining))
	note := fmt.Sprintf("BPM gross €%.0f × %.0f%% remaining (age %d mo) — indicative 2025 table",
		float64(gross)/100, remaining*100, v.AgeMonths)
	if v.CO2gkm == 0 {
		note = "BPM uses CO2=0 (unknown) → base only; provide CO2 for an accurate figure"
	}
	return RegistrationResult{Country: c, TaxCents: tax, Method: "NL_BPM", Note: note}
}

// depreciationRemaining approximates the Belastingdienst BPM afschrijvingstabel:
// the fraction of gross BPM still due, by months since first registration. Linear
// interpolation between documented breakpoints; clamps to [0,1]. Vehicles ≥ 25y
// (300 months) are exempt. Indicative — verify against the official table.
func depreciationRemaining(ageMonths int) float64 {
	if ageMonths <= 0 {
		return 1.0
	}
	type pt struct {
		m    int
		frac float64
	}
	table := []pt{
		{0, 1.00}, {1, 0.92}, {3, 0.79}, {5, 0.71}, {6, 0.69}, {9, 0.63},
		{12, 0.58}, {18, 0.48}, {24, 0.42}, {36, 0.33}, {48, 0.26}, {60, 0.20},
		{72, 0.16}, {96, 0.10}, {120, 0.06}, {300, 0.0},
	}
	if ageMonths >= 300 {
		return 0.0
	}
	for i := 1; i < len(table); i++ {
		if ageMonths <= table[i].m {
			lo, hi := table[i-1], table[i]
			span := float64(hi.m - lo.m)
			if span == 0 {
				return lo.frac
			}
			t := float64(ageMonths-lo.m) / span
			return lo.frac + t*(hi.frac-lo.frac)
		}
	}
	return 0.0
}

// --- France: CO2 malus écologique (+ used-vehicle abatement) ---
//
// One-time CO2 malus at first French registration (WLTP). Anchored to indicative
// 2025 grid points with linear interpolation; €0 below 113 g/km, capped at
// €70 000 from 193 g/km. Used imports get a 10%/started-year abatement. The
// regional carte grise fee is modeled as a flat admin cost (see AdminFees), not
// here. VERIFY the grid annually.
type frMalusPoint struct {
	co2  int
	cent int64
}

var frMalusGrid = []frMalusPoint{
	{112, 0}, {113, 5000}, {120, 26000}, {130, 98300}, {140, 190100},
	{150, 311900}, {160, 510500}, {170, 877000}, {180, 1626000},
	{190, 4044300}, {193, 7000000},
}

const frMalusCapCents int64 = 7000000 // €70 000

func frMalus(c string, v Vehicle) RegistrationResult {
	if v.Fuel == FuelElectric {
		return RegistrationResult{Country: c, TaxCents: 0, Method: "FR_MALUS",
			Note: "Malus €0 — electric vehicles are exempt."}
	}
	gross := interpMalus(v.CO2gkm)
	years := v.AgeMonths / 12
	abate := 1.0 - 0.10*float64(years)
	if abate < 0 {
		abate = 0
	}
	tax := int64(math.Round(float64(gross) * abate))
	note := fmt.Sprintf("CO2 malus €%.0f × %.0f%% (used abatement, age %d mo) — indicative 2025 grid",
		float64(gross)/100, abate*100, v.AgeMonths)
	if v.CO2gkm == 0 {
		note = "Malus €0 — CO2 unknown; provide emissions for an accurate figure"
	}
	return RegistrationResult{Country: c, TaxCents: tax, Method: "FR_MALUS", Note: note}
}

// interpMalus linearly interpolates the malus grid (EUR cents) for a CO2 value.
func interpMalus(co2 int) int64 {
	if co2 <= frMalusGrid[0].co2 {
		return 0
	}
	last := frMalusGrid[len(frMalusGrid)-1]
	if co2 >= last.co2 {
		return frMalusCapCents
	}
	for i := 1; i < len(frMalusGrid); i++ {
		if co2 <= frMalusGrid[i].co2 {
			lo, hi := frMalusGrid[i-1], frMalusGrid[i]
			span := float64(hi.co2 - lo.co2)
			t := float64(co2-lo.co2) / span
			return lo.cent + int64(math.Round(t*float64(hi.cent-lo.cent)))
		}
	}
	return frMalusCapCents
}

// --- Belgium: BIV (Flanders) / TMC (Wallonia, Brussels) ---
//
// Flanders uses a CO2/fuel formula; Wallonia & Brussels use a power-based table.
// Both apply an age reduction. Indicative models — VERIFY annually.
func beRegistration(c string, v Vehicle, region BERegion) RegistrationResult {
	if region == "" {
		region = BEFlanders
	}
	switch region {
	case BEWallonia, BEBrussels:
		return beTMCPowerTable(c, v, region)
	default:
		return beFlandersBIV(c, v)
	}
}

// beFlandersBIV implements the Flanders CO2 formula:
//
//	BIV = 4500 × ((CO2·f + x) / 246)^6, with a regulatory floor, then age reduction.
//
// Petrol f=1,x=0; diesel adds a particulate component. Euro-6 assumed.
func beFlandersBIV(c string, v Vehicle) RegistrationResult {
	const floorCents int64 = 5150 // €51.50 minimum (indicative)
	if v.Fuel == FuelElectric || v.CO2gkm == 0 {
		note := "BIV €51.50 — Flanders minimum (electric/zero-emission)"
		if v.CO2gkm == 0 && v.Fuel != FuelElectric {
			note = "BIV €51.50 floor — CO2 unknown; provide emissions for an accurate figure"
		}
		return RegistrationResult{Country: c, TaxCents: floorCents, Method: "BE_BIV_FLANDERS", Note: note}
	}
	f, x := 1.0, 0.0
	if v.Fuel == FuelDiesel {
		x = 500.0 // diesel particulate addend (indicative)
	}
	base := 4500.0 * math.Pow((float64(v.CO2gkm)*f+x)/246.0, 6)
	gross := int64(math.Round(base * 100))
	if gross < floorCents {
		gross = floorCents
	}
	remaining := beAgeRemaining(v.AgeMonths)
	tax := int64(math.Round(float64(gross) * remaining))
	if tax < floorCents {
		tax = floorCents
	}
	note := fmt.Sprintf("Flanders BIV €%.0f × %.0f%% (age %d mo) — indicative formula",
		float64(gross)/100, remaining*100, v.AgeMonths)
	return RegistrationResult{Country: c, TaxCents: tax, Method: "BE_BIV_FLANDERS", Note: note}
}

// beTMCPowerTable implements the Wallonia/Brussels power-based TMC table with age
// reduction. Bands keyed on kW (mapped from fiscal horsepower). Indicative 2025.
func beTMCPowerTable(c string, v Vehicle, region BERegion) RegistrationResult {
	type band struct {
		maxKW int
		cents int64
	}
	bands := []band{
		{70, 6150}, {85, 12300}, {100, 49500}, {110, 86700},
		{120, 123900}, {155, 247800}, {math.MaxInt32, 495700},
	}
	gross := bands[len(bands)-1].cents
	for _, b := range bands {
		if v.PowerKW <= b.maxKW {
			gross = b.cents
			break
		}
	}
	const floorCents int64 = 6150 // €61.50 minimum
	remaining := beAgeRemaining(v.AgeMonths)
	tax := int64(math.Round(float64(gross) * remaining))
	if tax < floorCents {
		tax = floorCents
	}
	note := fmt.Sprintf("%s TMC €%.0f (%d kW) × %.0f%% (age %d mo) — indicative table",
		region, float64(gross)/100, v.PowerKW, remaining*100, v.AgeMonths)
	return RegistrationResult{Country: c, TaxCents: tax, Method: "BE_TMC_" + string(region), Note: note}
}

// beAgeRemaining returns the BIV/TMC remaining fraction by age: 10% reduction per
// started year, floored at 10% remaining. Indicative.
func beAgeRemaining(ageMonths int) float64 {
	years := ageMonths / 12
	rem := 1.0 - 0.10*float64(years)
	if rem < 0.10 {
		rem = 0.10
	}
	return rem
}
