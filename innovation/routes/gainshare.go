package routes

import "fmt"

// CalculateGainShare computes the CARDEX performance-based fee for documented
// vehicle price uplift.
//
// The gain-share model:
//   - Baseline: what the vehicle would have sold for locally without CARDEX routing.
//   - Uplift:   actual sale price − local baseline. Zero or negative uplift = no fee.
//   - Fee:      uplift × feeRate (e.g. 0.15 for 15%, 0.20 for 20%).
//   - Net:      uplift − fee (client's share of the gain).
//
// Typical feeRate range: 0.15 – 0.20 (15% – 20%).
func CalculateGainShare(actualSalePrice, localBaseline int64, feeRate float64) (GainShare, error) {
	if feeRate < 0 || feeRate > 1 {
		return GainShare{}, fmt.Errorf("feeRate must be in [0,1], got %.4f", feeRate)
	}
	uplift := actualSalePrice - localBaseline
	if uplift < 0 {
		uplift = 0 // no fee on a loss
	}
	fee := int64(float64(uplift) * feeRate)
	return GainShare{
		ActualSalePrice: actualSalePrice,
		LocalBaseline:   localBaseline,
		Uplift:          uplift,
		FeeRate:         feeRate,
		Fee:             fee,
		NetToClient:     uplift - fee,
	}, nil
}
