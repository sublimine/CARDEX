package tax

import (
	"math"
	"testing"
)

func TestSpainCalculator_IEDMT(t *testing.T) {
	calc := &SpainCalculator{}
	epsilon := 0.0001

	tests := []struct {
		name     string
		co2GKM   int
		netPrice float64
		want     float64
	}{
		{
			name:     "high CO2 over 200",
			co2GKM:   210,
			netPrice: 25000,
			want:     3687.50,
		},
		{
			name:     "mid CO2 161-200",
			co2GKM:   180,
			netPrice: 25000,
			want:     2437.50,
		},
		{
			name:     "low CO2 121-160",
			co2GKM:   140,
			netPrice: 25000,
			want:     1187.50,
		},
		{
			name:     "zero CO2 under 120",
			co2GKM:   100,
			netPrice: 25000,
			want:     0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := calc.IEDMT(tt.co2GKM, tt.netPrice)
			if math.Abs(got-tt.want) > epsilon {
				t.Errorf("IEDMT(%d, %v) = %v, want %v", tt.co2GKM, tt.netPrice, got, tt.want)
			}
		})
	}
}
