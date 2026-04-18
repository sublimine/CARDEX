package pulse

import (
	"encoding/json"
	"fmt"
	"os"
)

// WeightConfig holds the fractional weights for each of the seven health signals.
// All weights must sum to 1.0. Load from a JSON file via LoadWeights; fall back
// to DefaultWeights() when no override file is present.
type WeightConfig struct {
	Liquidation    float64 `json:"liquidation"`
	PriceTrend     float64 `json:"price_trend"`
	Volume         float64 `json:"volume"`
	TimeOnMarket   float64 `json:"time_on_market"`
	CompositeDelta float64 `json:"composite_delta"`
	BrandHHI       float64 `json:"brand_hhi"`
	PriceVsMarket  float64 `json:"price_vs_market"`
}

// DefaultWeights returns the baseline signal weights as specified in Sprint 35.
// Liquidation 20% | Price trend 15% | Volume 15% | ToM 15% |
// Composite delta 10% | Brand HHI 10% | Price vs market 15%
func DefaultWeights() WeightConfig {
	return WeightConfig{
		Liquidation:    0.20,
		PriceTrend:     0.15,
		Volume:         0.15,
		TimeOnMarket:   0.15,
		CompositeDelta: 0.10,
		BrandHHI:       0.10,
		PriceVsMarket:  0.15,
	}
}

// LoadWeights reads a JSON weight-override file from path.
// Returns DefaultWeights() when the file does not exist.
func LoadWeights(path string) (WeightConfig, error) {
	if path == "" {
		return DefaultWeights(), nil
	}
	f, err := os.Open(path)
	if os.IsNotExist(err) {
		return DefaultWeights(), nil
	}
	if err != nil {
		return WeightConfig{}, fmt.Errorf("pulse: open weights file: %w", err)
	}
	defer f.Close()

	var w WeightConfig
	if err := json.NewDecoder(f).Decode(&w); err != nil {
		return WeightConfig{}, fmt.Errorf("pulse: decode weights: %w", err)
	}
	return w, nil
}
