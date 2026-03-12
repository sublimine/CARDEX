package taxhunter

import (
	"context"
	"errors"
	"testing"

	"github.com/cardex/forensics/pkg/ahocorasick"
	"github.com/redis/go-redis/v9"
)

type mockVatChecker struct {
	valid   bool
	name    string
	err     error
}

func (m *mockVatChecker) CheckVAT(ctx context.Context, countryCode string, vatNumber string) (bool, string, error) {
	return m.valid, m.name, m.err
}

type mockTaxCache struct {
	data map[string]string
	err  error
}

func (m *mockTaxCache) Get(ctx context.Context, vehicleULID string) (string, error) {
	if m.err != nil {
		return "", m.err
	}
	if v, ok := m.data[vehicleULID]; ok {
		return v, nil
	}
	return "", redis.Nil
}

func TestClassifier_Classify(t *testing.T) {
	scanner := ahocorasick.New()
	ctx := context.Background()

	tests := []struct {
		name        string
		vehicle     VehicleInput
		vatChecker  VatChecker
		taxCache    TaxCache
		wantStatus  string
		wantConf    float64
		wantMethod  string
		wantErr     bool
	}{
		{
			name: "entity override",
			vehicle: VehicleInput{
				VehicleULID:   "01HXYZ",
				Description:   "BMW 330i",
				SellerType:    "INDIVIDUAL",
				SellerVATID:   "",
				OriginCountry: "DE",
			},
			vatChecker: &mockVatChecker{},
			taxCache:   &mockTaxCache{},
			wantStatus: "REBU",
			wantConf:   1.00,
			wantMethod: "ENTITY_OVERRIDE",
		},
		{
			name: "aho-corasick match",
			vehicle: VehicleInput{
				VehicleULID:   "01HXYZ",
				Description:   "Vendu en marge de la TVA",
				SellerType:    "DEALER",
				SellerVATID:   "",
				OriginCountry: "FR",
			},
			vatChecker: &mockVatChecker{},
			taxCache:   &mockTaxCache{},
			wantStatus: "REBU",
			wantConf:   1.00,
			wantMethod: "AHO_CORASICK:marge",
		},
		{
			name: "L1 cache hit",
			vehicle: VehicleInput{
				VehicleULID:   "01HCACHE",
				Description:   "BMW 330i clean",
				SellerType:    "DEALER",
				SellerVATID:   "",
				OriginCountry: "DE",
			},
			vatChecker: &mockVatChecker{},
			taxCache: &mockTaxCache{
				data: map[string]string{
					"01HCACHE": `{"Status":"DEDUCTIBLE","Confidence":0.99,"Method":"L3_CACHE"}`,
				},
			},
			wantStatus: "DEDUCTIBLE",
			wantConf:   0.99,
			wantMethod: "L3_CACHE",
		},
		{
			name: "VIES valid",
			vehicle: VehicleInput{
				VehicleULID:   "01HVIES",
				Description:   "BMW 330i",
				SellerType:    "DEALER",
				SellerVATID:   "DE123456789",
				OriginCountry: "DE",
			},
			vatChecker: &mockVatChecker{valid: true, name: "BMW AG"},
			taxCache:   &mockTaxCache{},
			wantStatus: "DEDUCTIBLE",
			wantConf:   0.98,
			wantMethod: "VIES",
		},
		{
			name: "VIES invalid",
			vehicle: VehicleInput{
				VehicleULID:   "01HINVALID",
				Description:   "BMW 330i",
				SellerType:    "DEALER",
				SellerVATID:   "DE999999999",
				OriginCountry: "DE",
			},
			vatChecker: &mockVatChecker{valid: false},
			taxCache:   &mockTaxCache{},
			wantStatus: "REBU",
			wantConf:   0.95,
			wantMethod: "VIES_INVALID",
		},
		{
			name: "VIES timeout",
			vehicle: VehicleInput{
				VehicleULID:   "01HTIMEOUT",
				Description:   "BMW 330i",
				SellerType:    "DEALER",
				SellerVATID:   "DE123456789",
				OriginCountry: "DE",
			},
			vatChecker: &mockVatChecker{err: errors.New("vies: timeout after 200ms for DE123456789")},
			taxCache:   &mockTaxCache{},
			wantStatus: "PENDING_VIES_OPTIMISTIC",
			wantConf:   0.70,
			wantMethod: "VIES_TIMEOUT",
		},
		{
			name: "no-signal fallback",
			vehicle: VehicleInput{
				VehicleULID:   "01HNOSIG",
				Description:   "BMW 330i clean listing",
				SellerType:    "DEALER",
				SellerVATID:   "",
				OriginCountry: "DE",
			},
			vatChecker: &mockVatChecker{},
			taxCache:   &mockTaxCache{},
			wantStatus: "REQUIRES_HUMAN_AUDIT",
			wantConf:   0.00,
			wantMethod: "NO_SIGNAL",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c := NewWithCache(scanner, tt.vatChecker, tt.taxCache)
			got, err := c.Classify(ctx, tt.vehicle)
			if tt.wantErr {
				if err == nil {
					t.Errorf("Classify() expected error, got nil")
				}
				return
			}
			if err != nil {
				t.Errorf("Classify() unexpected error: %v", err)
				return
			}
			if got.Status != tt.wantStatus {
				t.Errorf("Classify() Status = %q, want %q", got.Status, tt.wantStatus)
			}
			if got.Confidence != tt.wantConf {
				t.Errorf("Classify() Confidence = %v, want %v", got.Confidence, tt.wantConf)
			}
			if got.Method != tt.wantMethod {
				t.Errorf("Classify() Method = %q, want %q", got.Method, tt.wantMethod)
			}
		})
	}
}
