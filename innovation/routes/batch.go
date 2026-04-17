package routes

import (
	"fmt"
	"sort"
	"time"
)

const defaultMaxFraction = 0.20 // max 20% of fleet to a single destination

// BatchOptimizer runs a fleet of vehicles through the Optimizer while
// enforcing a per-destination concentration cap.
//
// Algorithm:
//  1. For each vehicle, compute its full DispositionPlan.
//  2. Assign the best route whose destination is not yet at capacity.
//  3. If all destinations are at capacity, assign the best unconstrained route
//     (the constraint is advisory, not hard, for small fleets).
type BatchOptimizer struct {
	optimizer   *Optimizer
	maxFraction float64 // per-destination cap, e.g. 0.20
}

// NewBatchOptimizer constructs a BatchOptimizer with the given per-destination cap.
// maxFraction of 0 uses the default (20%).
func NewBatchOptimizer(opt *Optimizer, maxFraction float64) *BatchOptimizer {
	if maxFraction <= 0 || maxFraction > 1 {
		maxFraction = defaultMaxFraction
	}
	return &BatchOptimizer{optimizer: opt, maxFraction: maxFraction}
}

// Optimize computes the fleet-level disposition plan.
func (bo *BatchOptimizer) Optimize(vehicles []VehicleInput) (*BatchPlan, error) {
	if len(vehicles) == 0 {
		return &BatchPlan{ComputedAt: time.Now()}, nil
	}

	total := len(vehicles)
	cap := int(float64(total)*bo.maxFraction + 0.999) // round up; min 1
	if cap < 1 {
		cap = 1
	}

	// destCount tracks how many vehicles have been assigned to each destination.
	destCount := make(map[string]int)

	// Step 1: compute all plans up-front.
	type vehiclePlan struct {
		input VehicleInput
		plan  *DispositionPlan
		err   error
	}
	plans := make([]vehiclePlan, total)
	for i, v := range vehicles {
		plan, err := bo.optimizer.Optimize(OptimizeRequest{
			VehicleVIN:     v.VIN,
			Make:           v.Make,
			Model:          v.Model,
			Year:           v.Year,
			MileageKm:      v.MileageKm,
			FuelType:       v.FuelType,
			CurrentCountry: v.CurrentCountry,
			Channel:        v.Channel,
		})
		plans[i] = vehiclePlan{input: v, plan: plan, err: err}
	}

	// Sort plan indices by best unconstrained net profit (highest first) so that
	// vehicles with the most to gain get first pick of destinations.
	indices := make([]int, total)
	for i := range indices {
		indices[i] = i
	}
	sort.Slice(indices, func(a, b int) bool {
		pa, pb := plans[indices[a]].plan, plans[indices[b]].plan
		if pa == nil {
			return false
		}
		if pb == nil {
			return true
		}
		return pa.BestRoute.NetProfit > pb.BestRoute.NetProfit
	})

	// Step 2: assign routes respecting the concentration cap.
	batchPlan := &BatchPlan{
		TotalVehicles:  total,
		ByDestination:  make(map[string]int),
		ComputedAt:     time.Now(),
	}

	for _, i := range indices {
		vp := plans[i]
		if vp.err != nil || vp.plan == nil || len(vp.plan.Routes) == 0 {
			// No routes available — use a zero-profit local placeholder.
			batchPlan.Assignments = append(batchPlan.Assignments, BatchRouteAssignment{
				Vehicle: vp.input,
				AssignedRoute: DispositionRoute{
					FromCountry: vp.input.CurrentCountry,
					ToCountry:   vp.input.CurrentCountry,
					Channel:     ChannelDealerDirect,
					Explanation: "no market data available",
				},
				Rank: 0,
			})
			continue
		}

		assigned, rank, rerouted := bo.pickRoute(vp.plan.Routes, destCount, cap)
		destCount[assigned.ToCountry]++
		batchPlan.ByDestination[assigned.ToCountry]++
		if rerouted {
			batchPlan.CapConstraintApplied++
		}

		batchPlan.TotalEstimatedUplift += vp.plan.TotalUplift
		batchPlan.Assignments = append(batchPlan.Assignments, BatchRouteAssignment{
			Vehicle:       vp.input,
			AssignedRoute: assigned,
			Rank:          rank,
		})
	}

	if total > 0 {
		batchPlan.AvgUpliftPerVehicle = batchPlan.TotalEstimatedUplift / int64(total)
	}

	return batchPlan, nil
}

// pickRoute selects the best available route that does not exceed the
// destination cap. Returns the route, its 1-based rank in the sorted list,
// and whether the cap caused a fallback.
func (bo *BatchOptimizer) pickRoute(routes []DispositionRoute, destCount map[string]int, cap int) (DispositionRoute, int, bool) {
	for rank, r := range routes {
		if destCount[r.ToCountry] < cap {
			return r, rank + 1, rank > 0
		}
	}
	// All preferred destinations at capacity — use best route regardless.
	return routes[0], 1, true
}

// BatchSummary is a human-readable report for a BatchPlan.
type BatchSummary struct {
	TotalVehicles        int
	TotalUpliftEUR       float64
	AvgUpliftEUR         float64
	CapConstraintApplied int
	RouteBreakdown       []routeBreakdownRow
}

type routeBreakdownRow struct {
	Destination string
	Count       int
	PctOfFleet  float64
}

// Summarise generates a human-readable summary of a BatchPlan.
func Summarise(p *BatchPlan) BatchSummary {
	if p == nil {
		return BatchSummary{}
	}
	s := BatchSummary{
		TotalVehicles:        p.TotalVehicles,
		TotalUpliftEUR:       float64(p.TotalEstimatedUplift) / 100,
		CapConstraintApplied: p.CapConstraintApplied,
	}
	if p.TotalVehicles > 0 {
		s.AvgUpliftEUR = float64(p.AvgUpliftPerVehicle) / 100
	}
	for country, count := range p.ByDestination {
		pct := 0.0
		if p.TotalVehicles > 0 {
			pct = float64(count) / float64(p.TotalVehicles) * 100
		}
		s.RouteBreakdown = append(s.RouteBreakdown, routeBreakdownRow{
			Destination: country,
			Count:       count,
			PctOfFleet:  pct,
		})
	}
	sort.Slice(s.RouteBreakdown, func(i, j int) bool {
		return s.RouteBreakdown[i].Count > s.RouteBreakdown[j].Count
	})
	return s
}

// validateBatchRequest checks that each VehicleInput has required fields.
func validateBatchRequest(vehicles []VehicleInput) error {
	for i, v := range vehicles {
		if v.Make == "" {
			return fmt.Errorf("vehicle[%d]: make is required", i)
		}
		if v.Model == "" {
			return fmt.Errorf("vehicle[%d]: model is required", i)
		}
		if v.Year == 0 {
			return fmt.Errorf("vehicle[%d]: year is required", i)
		}
		if v.CurrentCountry == "" {
			return fmt.Errorf("vehicle[%d]: current_country is required", i)
		}
	}
	return nil
}
