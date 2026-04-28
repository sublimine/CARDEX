package check

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

type stubDossierResolver struct {
	result *PlateResult
	err    error
}

func (s *stubDossierResolver) Resolve(_ context.Context, _ string) (*PlateResult, error) {
	return s.result, s.err
}

func mustParseTime(s string) *time.Time {
	t, _ := time.Parse(time.RFC3339, s)
	return &t
}

func TestDossierFromPlate_NLFullData(t *testing.T) {
	reg := mustParseTime("2018-09-19T00:00:00Z")
	insp := mustParseTime("2025-09-17T10:43:00Z")
	next := mustParseTime("2026-09-19T00:00:00Z")

	p := &PlateResult{
		Plate:                "12BKP6",
		Country:              "NL",
		Make:                 "DAF",
		Model:                "XF 480 FT",
		FuelType:             "Diesel",
		DisplacementCC:       12902,
		PowerKW:              355,
		CurbWeightKg:         8377,
		GrossWeightKg:        20500,
		LengthCm:             616,
		WidthCm:              255,
		TechnicalMaxMassKg:   20500,
		FirstRegistration:    reg,
		RegistrationStatus:   "active",
		LastInspectionDate:   insp,
		LastInspectionResult: "pass",
		NextInspectionDate:   next,
		APKHistory:           []APKEntry{{Date: *insp, Result: "pass"}},
		NCAPStars:            4,
		NCAPRatingYear:       2023,
		Source:               "RDW",
		FetchedAt:            time.Now(),
	}

	sources := []DataSource{{ID: "plate-resolver", Name: "RDW", Country: "NL", Status: StatusSuccess}}
	d := dossierFromPlate(p, sources)

	if d.Identity.Make != "DAF" {
		t.Errorf("make: want DAF, got %s", d.Identity.Make)
	}
	if d.Completeness.Identity != SectionFull {
		t.Errorf("identity completeness: want full, got %s", d.Completeness.Identity)
	}
	if d.Completeness.Technical != SectionFull {
		t.Errorf("technical completeness: want full, got %s", d.Completeness.Technical)
	}
	if d.Completeness.Inspections != SectionFull {
		t.Errorf("inspections completeness: want full, got %s", d.Completeness.Inspections)
	}
	if d.Legal.HasAlerts {
		t.Error("legal: expected no alerts")
	}
	if d.Safety.NCAPStars != 4 {
		t.Errorf("ncap stars: want 4, got %d", d.Safety.NCAPStars)
	}
	if d.Dimensions.LengthCm != 616 {
		t.Errorf("length_cm: want 616, got %d", d.Dimensions.LengthCm)
	}
}

func TestDossierFromPlate_ESPartialData(t *testing.T) {
	p := &PlateResult{
		Plate:              "8000LVY",
		Country:            "ES",
		EnvironmentalBadge: "B",
		Partial:            true,
		Source:             "DGT",
		FetchedAt:          time.Now(),
	}

	sources := []DataSource{{ID: "plate-resolver", Name: "DGT", Country: "ES", Status: StatusSuccess}}
	d := dossierFromPlate(p, sources)

	if d.Identity.Make != "" {
		t.Errorf("make: expected empty, got %s", d.Identity.Make)
	}
	if d.Completeness.Identity != SectionPartial {
		t.Errorf("identity completeness: want partial, got %s", d.Completeness.Identity)
	}
	if d.Registration.EnvironmentalBadge != "B" {
		t.Errorf("env badge: want B, got %s", d.Registration.EnvironmentalBadge)
	}
}

func TestDossierFromPlate_ESLegalAlerts(t *testing.T) {
	p := &PlateResult{
		Plate:         "1234ABC",
		Country:       "ES",
		Make:          "VOLKSWAGEN",
		Model:         "GOLF",
		EmbargoFlag:   true,
		TransferCount: 3,
		Source:        "MATRABA",
		FetchedAt:     time.Now(),
	}

	sources := []DataSource{{ID: "plate-resolver", Name: "MATRABA", Country: "ES", Status: StatusSuccess}}
	d := dossierFromPlate(p, sources)

	if !d.Legal.HasAlerts {
		t.Error("expected HasAlerts=true for embargoed vehicle")
	}
	if !d.Legal.EmbargoFlag {
		t.Error("expected EmbargoFlag=true")
	}
	if d.Ownership.TransferCount != 3 {
		t.Errorf("transfer count: want 3, got %d", d.Ownership.TransferCount)
	}
}

func TestDossierFromPlate_FRNCAPFull(t *testing.T) {
	reg := mustParseTime("2008-01-01T00:00:00Z")
	p := &PlateResult{
		Plate:             "AB123CD",
		Country:           "FR",
		Make:              "Mercedes-Benz",
		Model:             "CLASSE S",
		FuelType:          "Gazole",
		DisplacementCC:    2987,
		Color:             "Gris",
		FirstRegistration: reg,
		NCAPStars:         5,
		NCAPRatingYear:    2025,
		Partial:           true,
		Source:            "immatriculation-auto.info",
		FetchedAt:         time.Now(),
	}

	sources := []DataSource{{ID: "plate-resolver", Name: "immatriculation-auto.info", Country: "FR", Status: StatusSuccess}}
	d := dossierFromPlate(p, sources)

	if d.Identity.Make != "Mercedes-Benz" {
		t.Errorf("make: want Mercedes-Benz, got %s", d.Identity.Make)
	}
	if d.Safety.NCAPStars != 5 {
		t.Errorf("ncap: want 5, got %d", d.Safety.NCAPStars)
	}
	if d.Completeness.Safety != SectionFull {
		t.Errorf("safety completeness: want full, got %s", d.Completeness.Safety)
	}
}

func TestDossierCompleteness_Unavailable(t *testing.T) {
	p := &PlateResult{
		Plate:     "UNKNOWN",
		Country:   "DE",
		Source:    "stub",
		FetchedAt: time.Now(),
	}
	d := dossierFromPlate(p, nil)

	if d.Completeness.Technical != SectionUnavailable {
		t.Errorf("technical: want unavailable, got %s", d.Completeness.Technical)
	}
	if d.Completeness.Inspections != SectionUnavailable {
		t.Errorf("inspections: want unavailable, got %s", d.Completeness.Inspections)
	}
	if d.Completeness.Safety != SectionUnavailable {
		t.Errorf("safety: want unavailable, got %s", d.Completeness.Safety)
	}
}

func TestDossierHandler_OK(t *testing.T) {
	reg := mustParseTime("2020-01-01T00:00:00Z")
	fixed := &PlateResult{
		Plate:             "TEST123",
		Country:           "NL",
		Make:              "BMW",
		Model:             "3 Series",
		FuelType:          "Petrol",
		PowerKW:           110,
		FirstRegistration: reg,
		Source:            "stub",
		FetchedAt:         time.Now(),
	}
	registry := NewPlateRegistryFromMap(map[string]PlateResolver{
		"NL": &stubDossierResolver{result: fixed},
	})

	handler := NewDossierHandler(registry, nil)
	mux := http.NewServeMux()
	handler.Register(mux)

	req := httptest.NewRequest("GET", "/api/v1/dossier/NL/TEST123", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("status: want 200, got %d — body: %s", w.Code, w.Body.String())
	}
	var d VehicleDossier
	if err := json.NewDecoder(w.Body).Decode(&d); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if d.Identity.Make != "BMW" {
		t.Errorf("make: want BMW, got %s", d.Identity.Make)
	}
	if d.QueryCountry != "NL" {
		t.Errorf("query_country: want NL, got %s", d.QueryCountry)
	}
}

func TestDossierHandler_UnsupportedCountry(t *testing.T) {
	registry := NewPlateRegistryFromMap(map[string]PlateResolver{})
	handler := NewDossierHandler(registry, nil)
	mux := http.NewServeMux()
	handler.Register(mux)

	req := httptest.NewRequest("GET", "/api/v1/dossier/JP/ABC123", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("status: want 503, got %d", w.Code)
	}
}

func TestDossierHandler_NotFound(t *testing.T) {
	registry := NewPlateRegistryFromMap(map[string]PlateResolver{
		"NL": &stubDossierResolver{err: ErrPlateNotFound},
	})
	handler := NewDossierHandler(registry, nil)
	mux := http.NewServeMux()
	handler.Register(mux)

	req := httptest.NewRequest("GET", "/api/v1/dossier/NL/NOTEXIST", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("status: want 404, got %d", w.Code)
	}
}
