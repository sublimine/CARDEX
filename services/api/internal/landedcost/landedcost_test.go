package landedcost

import "testing"

func TestESIEDMTBands(t *testing.T) {
	const price = int64(2_000_000) // €20 000
	tests := []struct {
		name string
		co2  int
		want int64 // expected tax cents
	}{
		{"zero band below 120", 119, 0},
		{"zero band at 120", 120, 0},
		{"4.75% band lower", 121, 95000},
		{"4.75% band at 160", 160, 95000},
		{"9.75% band lower", 161, 195000},
		{"9.75% band at 200", 200, 195000},
		{"14.75% band", 210, 295000},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := RegistrationTax("ES", Vehicle{PriceCents: price, CO2gkm: tc.co2}, RegistrationOptions{})
			if got.TaxCents != tc.want {
				t.Fatalf("ES IEDMT co2=%d: got %d cents, want %d", tc.co2, got.TaxCents, tc.want)
			}
			if got.Method != "ES_IEDMT" {
				t.Errorf("method = %q, want ES_IEDMT", got.Method)
			}
		})
	}
}

func TestDEHasNoRegistrationTax(t *testing.T) {
	got := RegistrationTax("DE", Vehicle{PriceCents: 5_000_000, CO2gkm: 250}, RegistrationOptions{})
	if got.TaxCents != 0 {
		t.Fatalf("DE registration tax = %d, want 0", got.TaxCents)
	}
}

func TestCHAutomobileTax(t *testing.T) {
	got := RegistrationTax("CH", Vehicle{PriceCents: 2_000_000}, RegistrationOptions{})
	if got.TaxCents != 80000 { // 4% of €20 000 = €800
		t.Fatalf("CH auto tax = %d, want 80000", got.TaxCents)
	}
}

func TestVATCostByCorridor(t *testing.T) {
	const price = int64(2_000_000)
	tests := []struct {
		name       string
		from, to   string
		newVehicle bool
		want       int64
	}{
		{"intra-EU used → 0", "DE", "ES", false, 0},
		{"intra-EU new → destination VAT 21%", "DE", "ES", true, 420000},
		{"EU→CH import VAT 8.1%", "DE", "CH", false, 162000},
		{"CH→EU destination VAT 19%", "CH", "DE", false, 380000},
		{"unmodeled corridor → 0", "US", "JP", false, 0},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, _ := VATCost(tc.from, tc.to, price, tc.newVehicle)
			if got != tc.want {
				t.Fatalf("VAT %s→%s new=%v: got %d, want %d", tc.from, tc.to, tc.newVehicle, got, tc.want)
			}
		})
	}
}

func TestIsNewVehicle(t *testing.T) {
	tests := []struct {
		age, km int
		want    bool
	}{
		{3, 50000, true},   // young → new
		{12, 4000, true},   // low km → new
		{12, 50000, false}, // old + high km → used
		{6, 6000, true},    // exactly at thresholds → new
		{0, 0, false},      // unknown → not new
	}
	for _, tc := range tests {
		if got := IsNewVehicle(tc.age, tc.km); got != tc.want {
			t.Errorf("IsNewVehicle(age=%d,km=%d) = %v, want %v", tc.age, tc.km, got, tc.want)
		}
	}
}

func TestTransportCost(t *testing.T) {
	tests := []struct {
		from, to string
		want     int64
	}{
		{"DE", "FR", 75000},
		{"NL", "BE", 30000},
		{"ES", "NL", 180000},
		{"DE", "DE", 0},      // same country
		{"XX", "YY", 300000}, // unknown → penalty
		{"de", "fr", 75000},  // case-insensitive
	}
	for _, tc := range tests {
		if got := TransportCost(tc.from, tc.to); got != tc.want {
			t.Errorf("TransportCost(%s,%s) = %d, want %d", tc.from, tc.to, got, tc.want)
		}
	}
}

func TestNLBPMModel(t *testing.T) {
	// Petrol, CO2=100, age 0:
	//   base 44000 + bracket1(0..79 @200 = 79*200=15800) + bracket2(79..100 @7800 = 21*7800=163800)
	//   = 223600 cents, no depreciation.
	got := nlBPM("NL", Vehicle{PriceCents: 2_000_000, CO2gkm: 100, Fuel: FuelPetrol, AgeMonths: 0})
	if got.TaxCents != 223600 {
		t.Fatalf("NL BPM petrol co2=100 age0: got %d, want 223600", got.TaxCents)
	}
	// Diesel adds (100-70)*10918 = 327540 surcharge.
	gotD := nlBPM("NL", Vehicle{PriceCents: 2_000_000, CO2gkm: 100, Fuel: FuelDiesel, AgeMonths: 0})
	if gotD.TaxCents != 223600+327540 {
		t.Fatalf("NL BPM diesel co2=100 age0: got %d, want %d", gotD.TaxCents, 223600+327540)
	}
	// Electric is exempt.
	gotE := nlBPM("NL", Vehicle{PriceCents: 2_000_000, CO2gkm: 0, Fuel: FuelElectric})
	if gotE.TaxCents != 0 {
		t.Fatalf("NL BPM electric: got %d, want 0", gotE.TaxCents)
	}
	// Depreciation reduces an aged vehicle below its gross.
	gotOld := nlBPM("NL", Vehicle{PriceCents: 2_000_000, CO2gkm: 100, Fuel: FuelPetrol, AgeMonths: 60})
	if gotOld.TaxCents >= got.TaxCents {
		t.Errorf("aged BPM %d should be < new BPM %d", gotOld.TaxCents, got.TaxCents)
	}
}

func TestFRMalusModel(t *testing.T) {
	// CO2=130 is an exact grid anchor: €983.00 = 98300 cents, no abatement at age 0.
	got := frMalus("FR", Vehicle{PriceCents: 2_000_000, CO2gkm: 130, Fuel: FuelPetrol, AgeMonths: 0})
	if got.TaxCents != 98300 {
		t.Fatalf("FR malus co2=130 age0: got %d, want 98300", got.TaxCents)
	}
	// 2-year-old vehicle gets a 20% abatement.
	gotAged := frMalus("FR", Vehicle{PriceCents: 2_000_000, CO2gkm: 130, Fuel: FuelPetrol, AgeMonths: 24})
	if gotAged.TaxCents != 78640 { // 98300 * 0.8
		t.Fatalf("FR malus co2=130 age24: got %d, want 78640", gotAged.TaxCents)
	}
	// Below threshold → 0.
	gotLow := frMalus("FR", Vehicle{PriceCents: 2_000_000, CO2gkm: 100, Fuel: FuelPetrol})
	if gotLow.TaxCents != 0 {
		t.Errorf("FR malus co2=100: got %d, want 0", gotLow.TaxCents)
	}
	// Cap at very high CO2.
	gotCap := frMalus("FR", Vehicle{PriceCents: 2_000_000, CO2gkm: 250, Fuel: FuelPetrol})
	if gotCap.TaxCents != frMalusCapCents {
		t.Errorf("FR malus co2=250: got %d, want cap %d", gotCap.TaxCents, frMalusCapCents)
	}
	// Electric exempt.
	if e := frMalus("FR", Vehicle{CO2gkm: 0, Fuel: FuelElectric}); e.TaxCents != 0 {
		t.Errorf("FR malus electric: got %d, want 0", e.TaxCents)
	}
}

func TestBEFlandersAndRegions(t *testing.T) {
	floor := int64(5150)
	// Electric/zero-emission → Flanders floor.
	if e := RegistrationTax("BE", Vehicle{Fuel: FuelElectric}, RegistrationOptions{}); e.TaxCents != floor {
		t.Errorf("BE Flanders electric: got %d, want floor %d", e.TaxCents, floor)
	}
	// Higher CO2 must cost more than lower CO2 (monotonic) in Flanders.
	low := RegistrationTax("BE", Vehicle{CO2gkm: 120, Fuel: FuelPetrol}, RegistrationOptions{})
	high := RegistrationTax("BE", Vehicle{CO2gkm: 200, Fuel: FuelPetrol}, RegistrationOptions{})
	if !(high.TaxCents > low.TaxCents) {
		t.Errorf("BE Flanders not monotonic: co2=120 → %d, co2=200 → %d", low.TaxCents, high.TaxCents)
	}
	// Wallonia uses the power table: a 90 kW car falls in the €495 band.
	wal := RegistrationTax("BE", Vehicle{PowerKW: 90}, RegistrationOptions{BERegion: BEWallonia})
	if wal.TaxCents != 49500 {
		t.Errorf("BE Wallonia 90kW age0: got %d, want 49500", wal.TaxCents)
	}
	if wal.Method != "BE_TMC_WALLONIA" {
		t.Errorf("method = %q, want BE_TMC_WALLONIA", wal.Method)
	}
}

func TestComputeLandedCostIntraEU(t *testing.T) {
	// DE→ES, used petrol, €20 000, CO2 130, 2 years old.
	b := Compute("DE", "ES", Vehicle{
		PriceCents: 2_000_000, CO2gkm: 130, Fuel: FuelPetrol, AgeMonths: 24, Km: 60000,
	}, RegistrationOptions{})
	// price 20000 + transport 1500 + VAT 0 + IEDMT 4.75%*20000=950 + admin 100 = 22550
	if b.TotalLandedCostEUR != 22550.00 {
		t.Fatalf("DE→ES total = %.2f, want 22550.00", b.TotalLandedCostEUR)
	}
	if b.VATEUR != 0 {
		t.Errorf("intra-EU used VAT = %.2f, want 0", b.VATEUR)
	}
	if b.RegistrationTaxEUR != 950.00 {
		t.Errorf("ES registration = %.2f, want 950.00", b.RegistrationTaxEUR)
	}
}

func TestComputeLandedCostToSwitzerland(t *testing.T) {
	// DE→CH, used petrol, €20 000, CO2 130, 2 years old.
	b := Compute("DE", "CH", Vehicle{
		PriceCents: 2_000_000, CO2gkm: 130, Fuel: FuelPetrol, AgeMonths: 24, Km: 60000,
	}, RegistrationOptions{})
	// price 20000 + transport 600 + import VAT 8.1%*20000=1620 + auto tax 4%*20000=800 + admin 400 = 23420
	if b.TotalLandedCostEUR != 23420.00 {
		t.Fatalf("DE→CH total = %.2f, want 23420.00", b.TotalLandedCostEUR)
	}
	if b.VATEUR != 1620.00 {
		t.Errorf("EU→CH VAT = %.2f, want 1620.00", b.VATEUR)
	}
	if b.RegistrationTaxEUR != 800.00 {
		t.Errorf("CH auto tax = %.2f, want 800.00", b.RegistrationTaxEUR)
	}
}

func TestNormalizeFuel(t *testing.T) {
	tests := []struct {
		in   string
		want Fuel
	}{
		{"Diesel", FuelDiesel},
		{"Gasoil", FuelDiesel},
		{"Benzin", FuelPetrol},
		{"Essence", FuelPetrol},
		{"Electric", FuelElectric},
		{"BEV", FuelElectric},
		{"Plug-in Hybrid", FuelHybrid},
		{"LPG", FuelLPG},
		{"CNG", FuelCNG},
		{"", FuelUnknown},
	}
	for _, tc := range tests {
		if got := NormalizeFuel(tc.in); got != tc.want {
			t.Errorf("NormalizeFuel(%q) = %q, want %q", tc.in, got, tc.want)
		}
	}
}
