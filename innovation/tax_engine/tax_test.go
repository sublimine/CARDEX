package tax_test

import (
	"testing"

	tax "cardex.eu/tax"
)

// ── 1. All 30 directional pairs ──────────────────────────────────────────────

func TestAllThirtyPairs(t *testing.T) {
	t.Parallel()

	type pairCase struct {
		from, to    string
		wantRegimes []tax.VATRegime
		optimalIdx  int
	}

	euPairs := []struct{ from, to string }{
		{"DE", "FR"}, {"DE", "ES"}, {"DE", "BE"}, {"DE", "NL"},
		{"FR", "DE"}, {"FR", "ES"}, {"FR", "BE"}, {"FR", "NL"},
		{"ES", "DE"}, {"ES", "FR"}, {"ES", "BE"}, {"ES", "NL"},
		{"BE", "DE"}, {"BE", "FR"}, {"BE", "ES"}, {"BE", "NL"},
		{"NL", "DE"}, {"NL", "FR"}, {"NL", "ES"}, {"NL", "BE"},
	}

	chToEU := []string{"DE", "FR", "ES", "BE", "NL"}
	euToCH := []string{"DE", "FR", "ES", "BE", "NL"}

	validVIES := map[string]bool{"SELLER": true, "BUYER": true}

	// EU→EU with valid VIES: both IC and MS present; IC is optimal
	for _, p := range euPairs {
		from, to := p.from, p.to
		t.Run(from+"→"+to+"_validVIES", func(t *testing.T) {
			t.Parallel()
			req := tax.CalculationRequest{
				FromCountry:       from,
				ToCountry:         to,
				VehiclePriceCents: 2_000_000,
				MarginCents:       300_000,
				SellerVATID:       "SELLER",
				BuyerVATID:        "BUYER",
			}
			resp := tax.Calculate(req, validVIES)

			if len(resp.Routes) != 2 {
				t.Fatalf("want 2 routes, got %d", len(resp.Routes))
			}
			if resp.Routes[0].Route.Regime != tax.RegimeIntraCommunity {
				t.Errorf("routes[0] regime = %s, want INTRA_COMMUNITY", resp.Routes[0].Route.Regime)
			}
			if resp.Routes[1].Route.Regime != tax.RegimeMarginScheme {
				t.Errorf("routes[1] regime = %s, want MARGIN_SCHEME", resp.Routes[1].Route.Regime)
			}
			if !resp.Routes[0].IsOptimal {
				t.Error("routes[0].IsOptimal should be true")
			}
			if resp.Routes[1].IsOptimal {
				t.Error("routes[1].IsOptimal should be false")
			}
			if resp.OptimalRoute == nil {
				t.Fatal("OptimalRoute is nil")
			}
			if resp.OptimalRoute.Route.Regime != tax.RegimeIntraCommunity {
				t.Errorf("OptimalRoute regime = %s, want INTRA_COMMUNITY", resp.OptimalRoute.Route.Regime)
			}
			if resp.Routes[0].Explanation == "" {
				t.Error("IC explanation should not be empty")
			}
			if resp.Routes[0].Route.LegalBasis == "" {
				t.Error("IC LegalBasis should not be empty")
			}
		})
	}

	// EU→EU no VIES: only MS
	t.Run("DE→FR_noVIES", func(t *testing.T) {
		t.Parallel()
		req := tax.CalculationRequest{
			FromCountry:       "DE",
			ToCountry:         "FR",
			VehiclePriceCents: 2_000_000,
			MarginCents:       300_000,
		}
		resp := tax.Calculate(req, map[string]bool{})
		if len(resp.Routes) != 1 {
			t.Fatalf("want 1 route (no VIES), got %d", len(resp.Routes))
		}
		if resp.Routes[0].Route.Regime != tax.RegimeMarginScheme {
			t.Errorf("want MARGIN_SCHEME, got %s", resp.Routes[0].Route.Regime)
		}
	})

	// CH→EU
	for _, to := range chToEU {
		to := to
		t.Run("CH→"+to, func(t *testing.T) {
			t.Parallel()
			req := tax.CalculationRequest{
				FromCountry:       "CH",
				ToCountry:         to,
				VehiclePriceCents: 2_000_000,
			}
			resp := tax.Calculate(req, map[string]bool{})
			if len(resp.Routes) != 1 {
				t.Fatalf("CH→%s: want 1 route, got %d", to, len(resp.Routes))
			}
			if resp.Routes[0].Route.Regime != tax.RegimeExportImport {
				t.Errorf("CH→%s: want EXPORT_IMPORT, got %s", to, resp.Routes[0].Route.Regime)
			}
			if resp.Routes[0].Route.VATRate != tax.NationalVATRates[to] {
				t.Errorf("CH→%s: VATRate = %.3f, want %.3f", to, resp.Routes[0].Route.VATRate, tax.NationalVATRates[to])
			}
		})
	}

	// EU→CH
	for _, from := range euToCH {
		from := from
		t.Run(from+"→CH", func(t *testing.T) {
			t.Parallel()
			req := tax.CalculationRequest{
				FromCountry:       from,
				ToCountry:         "CH",
				VehiclePriceCents: 2_000_000,
			}
			resp := tax.Calculate(req, map[string]bool{})
			if len(resp.Routes) != 1 {
				t.Fatalf("%s→CH: want 1 route, got %d", from, len(resp.Routes))
			}
			if resp.Routes[0].Route.Regime != tax.RegimeExportImport {
				t.Errorf("%s→CH: want EXPORT_IMPORT, got %s", from, resp.Routes[0].Route.Regime)
			}
			if resp.Routes[0].Route.VATRate != 0.081 {
				t.Errorf("%s→CH: CH MWST rate = %.3f, want 0.081", from, resp.Routes[0].Route.VATRate)
			}
		})
	}
}

// ── 2. MarginScheme vs IntraCommunity amounts ─────────────────────────────────

func TestMarginSchemeVsIntraCommunity(t *testing.T) {
	t.Parallel()

	req := tax.CalculationRequest{
		FromCountry:       "DE",
		ToCountry:         "FR",
		VehiclePriceCents: 1_500_000, // €15 000
		MarginCents:       200_000,   // €2 000
		SellerVATID:       "DE111",
		BuyerVATID:        "FR222",
	}
	vies := map[string]bool{"DE111": true, "FR222": true}
	resp := tax.Calculate(req, vies)

	if len(resp.Routes) != 2 {
		t.Fatalf("want 2 routes, got %d", len(resp.Routes))
	}

	ic := resp.Routes[0]
	ms := resp.Routes[1]

	if ic.Route.Regime != tax.RegimeIntraCommunity {
		t.Fatalf("routes[0] = %s, want INTRA_COMMUNITY", ic.Route.Regime)
	}
	if ms.Route.Regime != tax.RegimeMarginScheme {
		t.Fatalf("routes[1] = %s, want MARGIN_SCHEME", ms.Route.Regime)
	}

	// IntraCommunity: VATAmount=0, TotalCost=price
	if ic.VATAmount != 0 {
		t.Errorf("IntraCommunity VATAmount = %d, want 0", ic.VATAmount)
	}
	if ic.TotalCost != req.VehiclePriceCents {
		t.Errorf("IntraCommunity TotalCost = %d, want %d", ic.TotalCost, req.VehiclePriceCents)
	}

	// MarginScheme: embedded VAT on margin at DE rate 19%
	// VATAmount = 200000 × 0.19/1.19 ≈ 31932 cents
	var marginF float64 = 200_000
	expectedVAT := int64(marginF * 0.19 / 1.19)
	if ms.VATAmount != expectedVAT {
		t.Errorf("MarginScheme VATAmount = %d, want %d", ms.VATAmount, expectedVAT)
	}

	// NetSaving of IntraCommunity = VATAmount of MarginScheme
	if ic.NetSaving != ms.VATAmount {
		t.Errorf("NetSaving = %d, want %d (MarginScheme VATAmount)", ic.NetSaving, ms.VATAmount)
	}

	// MarginScheme NetSaving = 0 (it's the worst route)
	if ms.NetSaving != 0 {
		t.Errorf("MarginScheme NetSaving = %d, want 0", ms.NetSaving)
	}
}

// ── 3. VIES invalid → margin scheme only ──────────────────────────────────────

func TestVIESInvalidFallback(t *testing.T) {
	t.Parallel()
	req := tax.CalculationRequest{
		FromCountry:       "ES",
		ToCountry:         "DE",
		VehiclePriceCents: 1_500_000,
		MarginCents:       200_000,
		SellerVATID:       "ESX",
		BuyerVATID:        "DEY",
	}
	// Both IDs present in status but false → no IC
	vies := map[string]bool{"ESX": false, "DEY": false}
	resp := tax.Calculate(req, vies)

	if len(resp.Routes) != 1 {
		t.Fatalf("want 1 route, got %d", len(resp.Routes))
	}
	if resp.Routes[0].Route.Regime != tax.RegimeMarginScheme {
		t.Errorf("want MARGIN_SCHEME, got %s", resp.Routes[0].Route.Regime)
	}
}

// ── 4. Missing VAT IDs → margin scheme only ───────────────────────────────────

func TestMissingVATIDs(t *testing.T) {
	t.Parallel()
	req := tax.CalculationRequest{
		FromCountry:       "FR",
		ToCountry:         "BE",
		VehiclePriceCents: 800_000,
	}
	resp := tax.Calculate(req, map[string]bool{})
	if len(resp.Routes) != 1 || resp.Routes[0].Route.Regime != tax.RegimeMarginScheme {
		t.Errorf("want MARGIN_SCHEME only, got %d routes", len(resp.Routes))
	}
}

// ── 5. New vehicle — by age ───────────────────────────────────────────────────

func TestNewVehicleByAge(t *testing.T) {
	t.Parallel()
	req := tax.CalculationRequest{
		FromCountry:       "DE",
		ToCountry:         "FR",
		VehiclePriceCents: 3_000_000,
		VehicleAgeMonths:  4, // ≤ 6 → new
		SellerVATID:       "DE1",
		BuyerVATID:        "FR2",
	}
	vies := map[string]bool{"DE1": true, "FR2": true}
	resp := tax.Calculate(req, vies)

	if !resp.IsNewVehicle {
		t.Error("IsNewVehicle should be true for age=4 months")
	}
	if len(resp.Routes) != 1 {
		t.Fatalf("want 1 route for new vehicle, got %d", len(resp.Routes))
	}
	if resp.Routes[0].Route.Regime != tax.RegimeIntraCommunity {
		t.Errorf("want INTRA_COMMUNITY at dest rate, got %s", resp.Routes[0].Route.Regime)
	}
	if resp.Routes[0].Route.VATRate != tax.NationalVATRates["FR"] {
		t.Errorf("VATRate = %.3f, want FR rate %.3f", resp.Routes[0].Route.VATRate, tax.NationalVATRates["FR"])
	}
	// New vehicle IC: taxed at destination rate, TotalCost > price
	if resp.Routes[0].TotalCost <= req.VehiclePriceCents {
		t.Errorf("TotalCost = %d should be > price %d for new vehicle", resp.Routes[0].TotalCost, req.VehiclePriceCents)
	}
}

// ── 6. New vehicle — by km ────────────────────────────────────────────────────

func TestNewVehicleByKM(t *testing.T) {
	t.Parallel()
	req := tax.CalculationRequest{
		FromCountry:       "ES",
		ToCountry:         "NL",
		VehiclePriceCents: 2_500_000,
		VehicleKM:         3_000, // ≤ 6000 → new
	}
	resp := tax.Calculate(req, map[string]bool{})
	if !resp.IsNewVehicle {
		t.Error("IsNewVehicle should be true for km=3000")
	}
	if len(resp.Routes) != 1 {
		t.Fatalf("want 1 route (new vehicle), got %d", len(resp.Routes))
	}
	if resp.Routes[0].Route.Regime != tax.RegimeIntraCommunity {
		t.Errorf("want INTRA_COMMUNITY for new vehicle, got %s", resp.Routes[0].Route.Regime)
	}
}

// ── 7. Used vehicle — above thresholds ───────────────────────────────────────

func TestUsedVehicleAboveThresholds(t *testing.T) {
	t.Parallel()
	req := tax.CalculationRequest{
		FromCountry:       "NL",
		ToCountry:         "ES",
		VehiclePriceCents: 1_200_000,
		VehicleAgeMonths:  24,
		VehicleKM:         50_000,
	}
	resp := tax.Calculate(req, map[string]bool{})
	if resp.IsNewVehicle {
		t.Error("IsNewVehicle should be false for age=24/km=50000")
	}
}

// ── 8. EU→CH rate check ───────────────────────────────────────────────────────

func TestEUToCHRate(t *testing.T) {
	t.Parallel()
	req := tax.CalculationRequest{
		FromCountry:       "DE",
		ToCountry:         "CH",
		VehiclePriceCents: 2_000_000,
	}
	resp := tax.Calculate(req, map[string]bool{})
	if len(resp.Routes) != 1 {
		t.Fatalf("want 1 route, got %d", len(resp.Routes))
	}
	r := resp.Routes[0]
	if r.Route.VATRate != 0.081 {
		t.Errorf("EU→CH rate = %.4f, want 0.081 (Swiss MWST)", r.Route.VATRate)
	}
	wantVAT := int64(float64(2_000_000) * 0.081)
	if r.VATAmount != wantVAT {
		t.Errorf("VATAmount = %d, want %d", r.VATAmount, wantVAT)
	}
}

// ── 9. CH→EU rates for all 5 destinations ────────────────────────────────────

func TestCHToEURates(t *testing.T) {
	t.Parallel()
	cases := []struct {
		to   string
		rate float64
	}{
		{"DE", 0.19},
		{"FR", 0.20},
		{"ES", 0.21},
		{"BE", 0.21},
		{"NL", 0.21},
	}
	for _, tc := range cases {
		tc := tc
		t.Run("CH→"+tc.to, func(t *testing.T) {
			t.Parallel()
			req := tax.CalculationRequest{
				FromCountry:       "CH",
				ToCountry:         tc.to,
				VehiclePriceCents: 1_000_000,
			}
			resp := tax.Calculate(req, map[string]bool{})
			if resp.Routes[0].Route.VATRate != tc.rate {
				t.Errorf("CH→%s rate = %.3f, want %.3f", tc.to, resp.Routes[0].Route.VATRate, tc.rate)
			}
		})
	}
}

// ── 10. IsNewVehicle unit tests ───────────────────────────────────────────────

func TestIsNewVehicle(t *testing.T) {
	t.Parallel()
	cases := []struct {
		age, km int
		want    bool
	}{
		{5, 0, true},    // age ≤ 6
		{6, 0, true},    // age = 6 (boundary)
		{7, 0, false},   // age > 6
		{0, 5999, true}, // km ≤ 6000
		{0, 6000, true}, // km = 6000 (boundary)
		{0, 6001, false}, // km > 6000
		{0, 0, false},   // both zero → unknown → not new
		{7, 5000, true}, // km wins even if age > 6
		{4, 7000, true}, // age wins even if km > 6000
	}
	for _, tc := range cases {
		got := tax.IsNewVehicle(tc.age, tc.km)
		if got != tc.want {
			t.Errorf("IsNewVehicle(%d, %d) = %v, want %v", tc.age, tc.km, got, tc.want)
		}
	}
}

// ── 11. Default margin (20% of price) ────────────────────────────────────────

func TestDefaultMargin(t *testing.T) {
	t.Parallel()
	req := tax.CalculationRequest{
		FromCountry:       "BE",
		ToCountry:         "NL",
		VehiclePriceCents: 1_000_000,
		// MarginCents omitted → default 20% = 200 000
	}
	resp := tax.Calculate(req, map[string]bool{})
	if len(resp.Routes) == 0 {
		t.Fatal("no routes returned")
	}
	ms := resp.Routes[len(resp.Routes)-1]
	if ms.MarginAmount != 200_000 {
		t.Errorf("default margin = %d, want 200000 (20%%)", ms.MarginAmount)
	}
}

// ── 12. Response metadata ─────────────────────────────────────────────────────

func TestResponseMetadata(t *testing.T) {
	t.Parallel()
	req := tax.CalculationRequest{
		FromCountry:       "FR",
		ToCountry:         "DE",
		VehiclePriceCents: 1_500_000,
		VehicleAgeMonths:  10,
		VehicleKM:         25_000,
	}
	resp := tax.Calculate(req, map[string]bool{})
	if resp.FromCountry != "FR" {
		t.Errorf("FromCountry = %s, want FR", resp.FromCountry)
	}
	if resp.ToCountry != "DE" {
		t.Errorf("ToCountry = %s, want DE", resp.ToCountry)
	}
	if resp.VehiclePrice != 1_500_000 {
		t.Errorf("VehiclePrice = %d, want 1500000", resp.VehiclePrice)
	}
	if resp.IsNewVehicle {
		t.Error("IsNewVehicle should be false for age=10/km=25000")
	}
}

// ── 13. Unsupported pair returns nil routes ───────────────────────────────────

func TestUnsupportedPair(t *testing.T) {
	t.Parallel()
	req := tax.CalculationRequest{
		FromCountry:       "CH",
		ToCountry:         "CH",
		VehiclePriceCents: 1_000_000,
	}
	resp := tax.Calculate(req, map[string]bool{})
	if len(resp.Routes) != 0 {
		t.Errorf("CH→CH: want 0 routes, got %d", len(resp.Routes))
	}
	if resp.OptimalRoute != nil {
		t.Error("CH→CH: OptimalRoute should be nil")
	}
}

// ── 14. Routes sorted ascending by VATAmount when TotalCost equal ─────────────

func TestRoutesSortedByVATAmountOnTie(t *testing.T) {
	t.Parallel()
	req := tax.CalculationRequest{
		FromCountry:       "NL",
		ToCountry:         "DE",
		VehiclePriceCents: 2_000_000,
		MarginCents:       400_000,
		SellerVATID:       "NL_S",
		BuyerVATID:        "DE_B",
	}
	vies := map[string]bool{"NL_S": true, "DE_B": true}
	resp := tax.Calculate(req, vies)

	for i := 1; i < len(resp.Routes); i++ {
		if resp.Routes[i].VATAmount < resp.Routes[i-1].VATAmount &&
			resp.Routes[i].TotalCost == resp.Routes[i-1].TotalCost {
			t.Errorf("routes[%d].VATAmount=%d < routes[%d].VATAmount=%d with same TotalCost — not sorted",
				i, resp.Routes[i].VATAmount, i-1, resp.Routes[i-1].VATAmount)
		}
	}
}
