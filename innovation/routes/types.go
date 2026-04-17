// Package routes implements the CARDEX Fleet Disposition Intelligence engine.
//
// Given a used vehicle and its current country, the engine computes a ranked
// list of disposition routes — including direct dealer sales, auction, and
// cross-border export — ordered by estimated net profit after transport, VAT
// and customs costs.
//
// The three core components are:
//
//   - SpreadCalculator: queries the live SQLite KG for market prices per country.
//   - Optimizer:        combines market spread, tax costs and transport costs into
//                       a ranked DispositionPlan.
//   - BatchOptimizer:   runs a fleet of vehicles through the optimizer while
//                       enforcing a per-destination concentration cap (default 20%).
package routes

import "time"

// ── Core types ────────────────────────────────────────────────────────────────

// Channel is the disposition channel for a route.
type Channel string

const (
	ChannelDealerDirect Channel = "dealer_direct"
	ChannelAuction      Channel = "auction"
	ChannelExport       Channel = "export"
)

// DispositionRoute is one evaluated destination option for a vehicle.
type DispositionRoute struct {
	FromCountry      string  `json:"from_country"`
	ToCountry        string  `json:"to_country"`
	Channel          Channel `json:"channel"`
	EstimatedPrice   int64   `json:"estimated_price_cents"`   // market median in destination
	VATCost          int64   `json:"vat_cost_cents"`          // irrecoverable VAT/customs
	TransportCost    int64   `json:"transport_cost_cents"`    // logistics cost
	NetProfit        int64   `json:"net_profit_cents"`        // price − VAT − transport
	TimeToSellDays   int     `json:"time_to_sell_days"`
	AvailableDealers int     `json:"available_dealers"`       // active dealers in destination
	Confidence       float64 `json:"confidence"`              // 0–1 based on sample size
	Explanation      string  `json:"explanation"`
}

// DispositionPlan is the full optimization output for one vehicle.
type DispositionPlan struct {
	VehicleVIN     string             `json:"vehicle_vin,omitempty"`
	Make           string             `json:"make"`
	Model          string             `json:"model"`
	Year           int                `json:"year"`
	MileageKm      int                `json:"mileage_km"`
	CurrentCountry string             `json:"current_country"`
	Routes         []DispositionRoute `json:"routes"` // sorted by NetProfit desc
	BestRoute      DispositionRoute   `json:"best_route"`
	TotalUplift    int64              `json:"total_uplift_cents"` // best vs worst local price
	ComputedAt     time.Time          `json:"computed_at"`
}

// OptimizeRequest is the input to Optimizer.Optimize.
type OptimizeRequest struct {
	VehicleVIN     string  `json:"vin,omitempty"`
	Make           string  `json:"make"`
	Model          string  `json:"model"`
	Year           int     `json:"year"`
	MileageKm      int     `json:"mileage_km"`
	FuelType       string  `json:"fuel_type,omitempty"`
	CurrentCountry string  `json:"current_country"`
	Channel        Channel `json:"channel,omitempty"` // optional preferred channel filter
}

// ── Market spread ─────────────────────────────────────────────────────────────

// MarketSpread reports the estimated market price for a vehicle cohort in each country.
type MarketSpread struct {
	Make             string           `json:"make"`
	Model            string           `json:"model"`
	Year             int              `json:"year"`
	FuelType         string           `json:"fuel_type,omitempty"`
	MileageBracket   string           `json:"mileage_bracket"`          // "0-30k" | "30-80k" | "80k+"
	PricesByCountry  map[string]int64 `json:"prices_by_country_cents"`  // country → median EUR cents
	SamplesByCountry map[string]int   `json:"samples_by_country"`
	BestCountry      string           `json:"best_country"`
	WorstCountry     string           `json:"worst_country"`
	SpreadAmount     int64            `json:"spread_amount_cents"` // best − worst
	Confidence       float64          `json:"confidence"`          // 0–1
	ComputedAt       time.Time        `json:"computed_at"`
}

// ── Batch ────────────────────────────────────────────────────────────────────

// VehicleInput describes one vehicle in a batch request.
type VehicleInput struct {
	VIN            string  `json:"vin,omitempty"`
	Make           string  `json:"make"`
	Model          string  `json:"model"`
	Year           int     `json:"year"`
	MileageKm      int     `json:"mileage_km"`
	FuelType       string  `json:"fuel_type,omitempty"`
	CurrentCountry string  `json:"current_country"`
	Channel        Channel `json:"channel,omitempty"`
}

// BatchRouteAssignment maps one vehicle to its assigned DispositionRoute.
type BatchRouteAssignment struct {
	Vehicle       VehicleInput     `json:"vehicle"`
	AssignedRoute DispositionRoute `json:"assigned_route"`
	Rank          int              `json:"rank"` // 1 = best unconstrained, > 1 = capacity fallback
}

// BatchPlan is the full fleet disposition plan.
type BatchPlan struct {
	TotalVehicles         int                    `json:"total_vehicles"`
	Assignments           []BatchRouteAssignment `json:"assignments"`
	TotalEstimatedUplift  int64                  `json:"total_estimated_uplift_cents"`
	AvgUpliftPerVehicle   int64                  `json:"avg_uplift_per_vehicle_cents"`
	ByDestination         map[string]int         `json:"by_destination"`
	CapConstraintApplied  int                    `json:"cap_constraint_applied"` // vehicles rerouted due to cap
	ComputedAt            time.Time              `json:"computed_at"`
}

// ── Gain-share ────────────────────────────────────────────────────────────────

// GainShare computes the CARDEX performance fee on documented uplift.
type GainShare struct {
	ActualSalePrice int64   `json:"actual_sale_price_cents"`
	LocalBaseline   int64   `json:"local_baseline_cents"`
	Uplift          int64   `json:"uplift_cents"`
	FeeRate         float64 `json:"fee_rate"` // e.g. 0.15 = 15%
	Fee             int64   `json:"fee_cents"`
	NetToClient     int64   `json:"net_to_client_cents"` // uplift − fee
}
