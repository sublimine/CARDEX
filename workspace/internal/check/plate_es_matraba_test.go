package check

import (
	"context"
	"testing"
	"time"

	"cardex.eu/workspace/internal/check/matraba"
)

// fakeMATRABA is a stand-in for *matraba.Store that returns pre-seeded
// records without touching SQLite. Keeps the ES enrichment tests fast
// and hermetic.
type fakeMATRABA struct {
	byVIN    map[string]matraba.Record
	byPrefix map[string][]matraba.Record
}

func (f *fakeMATRABA) LookupByVIN(_ context.Context, vin string) (matraba.Record, bool, error) {
	r, ok := f.byVIN[vin]
	return r, ok, nil
}

func (f *fakeMATRABA) LookupByPrefix(_ context.Context, prefix string, limit int) ([]matraba.Record, error) {
	_ = limit
	return f.byPrefix[prefix], nil
}

func TestApplyMATRABAMergesEmptyFields(t *testing.T) {
	first := time.Date(2015, 5, 12, 0, 0, 0, 0, time.UTC)
	rec := matraba.Record{
		Bastidor:             "WVGZZZ5NZAW021819",
		MarcaITV:             "VOLKSWAGEN",
		ModeloITV:            "TIGUAN",
		VersionITV:           "2.0 TDI 4MOTION",
		CodPropulsionITV:     "1",
		CilindradaCC:         1968,
		PotenciaKW:           125,
		MasaOrdenMarchaKg:    1700,
		MasaMaxTecnicaKg:     2300,
		NumPlazas:            5,
		NivelEmisionesEURO:   "EURO5",
		CO2GPerKm:            185,
		CatHomologacionUE:    "M1",
		CodTipo:              "40",
		ContrasenaHomolog:    "E12*0048*01",
		DistanciaEjes12Mm:    2604,
		CodProvinciaVeh:      "28",
		NumTitulares:         3,
		FecPrimMatriculacion: first,
	}
	result := &PlateResult{Plate: "8000LVY", Country: "ES"}
	applyMATRABAToResult(rec, result)

	if result.VIN != "WVGZZZ5NZAW021819" {
		t.Errorf("VIN = %q", result.VIN)
	}
	if result.Make != "VOLKSWAGEN" {
		t.Errorf("Make = %q", result.Make)
	}
	if result.Model != "TIGUAN" {
		t.Errorf("Model = %q", result.Model)
	}
	if result.FuelType != "Diésel" {
		t.Errorf("FuelType = %q, want Diésel", result.FuelType)
	}
	if result.DisplacementCC != 1968 {
		t.Errorf("DisplacementCC = %d", result.DisplacementCC)
	}
	if result.PowerKW != 125 {
		t.Errorf("PowerKW = %v", result.PowerKW)
	}
	if result.EmptyWeightKg != 1700 {
		t.Errorf("EmptyWeightKg = %d", result.EmptyWeightKg)
	}
	if result.GrossWeightKg != 2300 {
		t.Errorf("GrossWeightKg = %d", result.GrossWeightKg)
	}
	if result.NumberOfSeats != 5 {
		t.Errorf("NumberOfSeats = %d", result.NumberOfSeats)
	}
	if result.EuroNorm != "EURO5" {
		t.Errorf("EuroNorm = %q", result.EuroNorm)
	}
	if result.CO2GPerKm != 185 {
		t.Errorf("CO2 = %v", result.CO2GPerKm)
	}
	if result.EuropeanVehicleCategory != "M1" {
		t.Errorf("EuropeanVehicleCategory = %q", result.EuropeanVehicleCategory)
	}
	if result.VehicleType != "Turismo" {
		t.Errorf("VehicleType = %q", result.VehicleType)
	}
	if result.TypeApprovalNumber != "E12*0048*01" {
		t.Errorf("TypeApprovalNumber = %q", result.TypeApprovalNumber)
	}
	if result.WheelbaseCm != 260 {
		t.Errorf("WheelbaseCm = %d (want 260, from 2604mm)", result.WheelbaseCm)
	}
	if result.District != "Madrid" {
		t.Errorf("District = %q, want Madrid", result.District)
	}
	if result.PreviousOwners != 3 {
		t.Errorf("PreviousOwners = %d", result.PreviousOwners)
	}
	if result.FirstRegistration == nil || !result.FirstRegistration.Equal(first) {
		t.Errorf("FirstRegistration = %v, want %v", result.FirstRegistration, first)
	}
}

func TestApplyMATRABAPreservesCMFields(t *testing.T) {
	// CM already filled these; MATRABA must not overwrite.
	result := &PlateResult{
		VIN:            "WVGZZZ5NZAW021819",
		Make:           "VW",
		Model:          "Tiguan",
		Variant:        "2.0 TDI 4motion | 170 cv",
		FuelType:       "Diésel",
		DisplacementCC: 1968,
		PowerKW:        125,
		PreviousOwners: 3,
	}
	rec := matraba.Record{
		Bastidor:       "WVGZZZ5NZAW021819",
		MarcaITV:       "VOLKSWAGEN", // longer/uppercase — NOT preferred over CM's "VW"
		ModeloITV:      "TIGUAN",
		VersionITV:     "Different",
		PotenciaKW:     130,
		NumTitulares:   10,
		CilindradaCC:   9999,
	}
	applyMATRABAToResult(rec, result)

	if result.Make != "VW" {
		t.Errorf("Make got overwritten: %q", result.Make)
	}
	if result.Model != "Tiguan" {
		t.Errorf("Model got overwritten: %q", result.Model)
	}
	if result.Variant != "2.0 TDI 4motion | 170 cv" {
		t.Errorf("Variant got overwritten: %q", result.Variant)
	}
	if result.DisplacementCC != 1968 {
		t.Errorf("CC got overwritten: %d", result.DisplacementCC)
	}
	if result.PowerKW != 125 {
		t.Errorf("PowerKW got overwritten: %v", result.PowerKW)
	}
	if result.PreviousOwners != 3 {
		t.Errorf("Owners got overwritten: %d", result.PreviousOwners)
	}
}

func TestEnrichWithMATRABAExactVIN(t *testing.T) {
	store := &fakeMATRABA{
		byVIN: map[string]matraba.Record{
			"WVGZZZ5NZAW021819": {
				Bastidor:          "WVGZZZ5NZAW021819",
				MasaOrdenMarchaKg: 1700,
				CodProvinciaVeh:   "28",
			},
		},
	}
	r := newESPlateResolver(nil).WithMATRABA(store)
	result := &PlateResult{VIN: "WVGZZZ5NZAW021819"}
	if err := r.enrichWithMATRABA(context.Background(), result); err != nil {
		t.Fatalf("enrich: %v", err)
	}
	if result.EmptyWeightKg != 1700 {
		t.Errorf("EmptyWeightKg = %d", result.EmptyWeightKg)
	}
	if result.District != "Madrid" {
		t.Errorf("District = %q", result.District)
	}
}

func TestEnrichWithMATRABAPrefixFallback(t *testing.T) {
	// Post-2025 masked VIN: full 17 chars but last 10 are literal data that
	// still happen to mismatch what's in the index. enrichWithMATRABA should
	// fall back to prefix matching on the first 11 chars and accept the
	// first hit whose make agrees.
	store := &fakeMATRABA{
		byVIN: map[string]matraba.Record{},
		byPrefix: map[string][]matraba.Record{
			"WVGZZZ5NZAW": {
				{Bastidor: "WVGZZZ5NZAW099999", MarcaITV: "AUDI"},
				{Bastidor: "WVGZZZ5NZAW123456", MarcaITV: "VOLKSWAGEN", NivelEmisionesEURO: "EURO5"},
			},
		},
	}
	r := newESPlateResolver(nil).WithMATRABA(store)
	result := &PlateResult{
		VIN:  "WVGZZZ5NZAW555555",
		Make: "Volkswagen",
	}
	if err := r.enrichWithMATRABA(context.Background(), result); err != nil {
		t.Fatalf("enrich: %v", err)
	}
	if result.EuroNorm != "EURO5" {
		t.Errorf("prefix fallback did not merge: EuroNorm = %q", result.EuroNorm)
	}
}

func TestEnrichWithMATRABANoStore(t *testing.T) {
	r := newESPlateResolver(nil)
	result := &PlateResult{VIN: "XXX"}
	// No store attached — must be a clean no-op.
	if err := r.enrichWithMATRABA(context.Background(), result); err != nil {
		t.Errorf("no-store enrich returned error: %v", err)
	}
}

func TestEnrichWithMATRABANoVIN(t *testing.T) {
	store := &fakeMATRABA{}
	r := newESPlateResolver(nil).WithMATRABA(store)
	result := &PlateResult{Plate: "1234ABC"}
	if err := r.enrichWithMATRABA(context.Background(), result); err != nil {
		t.Errorf("no-VIN enrich returned error: %v", err)
	}
	if result.EmptyWeightKg != 0 {
		t.Errorf("result mutated without a VIN: %+v", result)
	}
}
