package pulse

import "math"

// Score computes the 0-100 health score from raw signals and weights, then
// populates s.HealthScore, s.HealthTier, s.RiskSignals, and s.TrendDirection.
// history must be ordered oldest-first; pass nil when unavailable.
func Score(s *DealerHealthScore, w WeightConfig, history []HistoryPoint) {
	stress := weightedStress(s, w)
	s.HealthScore = math.Max(0, math.Min(100, 100*(1-stress)))
	s.HealthTier = TierFromScore(s.HealthScore)
	s.RiskSignals = CollectRiskSignals(s)
	s.TrendDirection = DetectTrend(history, s.HealthScore)
}

func weightedStress(s *DealerHealthScore, w WeightConfig) float64 {
	return w.Liquidation*liquidationStress(s.LiquidationRatio) +
		w.PriceTrend*priceTrendStress(s.PriceTrend) +
		w.Volume*volumeStress(s.VolumeZScore) +
		w.TimeOnMarket*tomStress(s.TimeOnMarketDelta) +
		w.CompositeDelta*compositeDeltaStress(s.CompositeScoreDelta) +
		w.BrandHHI*hhiStress(s.BrandHHI) +
		w.PriceVsMarket*priceVsMarketStress(s.PriceVsMarket)
}

func clamp01(v float64) float64 {
	if v < 0 {
		return 0
	}
	if v > 1 {
		return 1
	}
	return v
}

// liquidationStress: >1.5 = full stress, 1.0 = zero stress.
func liquidationStress(ratio float64) float64 { return clamp01((ratio - 1.0) / 0.5) }

// priceTrendStress: < -5%/week = stress; < -10%/week = full stress.
func priceTrendStress(pct float64) float64 { return clamp01(-pct / 10.0) }

// volumeStress: |z| >= 2 = full stress.
func volumeStress(z float64) float64 { return clamp01(math.Abs(z) / 2.0) }

// tomStress: ToM delta > 20% = stress; > 40% = full stress.
func tomStress(deltaPct float64) float64 { return clamp01(deltaPct / 40.0) }

// compositeDeltaStress: < -10 pts = stress; < -20 pts = full stress.
func compositeDeltaStress(delta float64) float64 { return clamp01(-delta / 20.0) }

// hhiStress: HHI > 0.5 = stress; 1.0 = full stress.
func hhiStress(hhi float64) float64 { return clamp01((hhi - 0.25) / 0.75) }

// priceVsMarketStress: ratio < 0.85 = stress; < 0.65 = full stress.
func priceVsMarketStress(ratio float64) float64 { return clamp01((0.85 - ratio) / 0.20) }

// CollectRiskSignals returns active stress signal labels for the given score.
func CollectRiskSignals(s *DealerHealthScore) []string {
	var signals []string
	if s.LiquidationRatio > 1.5 {
		signals = append(signals, "liquidation_pressure")
	}
	if s.PriceTrend < -5 {
		signals = append(signals, "price_erosion")
	}
	if math.Abs(s.VolumeZScore) > 1.5 {
		signals = append(signals, "volume_anomaly")
	}
	if s.TimeOnMarketDelta > 20 {
		signals = append(signals, "inventory_stagnation")
	}
	if s.CompositeScoreDelta < -10 {
		signals = append(signals, "quality_deterioration")
	}
	if s.BrandHHI > 0.5 {
		signals = append(signals, "brand_concentration")
	}
	if s.PriceVsMarket > 0 && s.PriceVsMarket < 0.85 {
		signals = append(signals, "deep_discount")
	}
	return signals
}

// DetectTrend compares currentScore against the trailing average of history
// (up to 3 most recent points) and returns "improving", "deteriorating", or "stable".
func DetectTrend(history []HistoryPoint, currentScore float64) string {
	if len(history) < 2 {
		return "stable"
	}
	tail := history
	if len(tail) > 3 {
		tail = tail[len(tail)-3:]
	}
	var sum float64
	for _, h := range tail {
		sum += h.HealthScore
	}
	avg := sum / float64(len(tail))
	delta := currentScore - avg
	switch {
	case delta > 5:
		return "improving"
	case delta < -5:
		return "deteriorating"
	default:
		return "stable"
	}
}
