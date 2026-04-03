// Package nlc implements Net Landed Cost computation for Phase 6.
package nlc

import (
	"context"
	"fmt"
	"strconv"

	"github.com/cardex/alpha/pkg/tax"
	"github.com/redis/go-redis/v9"
)

const logisticsKey = "logistics:worst_case"

// NLCInput holds vehicle data for NLC computation.
type NLCInput struct {
	GrossPhysicalCostEUR float64
	OriginCountry        string
	TargetCountry        string
	CO2GKM               int
	VehicleAgeYears      int
	VehicleAgeMonths     int
}

// NLCResult holds the computed NLC components.
type NLCResult struct {
	NetLandedCostEUR   float64
	LogisticsCostEUR   float64
	TaxAmountEUR       float64
}

// Calculator computes Net Landed Cost.
type Calculator struct {
	rdb         *redis.Client
	spain       *tax.SpainCalculator
	france      *tax.FranceCalculator
	netherlands *tax.NetherlandsCalculator
}

// New creates a Calculator with the given dependencies.
func New(rdb *redis.Client, spain *tax.SpainCalculator, france *tax.FranceCalculator, netherlands *tax.NetherlandsCalculator) *Calculator {
	return &Calculator{
		rdb:         rdb,
		spain:       spain,
		france:      france,
		netherlands: netherlands,
	}
}

// Compute calculates NLC = GrossPhysicalCost + Logistics + Tax.
// Returns error if origin country not in logistics:worst_case.
func (c *Calculator) Compute(ctx context.Context, vehicle NLCInput) (NLCResult, error) {
	logisticsStr, err := c.rdb.HGet(ctx, logisticsKey, vehicle.OriginCountry).Result()
	if err == redis.Nil {
		return NLCResult{}, fmt.Errorf("nlc: unknown origin country %s", vehicle.OriginCountry)
	}
	if err != nil {
		return NLCResult{}, fmt.Errorf("nlc: logistics lookup: %w", err)
	}

	logistics, err := strconv.ParseFloat(logisticsStr, 64)
	if err != nil {
		return NLCResult{}, fmt.Errorf("nlc: invalid logistics value for %s: %w", vehicle.OriginCountry, err)
	}

	if vehicle.GrossPhysicalCostEUR < 0 || logistics < 0 {
		return NLCResult{}, fmt.Errorf("nlc: gross physical cost and logistics must be non-negative")
	}

	var taxAmount float64
	switch vehicle.TargetCountry {
	case "ES":
		preTax := vehicle.GrossPhysicalCostEUR + logistics
		taxAmount = c.spain.IEDMT(vehicle.CO2GKM, preTax)
	case "FR":
		taxAmount = c.france.Malus(vehicle.CO2GKM, vehicle.VehicleAgeYears)
	case "NL":
		taxAmount = c.netherlands.RestBPM(vehicle.CO2GKM, vehicle.VehicleAgeMonths)
	default:
		taxAmount = 0
	}

	if taxAmount < 0 {
		return NLCResult{}, fmt.Errorf("nlc: tax amount must be non-negative")
	}

	nlc := vehicle.GrossPhysicalCostEUR + logistics + taxAmount
	return NLCResult{
		NetLandedCostEUR: nlc,
		LogisticsCostEUR: logistics,
		TaxAmountEUR:     taxAmount,
	}, nil
}
