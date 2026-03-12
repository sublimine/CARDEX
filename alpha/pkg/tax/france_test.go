package tax

import (
	"math"
	"testing"
)

func TestFranceCalculator_Malus(t *testing.T) {
	calc := &FranceCalculator{}
	epsilon := 0.0001

	tests := []struct {
		name     string
		co2GKM   int
		ageYears int
		want     float64
	}{
		{
			name:     "high CO2",
			co2GKM:   200,
			ageYears: 0,
			want:     60000,
		},
		{
			name:     "moderate CO2",
			co2GKM:   150,
			ageYears: 2,
			want:     8712,
		},
		{
			name:     "below threshold",
			co2GKM:   110,
			ageYears: 0,
			want:     0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := calc.Malus(tt.co2GKM, tt.ageYears)
			if math.Abs(got-tt.want) > epsilon {
				t.Errorf("Malus(%d, %d) = %v, want %v", tt.co2GKM, tt.ageYears, got, tt.want)
			}
		})
	}
}
