// Package pulse computes real-time dealer health scores from vehicle inventory
// signals. It serves as a leading indicator 6–18 months ahead of traditional
// bank floorplan-lending risk assessments (which rely on 12–18-month-lagged
// financials).
//
// Seven inventory-derived signals are combined into a weighted health score:
//
//  1. Liquidation ratio  — accelerated sell-off vs new stock intake
//  2. Price trend        — week-over-week price direction
//  3. Volume z-score     — abnormal listing volume vs 90-day baseline
//  4. Time on market     — stagnant inventory = weak demand
//  5. Composite delta    — quality-score deterioration
//  6. Brand HHI          — supply-chain concentration risk
//  7. Price vs market    — deep discount = cash urgency
package pulse

import "time"

// DealerHealthScore is the full output of a single scoring run for one dealer.
type DealerHealthScore struct {
	DealerID    string `json:"dealer_id"`
	DealerName  string `json:"dealer_name"`
	Country     string `json:"country"`
	ActiveCount int    `json:"active_listings"`

	// Raw signals
	LiquidationRatio    float64 `json:"liquidation_ratio"`       // removed/new in 14d; >1.5 = stress
	PriceTrend          float64 `json:"price_trend_pct_week"`    // %/week; <-5 = stress
	VolumeZScore        float64 `json:"volume_z_score"`          // weekly vol vs 90d baseline
	AvgTimeOnMarket     float64 `json:"avg_time_on_market_days"` // days; rising = weak demand
	TimeOnMarketDelta   float64 `json:"time_on_market_delta_pct"` // % vs prior 30d; >20 = stress
	CompositeScoreDelta float64 `json:"composite_score_delta"`   // pts vs prior 14d; <-10 = stress
	BrandHHI            float64 `json:"brand_hhi"`               // 0-1; >0.5 = concentration risk
	PriceVsMarket       float64 `json:"price_vs_market_ratio"`   // dealer avg / market avg; <0.85 = stress

	// Derived
	HealthScore    float64   `json:"health_score"`    // 0-100 (100 = fully healthy)
	HealthTier     string    `json:"health_tier"`     // "healthy"|"watch"|"stress"|"critical"
	RiskSignals    []string  `json:"risk_signals"`    // active stress signal labels
	TrendDirection string    `json:"trend_direction"` // "improving"|"stable"|"deteriorating"
	ComputedAt     time.Time `json:"computed_at"`
}

// HealthTier labels.
const (
	TierHealthy  = "healthy"  // score >= 70
	TierWatch    = "watch"    // score >= 50
	TierStress   = "stress"   // score >= 30
	TierCritical = "critical" // score < 30
)

// TierFromScore maps a numeric score to a human-readable tier.
func TierFromScore(score float64) string {
	switch {
	case score >= 70:
		return TierHealthy
	case score >= 50:
		return TierWatch
	case score >= 30:
		return TierStress
	default:
		return TierCritical
	}
}

// HistoryPoint is a single time-series snapshot stored in dealer_health_history.
type HistoryPoint struct {
	DealerID    string    `json:"dealer_id"`
	HealthScore float64   `json:"health_score"`
	HealthTier  string    `json:"health_tier"`
	SignalsJSON string    `json:"signals_json"`
	ComputedAt  time.Time `json:"computed_at"`
}
