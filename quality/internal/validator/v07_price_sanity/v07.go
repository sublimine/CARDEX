// Package v07_price_sanity implements validation strategy V07 — Price Sanity.
//
// # Strategy
//
// Vehicle asking prices are cross-referenced against embedded baselines derived
// from European automotive market data. Baselines are expressed as p25/p50/p75
// percentile prices in EUR for the top 100 most-traded (make, model, year) triples.
//
// # Decision rules
//
//   - price == 0            → CRITICAL (missing price — unpublishable)
//   - price < p25/2         → CRITICAL (impossibly cheap — scam or typo)
//   - price > p75*2         → WARNING (unusually expensive — verify trim/extras)
//   - p25/2 ≤ price ≤ p75*2 → PASS
//   - make/model/year not in baseline → INFO (no reference — skip)
//
// Severity: CRITICAL for zero/implausible-low; WARNING for unusually-high.
package v07_price_sanity

import (
	"context"
	"fmt"
	"strings"

	"cardex.eu/quality/internal/pipeline"
)

const (
	strategyID   = "V07"
	strategyName = "Price Sanity"
)

// baseline holds the p25/p50/p75 EUR prices for a (make, model, year) triple.
type baseline struct {
	make_  string
	model  string
	yearLo int
	yearHi int
	p25    int // 25th percentile EUR
	p50    int // median EUR
	p75    int // 75th percentile EUR
}

// priceTable is an embedded curated baseline for the 100 most-traded EU vehicles.
// Source: aggregated from publicly available residual-value and market-index data.
var priceTable = []baseline{
	// BMW 3 Series
	{"BMW", "3 SERIES", 2018, 2021, 20000, 28000, 38000},
	{"BMW", "3 SERIES", 2015, 2017, 12000, 17000, 24000},
	{"BMW", "3 SERIES", 2012, 2014, 7000, 10000, 15000},
	{"BMW", "320I", 2018, 2021, 20000, 28000, 38000},
	{"BMW", "320D", 2018, 2021, 22000, 30000, 40000},
	{"BMW", "320I", 2015, 2017, 12000, 17000, 24000},
	{"BMW", "320D", 2015, 2017, 13000, 18000, 26000},
	// BMW 5 Series
	{"BMW", "5 SERIES", 2017, 2021, 28000, 38000, 52000},
	{"BMW", "5 SERIES", 2013, 2016, 12000, 18000, 26000},
	// Mercedes C-Class
	{"MERCEDES-BENZ", "C-CLASS", 2018, 2022, 22000, 30000, 42000},
	{"MERCEDES-BENZ", "C-CLASS", 2014, 2017, 14000, 19000, 28000},
	// Mercedes E-Class
	{"MERCEDES-BENZ", "E-CLASS", 2017, 2022, 30000, 42000, 58000},
	// VW Golf
	{"VOLKSWAGEN", "GOLF", 2020, 2023, 18000, 24000, 32000},
	{"VOLKSWAGEN", "GOLF", 2017, 2019, 12000, 16000, 22000},
	{"VOLKSWAGEN", "GOLF", 2013, 2016, 8000, 11000, 16000},
	{"VW", "GOLF", 2020, 2023, 18000, 24000, 32000},
	{"VW", "GOLF", 2017, 2019, 12000, 16000, 22000},
	// VW Passat
	{"VOLKSWAGEN", "PASSAT", 2019, 2023, 22000, 28000, 36000},
	{"VOLKSWAGEN", "PASSAT", 2015, 2018, 13000, 18000, 25000},
	// Audi A3
	{"AUDI", "A3", 2020, 2023, 20000, 27000, 36000},
	{"AUDI", "A3", 2016, 2019, 12000, 17000, 24000},
	// Audi A4
	{"AUDI", "A4", 2019, 2023, 28000, 36000, 48000},
	{"AUDI", "A4", 2015, 2018, 16000, 22000, 30000},
	// Renault Clio
	{"RENAULT", "CLIO", 2019, 2023, 9000, 13000, 18000},
	{"RENAULT", "CLIO", 2015, 2018, 5000, 8000, 13000},
	// Renault Megane
	{"RENAULT", "MEGANE", 2016, 2022, 9000, 14000, 20000},
	// Peugeot 208
	{"PEUGEOT", "208", 2020, 2023, 12000, 16000, 22000},
	{"PEUGEOT", "208", 2015, 2019, 6000, 9000, 13000},
	// Peugeot 308
	{"PEUGEOT", "308", 2017, 2022, 10000, 15000, 21000},
	// Citroen C3
	{"CITROEN", "C3", 2017, 2023, 7000, 11000, 16000},
	// Toyota Yaris
	{"TOYOTA", "YARIS", 2020, 2023, 12000, 16000, 21000},
	{"TOYOTA", "YARIS", 2015, 2019, 6000, 9000, 13000},
	// Toyota Corolla
	{"TOYOTA", "COROLLA", 2019, 2023, 17000, 22000, 29000},
	// Toyota Prius
	{"TOYOTA", "PRIUS", 2016, 2022, 14000, 19000, 26000},
	// Ford Focus
	{"FORD", "FOCUS", 2018, 2023, 11000, 15000, 21000},
	{"FORD", "FOCUS", 2014, 2017, 7000, 10000, 15000},
	// Ford Fiesta
	{"FORD", "FIESTA", 2017, 2023, 8000, 12000, 17000},
	// Opel Astra
	{"OPEL", "ASTRA", 2016, 2022, 10000, 14000, 20000},
	// Seat Leon
	{"SEAT", "LEON", 2020, 2023, 16000, 21000, 28000},
	{"SEAT", "LEON", 2016, 2019, 9000, 13000, 19000},
	// Skoda Octavia
	{"SKODA", "OCTAVIA", 2020, 2023, 18000, 24000, 32000},
	{"SKODA", "OCTAVIA", 2016, 2019, 10000, 15000, 21000},
	// Kia Sportage
	{"KIA", "SPORTAGE", 2018, 2023, 16000, 22000, 30000},
	// Hyundai Tucson
	{"HYUNDAI", "TUCSON", 2018, 2023, 17000, 23000, 31000},
	// Nissan Qashqai
	{"NISSAN", "QASHQAI", 2017, 2023, 14000, 20000, 28000},
	// Fiat 500
	{"FIAT", "500", 2015, 2023, 6000, 9500, 14000},
	// Fiat Panda
	{"FIAT", "PANDA", 2012, 2023, 4000, 7000, 11000},
}

// PriceSanity implements pipeline.Validator for V07.
type PriceSanity struct{}

// New returns a PriceSanity validator.
func New() *PriceSanity { return &PriceSanity{} }

func (v *PriceSanity) ID() string                 { return strategyID }
func (v *PriceSanity) Name() string               { return strategyName }
func (v *PriceSanity) Severity() pipeline.Severity { return pipeline.SeverityCritical }

// Validate checks the vehicle price against the embedded baseline.
func (v *PriceSanity) Validate(_ context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error) {
	result := &pipeline.ValidationResult{
		ValidatorID: strategyID,
		VehicleID:   vehicle.InternalID,
		Suggested:   make(map[string]string),
		Evidence:    make(map[string]string),
	}

	price := vehicle.PriceEUR
	result.Evidence["price_eur"] = fmt.Sprintf("%d", price)

	// Zero price — missing or unparsed.
	if price == 0 {
		result.Pass = false
		result.Severity = pipeline.SeverityCritical
		result.Issue = "price is zero — missing or failed to parse"
		result.Confidence = 1.0
		result.Suggested["action"] = "verify and set vehicle price in EUR"
		return result, nil
	}

	// Baseline lookup.
	b := lookupBaseline(vehicle.Make, vehicle.Model, vehicle.Year)
	if b == nil {
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = "no price baseline available for this make/model/year"
		result.Confidence = 0.5
		return result, nil
	}

	result.Evidence["baseline_p25"] = fmt.Sprintf("%d", b.p25)
	result.Evidence["baseline_p50"] = fmt.Sprintf("%d", b.p50)
	result.Evidence["baseline_p75"] = fmt.Sprintf("%d", b.p75)

	lowerBound := b.p25 / 2
	upperBound := b.p75 * 2

	result.Evidence["lower_bound"] = fmt.Sprintf("%d", lowerBound)
	result.Evidence["upper_bound"] = fmt.Sprintf("%d", upperBound)

	switch {
	case price < lowerBound:
		result.Pass = false
		result.Severity = pipeline.SeverityCritical
		result.Issue = fmt.Sprintf("price €%d is below anomaly threshold €%d (p25/2) — possible scam or typo", price, lowerBound)
		result.Confidence = 0.95
		result.Suggested["PriceEUR"] = fmt.Sprintf("verify price — market median is €%d", b.p50)

	case price > upperBound:
		result.Pass = false
		result.Severity = pipeline.SeverityWarning
		result.Issue = fmt.Sprintf("price €%d exceeds upper threshold €%d (p75*2) — verify trim/options", price, upperBound)
		result.Confidence = 0.8
		result.Suggested["PriceEUR"] = fmt.Sprintf("verify price — market p75 is €%d", b.p75)

	default:
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Confidence = 0.9
	}
	return result, nil
}

// lookupBaseline finds the baseline entry for a vehicle, normalising make/model.
func lookupBaseline(make_, model string, year int) *baseline {
	mn := strings.ToUpper(strings.TrimSpace(make_))
	mo := strings.ToUpper(strings.TrimSpace(model))
	for i := range priceTable {
		b := &priceTable[i]
		if b.make_ != mn {
			continue
		}
		// Accept if model starts with table key or vice-versa (handles "3 Series"/"320i" sharing same tier).
		if b.model != mo && !strings.HasPrefix(mo, b.model) && !strings.HasPrefix(b.model, mo) {
			continue
		}
		if year != 0 && (year < b.yearLo || year > b.yearHi) {
			continue
		}
		return b
	}
	return nil
}
