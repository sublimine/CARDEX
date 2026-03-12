// Package tax implements sovereign tax formulas for NLC computation (Phase 6).
package tax

// SpainCalculator computes Spanish IEDMT (Impuesto sobre Matriculación) registration tax.
// CO₂-based registration tax applied to net_landed_cost_eur (pre-tax).
type SpainCalculator struct{}

// IEDMT returns the Spanish registration tax amount in EUR.
// CO₂ > 200 g/km → 14.75%, CO₂ > 160 g/km → 9.75%, CO₂ > 120 g/km → 4.75%, CO₂ ≤ 120 g/km → 0%.
func (c *SpainCalculator) IEDMT(co2GKM int, netPrice float64) float64 {
	var rate float64
	switch {
	case co2GKM > 200:
		rate = 0.1475
	case co2GKM > 160:
		rate = 0.0975
	case co2GKM > 120:
		rate = 0.0475
	default:
		rate = 0
	}
	return netPrice * rate
}
