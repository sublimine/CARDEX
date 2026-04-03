// Package sdi implements the Seller Desperation Index detector for Phase 6.
// Flags vehicles in floorplan curtailment cliff zones.
package sdi

const (
	zone60D = "FLOORPLAN_60D_CLIFF"
	zone90D = "FLOORPLAN_90D_CLIFF"
)

// Detector flags vehicles in curtailment cliff zones.
type Detector struct{}

// Check returns whether daysOnMarket falls in a cliff zone.
// Zone 1: 58-65 days (floorplan 60-day cliff).
// Zone 2: 88-95 days (floorplan 90-day cliff).
func (d *Detector) Check(daysOnMarket int) (alert bool, zone string) {
	if daysOnMarket >= 58 && daysOnMarket <= 65 {
		return true, zone60D
	}
	if daysOnMarket >= 88 && daysOnMarket <= 95 {
		return true, zone90D
	}
	return false, ""
}
