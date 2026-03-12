package tax

import (
	"math"
	"testing"
)

func TestNetherlandsCalculator_RestBPM(t *testing.T) {
	calc := &NetherlandsCalculator{}
	epsilon := 0.0001

	tests := []struct {
		name       string
		co2GKM     int
		ageMonths  int
		want       float64
	}{
		{
			name:      "new vehicle",
			co2GKM:    150,
			ageMonths: 0,
			want:      19500,
		},
		{
			name:      "aged vehicle",
			co2GKM:    150,
			ageMonths: 50,
			want:      9750,
		},
		{
			name:      "max discount 90%",
			co2GKM:    150,
			ageMonths: 120,
			want:      1950,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := calc.RestBPM(tt.co2GKM, tt.ageMonths)
			if math.Abs(got-tt.want) > epsilon {
				t.Errorf("RestBPM(%d, %d) = %v, want %v", tt.co2GKM, tt.ageMonths, got, tt.want)
			}
		})
	}
}
