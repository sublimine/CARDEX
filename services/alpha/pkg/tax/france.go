// Package tax implements sovereign tax formulas for NLC computation (Phase 6).
package tax

// FranceCalculator computes French Malus Écologique registration tax.
// Flat EUR amount added to NLC based on CO₂ and vehicle age.
type FranceCalculator struct{}

// Malus returns the French Malus Écologique tax amount in EUR.
// Formula: min((CO₂ - 117)² × 10, 60000) × (1 - ageYears × 0.10).
// Returns 0 if CO₂ ≤ 117 or if age discount makes result negative.
func (c *FranceCalculator) Malus(co2GKM int, ageYears int) float64 {
	if co2GKM <= 117 {
		return 0
	}
	base := float64((co2GKM-117)*(co2GKM-117)) * 10
	if base > 60000 {
		base = 60000
	}
	ageFactor := 1 - float64(ageYears)*0.10
	if ageFactor <= 0 {
		return 0
	}
	result := base * ageFactor
	if result < 0 {
		return 0
	}
	return result
}
