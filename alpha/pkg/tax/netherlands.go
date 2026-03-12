// Package tax implements sovereign tax formulas for NLC computation (Phase 6).
package tax

// NetherlandsCalculator computes Dutch Rest-BPM registration tax.
// Flat EUR amount added to NLC based on CO₂ and vehicle age.
type NetherlandsCalculator struct{}

// RestBPM returns the Dutch Rest-BPM tax amount in EUR.
// Formula: CO₂ × 130 × (1 - min(ageMonths × 0.01, 0.90)).
func (c *NetherlandsCalculator) RestBPM(co2GKM int, ageMonths int) float64 {
	discount := float64(ageMonths) * 0.01
	if discount > 0.90 {
		discount = 0.90
	}
	factor := 1 - discount
	return float64(co2GKM) * 130 * factor
}
