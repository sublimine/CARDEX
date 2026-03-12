//go:build integration

package nlc

import (
	"context"
	"math"
	"strings"
	"testing"
	"time"

	"github.com/cardex/alpha/pkg/tax"
	"github.com/redis/go-redis/v9"
)

func newTestCalculator(t *testing.T) *Calculator {
	t.Helper()
	rdb := redis.NewClient(&redis.Options{
		Addr: "localhost:6379",
	})
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := rdb.Ping(ctx).Err(); err != nil {
		t.Skipf("Redis not available at localhost:6379: %v", err)
	}
	return New(rdb, &tax.SpainCalculator{}, &tax.FranceCalculator{}, &tax.NetherlandsCalculator{})
}

func TestCalculator_Compute(t *testing.T) {
	calc := newTestCalculator(t)
	ctx := context.Background()
	epsilon := 0.0001

	tests := []struct {
		name            string
		input           NLCInput
		wantNLC         float64
		wantLogistics   float64
		wantTax         float64
		wantErr         bool
		errSubstr       string
	}{
		{
			name: "Spain target",
			input: NLCInput{
				GrossPhysicalCostEUR: 20000,
				OriginCountry:        "DE",
				TargetCountry:        "ES",
				CO2GKM:               180,
				VehicleAgeYears:      2,
				VehicleAgeMonths:     24,
			},
			wantLogistics: 800,
			wantTax:       20800 * 0.0975,
			wantNLC:       20000 + 800 + (20800 * 0.0975),
			wantErr:       false,
		},
		{
			name: "France target",
			input: NLCInput{
				GrossPhysicalCostEUR: 20000,
				OriginCountry:        "DE",
				TargetCountry:        "FR",
				CO2GKM:               150,
				VehicleAgeYears:      1,
				VehicleAgeMonths:     12,
			},
			wantLogistics: 800,
			wantTax:       float64((150-117)*(150-117)*10) * 0.9,
			wantNLC:       20000 + 800 + float64((150-117)*(150-117)*10)*0.9,
			wantErr:       false,
		},
		{
			name: "unknown origin fails",
			input: NLCInput{
				GrossPhysicalCostEUR: 20000,
				OriginCountry:        "XX",
				TargetCountry:        "ES",
				CO2GKM:               180,
			},
			wantErr:   true,
			errSubstr: "unknown origin",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := calc.Compute(ctx, tt.input)
			if tt.wantErr {
				if err == nil {
					t.Errorf("Compute() expected error, got nil")
					return
				}
				if tt.errSubstr != "" && !strings.Contains(err.Error(), tt.errSubstr) {
					t.Errorf("Compute() error = %v, want substring %q", err, tt.errSubstr)
				}
				return
			}
			if err != nil {
				t.Errorf("Compute() unexpected error: %v", err)
				return
			}
			if math.Abs(got.NetLandedCostEUR-tt.wantNLC) > epsilon {
				t.Errorf("Compute() NetLandedCostEUR = %v, want %v", got.NetLandedCostEUR, tt.wantNLC)
			}
			if math.Abs(got.LogisticsCostEUR-tt.wantLogistics) > epsilon {
				t.Errorf("Compute() LogisticsCostEUR = %v, want %v", got.LogisticsCostEUR, tt.wantLogistics)
			}
			if math.Abs(got.TaxAmountEUR-tt.wantTax) > epsilon {
				t.Errorf("Compute() TaxAmountEUR = %v, want %v", got.TaxAmountEUR, tt.wantTax)
			}
		})
	}
}
