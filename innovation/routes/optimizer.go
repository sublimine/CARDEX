package routes

import (
	"database/sql"
	"fmt"
	"sort"
	"strings"
	"time"
)

// Optimizer combines MarketSpread, TaxEngine and TransportMatrix to produce
// a ranked DispositionPlan for a single vehicle.
type Optimizer struct {
	spread    *SpreadCalculator
	transport *TransportMatrix
	tax       TaxEngine
	db        *sql.DB
}

// NewOptimizer constructs an Optimizer. All fields are required.
func NewOptimizer(db *sql.DB, tax TaxEngine, transport *TransportMatrix) *Optimizer {
	return &Optimizer{
		spread:    NewSpreadCalculator(db),
		transport: transport,
		tax:       tax,
		db:        db,
	}
}

// destinations returns the list of target countries to evaluate.
// Includes all 6 supported countries; same-country routes are included as
// "dealer_direct" with zero transport cost.
var allCountries = []string{"DE", "FR", "ES", "NL", "BE", "CH"}

// Optimize computes a DispositionPlan for the given vehicle.
func (o *Optimizer) Optimize(req OptimizeRequest) (*DispositionPlan, error) {
	if req.Make == "" || req.Model == "" || req.Year == 0 {
		return nil, fmt.Errorf("make, model and year are required")
	}
	if req.CurrentCountry == "" {
		return nil, fmt.Errorf("current_country is required")
	}
	from := strings.ToUpper(req.CurrentCountry)

	// Compute market spread across all target countries in one shot.
	mspread, err := o.spread.Calculate(req.Make, req.Model, req.Year, req.MileageKm, req.FuelType)
	if err != nil {
		return nil, fmt.Errorf("spread calculation: %w", err)
	}

	plan := &DispositionPlan{
		VehicleVIN:     req.VehicleVIN,
		Make:           req.Make,
		Model:          req.Model,
		Year:           req.Year,
		MileageKm:      req.MileageKm,
		CurrentCountry: from,
		ComputedAt:     time.Now(),
	}

	// Build a route for every country × channel combination.
	channels := channelsForRequest(req.Channel)
	for _, toCountry := range allCountries {
		price, ok := mspread.PricesByCountry[toCountry]
		if !ok || price == 0 {
			continue // no market data for this destination
		}
		samples := mspread.SamplesByCountry[toCountry]

		for _, ch := range channels {
			// Skip export channel for same-country moves.
			if toCountry == from && ch == ChannelExport {
				continue
			}

			vatCost, err := o.tax.VATCost(from, toCountry, price)
			if err != nil {
				continue // unsupported pair
			}

			transportCost := o.transport.Cost(from, toCountry)
			if ch == ChannelAuction {
				// Auction incurs 3% buyer's premium (deducted from seller perspective).
				transportCost += price * 3 / 100
			}

			netProfit := price - vatCost - transportCost

			dealers, _ := CountActiveDealers(o.db, toCountry)

			ttSell := timeToSellDays(toCountry, ch)

			conf := confidenceFromSamples(samples)

			route := DispositionRoute{
				FromCountry:      from,
				ToCountry:        toCountry,
				Channel:          ch,
				EstimatedPrice:   price,
				VATCost:          vatCost,
				TransportCost:    transportCost,
				NetProfit:        netProfit,
				TimeToSellDays:   ttSell,
				AvailableDealers: dealers,
				Confidence:       conf,
				Explanation:      buildExplanation(from, toCountry, ch, price, vatCost, transportCost, netProfit),
			}
			plan.Routes = append(plan.Routes, route)
		}
	}

	if len(plan.Routes) == 0 {
		return plan, nil
	}

	// Sort by NetProfit descending.
	sort.Slice(plan.Routes, func(i, j int) bool {
		return plan.Routes[i].NetProfit > plan.Routes[j].NetProfit
	})

	plan.BestRoute = plan.Routes[0]

	// TotalUplift: best net profit minus selling locally at whatever price is available.
	if localPrice, ok := mspread.PricesByCountry[from]; ok {
		plan.TotalUplift = plan.BestRoute.NetProfit - localPrice
	}

	return plan, nil
}

// channelsForRequest returns the list of channels to evaluate based on the
// optional preferred channel in the request.
func channelsForRequest(preferred Channel) []Channel {
	if preferred != "" {
		return []Channel{preferred}
	}
	return []Channel{ChannelDealerDirect, ChannelAuction, ChannelExport}
}

// confidenceFromSamples maps a sample count to a [0,1] confidence value.
func confidenceFromSamples(n int) float64 {
	if n <= 0 {
		return 0
	}
	if n >= 50 {
		return 1.0
	}
	// logarithmic ramp: 1→0.13, 5→0.46, 10→0.63, 20→0.78, 50→1.0
	return 1.0 - 1.0/float64(n+1)
}

// buildExplanation creates a human-readable narrative for a route.
func buildExplanation(from, to string, ch Channel, price, vat, transport, net int64) string {
	parts := []string{
		fmt.Sprintf("Market price in %s: €%.0f", to, float64(price)/100),
	}
	if vat > 0 {
		parts = append(parts, fmt.Sprintf("VAT/customs cost: −€%.0f", float64(vat)/100))
	} else {
		parts = append(parts, "Intra-EU reverse charge: €0 VAT")
	}
	if transport > 0 {
		parts = append(parts, fmt.Sprintf("Transport cost: −€%.0f", float64(transport)/100))
	}
	parts = append(parts, fmt.Sprintf("Net profit: €%.0f via %s", float64(net)/100, ch))
	return strings.Join(parts, " | ")
}
