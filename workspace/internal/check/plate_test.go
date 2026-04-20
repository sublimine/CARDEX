package check_test

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"cardex.eu/workspace/internal/check"
)

// ── NormalizePlate ────────────────────────────────────────────────────────────

func TestNormalizePlate(t *testing.T) {
	cases := []struct{ in, want string }{
		{"AB-12-CD", "AB12CD"},
		{"ab 12 cd", "AB12CD"},
		{"1-ABC-23", "1ABC23"},
		{"abc123", "ABC123"},
		{"  NL-123  ", "NL123"},
		{"GV-123-B", "GV123B"},
		{"ALREADY", "ALREADY"},
		{"ZH 123456", "ZH123456"},
		{"M-AB 1234", "MAB1234"},
	}
	for _, tc := range cases {
		got := check.NormalizePlate(tc.in)
		if got != tc.want {
			t.Errorf("NormalizePlate(%q) = %q, want %q", tc.in, got, tc.want)
		}
	}
}

// ── NL plate resolver ─────────────────────────────────────────────────────────

func rdwPlateServer(rows []map[string]string) *httptest.Server {
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(rows)
	}))
}

func TestNLPlateResolver_OK(t *testing.T) {
	srv := rdwPlateServer([]map[string]string{
		{
			"kenteken":                    "GV123B",
			"voertuigidentificatienummer": validVIN,
			"merk":                        "BMW",
			"handelsbenaming":             "3 Series",
			"brandstof_omschrijving":      "Benzine",
			"massa_ledig_voertuig":        "1420",
			"netto_maximumvermogen":       "135",
			"eerste_kleur":                "GRIJS",
		},
	})
	defer srv.Close()

	r := check.NewNLPlateResolverWithBase(srv.URL)
	result, err := r.Resolve(context.Background(), "GV123B")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.VIN != validVIN {
		t.Errorf("got VIN %q, want %q", result.VIN, validVIN)
	}
	if result.Make != "BMW" {
		t.Errorf("Make = %q, want BMW", result.Make)
	}
	if result.FuelType != "Benzine" {
		t.Errorf("FuelType = %q, want Benzine", result.FuelType)
	}
	if result.EmptyWeightKg != 1420 {
		t.Errorf("EmptyWeightKg = %d, want 1420", result.EmptyWeightKg)
	}
	if result.PowerKW != 135 {
		t.Errorf("PowerKW = %f, want 135", result.PowerKW)
	}
	if result.Color != "GRIJS" {
		t.Errorf("Color = %q, want GRIJS", result.Color)
	}
}

func TestNLPlateResolver_NormalizesBeforeQuery(t *testing.T) {
	var gotQuery string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotQuery = r.URL.RawQuery
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode([]map[string]string{
			{"kenteken": "GV123B", "voertuigidentificatienummer": validVIN},
		})
	}))
	defer srv.Close()

	reg := check.NewPlateRegistry(srv.URL)
	_, err := reg.Resolve(context.Background(), "gv-123-b", "NL")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(gotQuery, "GV123B") {
		t.Errorf("expected query to contain GV123B, got %q", gotQuery)
	}
}

func TestNLPlateResolver_NotFound(t *testing.T) {
	srv := rdwPlateServer(nil) // empty array
	defer srv.Close()

	r := check.NewNLPlateResolverWithBase(srv.URL)
	_, err := r.Resolve(context.Background(), "NOTFOUND")
	if !errors.Is(err, check.ErrPlateNotFound) {
		t.Errorf("want ErrPlateNotFound, got %v", err)
	}
}

func TestNLPlateResolver_EmptyVINField(t *testing.T) {
	// RDW does NOT expose voertuigidentificatienummer in the m9d7-ebf2 dataset.
	// The resolver must return vehicle data (not an error) when VIN is absent.
	srv := rdwPlateServer([]map[string]string{
		{"kenteken": "XX0000", "merk": "FIAT", "handelsbenaming": "500", "voertuigidentificatienummer": ""},
	})
	defer srv.Close()

	r := check.NewNLPlateResolverWithBase(srv.URL)
	result, err := r.Resolve(context.Background(), "XX0000")
	if err != nil {
		t.Fatalf("expected no error when VIN is empty, got %v", err)
	}
	if result.VIN != "" {
		t.Errorf("expected empty VIN when field is absent, got %q", result.VIN)
	}
	if result.Make != "FIAT" {
		t.Errorf("expected Make=FIAT, got %q", result.Make)
	}
}

func TestNLPlateResolver_ServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	r := check.NewNLPlateResolverWithBase(srv.URL)
	_, err := r.Resolve(context.Background(), "XX1234")
	if err == nil {
		t.Fatal("expected error for HTTP 500, got nil")
	}
}

// TestNLPlateResolver_FullCoverage asserts that the resolver extracts every field
// the RDW datasets expose for a real vehicle. Fixture is the recorded response
// for plate 3TKZ08 (FIAT 500, 2014). If RDW adds new fields, the expectation list
// below should be expanded.
func TestNLPlateResolver_FullCoverage(t *testing.T) {
	// Route Socrata dataset requests to the right fixture based on URL path.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case strings.Contains(r.URL.Path, "m9d7-ebf2"): // main vehicle
			fmt.Fprint(w, `[{"kenteken":"3TKZ08","voertuigsoort":"Personenauto","merk":"FIAT","handelsbenaming":"FIAT 500","vervaldatum_apk":"20250504","inrichting":"hatchback","aantal_zitplaatsen":"4","eerste_kleur":"ZWART","tweede_kleur":"Niet geregistreerd","aantal_cilinders":"2","cilinderinhoud":"964","massa_ledig_voertuig":"840","toegestane_maximum_massa_voertuig":"1305","maximum_massa_trekken_ongeremd":"400","maximum_trekken_massa_geremd":"800","datum_eerste_toelating":"20140318","catalogusprijs":"15280","wam_verzekerd":"Nee","aantal_deuren":"2","aantal_wielen":"4","europese_voertuigcategorie":"M1","variant":"AXP1A","typegoedkeuringsnummer":"e3*2007/46*0064*16","wielbasis":"230","export_indicator":"Ja","openstaande_terugroepactie_indicator":"Nee","taxi_indicator":"Nee","jaar_laatste_registratie_tellerstand":"2024","tellerstandoordeel":"Logisch","zuinigheidsclassificatie":"A"}]`)
		case strings.Contains(r.URL.Path, "8ys7-d773"): // fuel
			fmt.Fprint(w, `[{"kenteken":"3TKZ08","brandstof_omschrijving":"Benzine","brandstofverbruik_buiten":"3.40","brandstofverbruik_gecombineerd":"3.80","brandstofverbruik_stad":"4.60","co2_uitstoot_gecombineerd":"88","geluidsniveau_stationair":"82","emissiecode_omschrijving":"6","nettomaximumvermogen":"44.00","roetuitstoot":"0.52","uitlaatemissieniveau":"EURO 6 W"}]`)
		case strings.Contains(r.URL.Path, "sgfe-77wx"): // APK
			fmt.Fprint(w, `[{"kenteken":"3TKZ08","soort_erkenning_omschrijving":"APK Lichte voertuigen","soort_melding_ki_omschrijving":"periodieke controle","meld_datum_door_keuringsinstantie_dt":"2024-04-16T15:37:00.000","vervaldatum_keuring_dt":"2025-05-04T00:00:00.000"}]`)
		case strings.Contains(r.URL.Path, "a34c-vvps"): // defects
			fmt.Fprint(w, `[{"kenteken":"3TKZ08","gebrek_identificatie":"210","aantal_gebreken_geconstateerd":"4","meld_datum_door_keuringsinstantie_dt":"2024-04-16T15:37:00.000"}]`)
		case strings.Contains(r.URL.Path, "3huj-srit"): // axles
			fmt.Fprint(w, `[{"kenteken":"3TKZ08","as_nummer":"1","aantal_assen":"2"},{"kenteken":"3TKZ08","as_nummer":"2","aantal_assen":"2"}]`)
		case strings.Contains(r.URL.Path, "vezc-m2t6"): // body
			fmt.Fprint(w, `[{"kenteken":"3TKZ08","carrosserietype":"AB","type_carrosserie_europese_omschrijving":"Hatchback"}]`)
		default:
			fmt.Fprint(w, "[]")
		}
	}))
	defer srv.Close()

	r := check.NewNLPlateResolverWithBase(srv.URL)
	res, err := r.Resolve(context.Background(), "3TKZ08")
	if err != nil {
		t.Fatalf("Resolve: %v", err)
	}

	cases := []struct {
		name string
		got  interface{}
		want interface{}
	}{
		// main dataset
		{"Make", res.Make, "FIAT"},
		{"Model", res.Model, "FIAT 500"},
		{"Variant", res.Variant, "AXP1A"},
		{"Color", res.Color, "ZWART"},
		{"SecondaryColor (sentinel suppressed)", res.SecondaryColor, ""},
		{"VehicleType", res.VehicleType, "Personenauto"},
		{"EuropeanVehicleCategory", res.EuropeanVehicleCategory, "M1"},
		{"TypeApprovalNumber", res.TypeApprovalNumber, "e3*2007/46*0064*16"},
		{"EnergyLabel", res.EnergyLabel, "A"},
		{"DisplacementCC", res.DisplacementCC, 964},
		{"NumberOfCylinders", res.NumberOfCylinders, 2},
		{"NumberOfSeats", res.NumberOfSeats, 4},
		{"NumberOfDoors", res.NumberOfDoors, 2},
		{"NumberOfWheels", res.NumberOfWheels, 4},
		{"NumberOfAxles", res.NumberOfAxles, 2},
		{"WheelbaseCm", res.WheelbaseCm, 230},
		{"EmptyWeightKg", res.EmptyWeightKg, 840},
		{"GrossWeightKg", res.GrossWeightKg, 1305},
		{"CataloguePriceEUR", res.CataloguePriceEUR, 15280},
		{"MaxTrailerWeightBrakedKg", res.MaxTrailerWeightBrakedKg, 800},
		{"MaxTrailerWeightUnbrakedKg", res.MaxTrailerWeightUnbrakedKg, 400},
		{"OdometerStatus", res.OdometerStatus, "Logisch"},
		{"LastMileageRegistrationYear", res.LastMileageRegistrationYear, 2024},
		{"ExportIndicator", res.ExportIndicator, true},
		{"OpenRecall", res.OpenRecall, false},
		{"TaxiIndicator", res.TaxiIndicator, false},
		{"RegistrationStatus", res.RegistrationStatus, "uninsured"},
		// fuel dataset
		{"FuelType", res.FuelType, "Benzine"},
		{"EuroNorm", res.EuroNorm, "EURO 6 W"},
		{"PowerKW", res.PowerKW, 44.0},
		{"CO2GPerKm", res.CO2GPerKm, 88.0},
		{"FuelConsumptionCombinedL100km", res.FuelConsumptionCombinedL100km, 3.8},
		{"FuelConsumptionCityL100km", res.FuelConsumptionCityL100km, 4.6},
		{"FuelConsumptionExtraUrbanL100km", res.FuelConsumptionExtraUrbanL100km, 3.4},
		{"StationaryNoiseDb", res.StationaryNoiseDb, 82.0},
		{"SootEmission", res.SootEmission, 0.52},
		{"EmissionCode", res.EmissionCode, "6"},
		// body dataset (overrides inrichting)
		{"BodyType (European)", res.BodyType, "Hatchback"},
		// inspection
		{"LastInspectionResult", res.LastInspectionResult, "pass"},
	}
	for _, tc := range cases {
		if tc.got != tc.want {
			t.Errorf("%s = %v (%T), want %v (%T)", tc.name, tc.got, tc.got, tc.want, tc.want)
		}
	}

	if res.FirstRegistration == nil || res.FirstRegistration.Year() != 2014 {
		t.Errorf("FirstRegistration: got %v, want year 2014", res.FirstRegistration)
	}
	if res.LastInspectionDate == nil || res.LastInspectionDate.Year() != 2024 {
		t.Errorf("LastInspectionDate: got %v, want 2024", res.LastInspectionDate)
	}
	if res.NextInspectionDate == nil || res.NextInspectionDate.Year() != 2025 {
		t.Errorf("NextInspectionDate: got %v, want 2025", res.NextInspectionDate)
	}
	if got := len(res.APKHistory); got != 1 {
		t.Fatalf("APKHistory length = %d, want 1", got)
	}
	ins := res.APKHistory[0]
	if ins.DefectsFound != 4 {
		t.Errorf("APKHistory[0].DefectsFound = %d, want 4", ins.DefectsFound)
	}
	if ins.Result != "pass" {
		t.Errorf("APKHistory[0].Result = %q, want pass", ins.Result)
	}
	if ins.InspectionType != "APK Lichte voertuigen" {
		t.Errorf("APKHistory[0].InspectionType = %q", ins.InspectionType)
	}
}

func TestNLPlateResolver_UppercasesVIN(t *testing.T) {
	srv := rdwPlateServer([]map[string]string{
		{"kenteken": "XX1234", "voertuigidentificatienummer": "wba3c5c5xdf773941"},
	})
	defer srv.Close()

	r := check.NewNLPlateResolverWithBase(srv.URL)
	result, err := r.Resolve(context.Background(), "XX1234")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.VIN != "WBA3C5C5XDF773941" {
		t.Errorf("VIN not uppercased: got %q", result.VIN)
	}
}

// ── PlateRegistry ─────────────────────────────────────────────────────────────

func TestPlateRegistry_NL_Live(t *testing.T) {
	srv := rdwPlateServer([]map[string]string{
		{"kenteken": "GV123B", "voertuigidentificatienummer": validVIN},
	})
	defer srv.Close()

	reg := check.NewPlateRegistry(srv.URL)
	result, err := reg.Resolve(context.Background(), "GV-123-B", "NL")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.VIN != validVIN {
		t.Errorf("got VIN %q, want %q", result.VIN, validVIN)
	}
}

func TestPlateRegistry_UnknownCountry(t *testing.T) {
	reg := check.NewPlateRegistry("http://localhost:0")
	_, err := reg.Resolve(context.Background(), "AB1234", "IT")
	if !errors.Is(err, check.ErrPlateResolutionUnavailable) {
		t.Errorf("want ErrPlateResolutionUnavailable for unknown country, got %v", err)
	}
}

func TestPlateRegistry_CountryNormalized(t *testing.T) {
	srv := rdwPlateServer([]map[string]string{
		{"kenteken": "XX1234", "voertuigidentificatienummer": validVIN},
	})
	defer srv.Close()

	reg := check.NewPlateRegistry(srv.URL)
	_, err := reg.Resolve(context.Background(), "XX1234", "nl")
	if err != nil {
		t.Errorf("lowercase country code should work: %v", err)
	}
}

// ── NL enrichment helpers ─────────────────────────────────────────────────────

// rdwMultiServer routes requests by RDW dataset ID embedded in the URL path.
// Any unregistered path returns an empty JSON array so best-effort fetches
// degrade gracefully.
func rdwMultiServer(t *testing.T, routes map[string][]map[string]string) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		for dsID, rows := range routes {
			if strings.Contains(r.URL.Path, "/"+dsID+".json") {
				_ = json.NewEncoder(w).Encode(rows)
				return
			}
		}
		_ = json.NewEncoder(w).Encode([]map[string]string{})
	}))
}

func TestNLPlateResolver_FullEnrichment(t *testing.T) {
	inspDate := "2024-03-15T10:00:00.000"
	nextAPK := "2025-03-15T10:00:00.000"

	srv := rdwMultiServer(t, map[string][]map[string]string{
		"m9d7-ebf2": {{
			"kenteken":                              "3TKZ08",
			"voertuigidentificatienummer":           validVIN,
			"merk":                                  "TOYOTA",
			"handelsbenaming":                       "YARIS",
			"inrichting":                            "HATCHBACK",
			"eerste_kleur":                          "ROOD",
			"massa_ledig_voertuig":                  "985",
			"toegestane_maximum_massa_voertuig":     "1395",
			"cilinderinhoud":                        "998",
			"aantal_cilinders":                      "3",
			"aantal_zitplaatsen":                    "5",
			"aantal_deuren":                         "5",
			"datum_eerste_toelating":                "20180301",
			"vervaldatum_apk":                       "20250301",
			"wam_verzekerd":                         "Ja",
			"tellerstandoordeel":                    "Logisch",
			"export_indicator":                      "Nee",
			"openstaande_terugroepactie_indicator":  "Nee",
		}},
		"8ys7-d773": {{
			"kenteken":                        "3TKZ08",
			"brandstof_omschrijving":          "Benzine",
			"nettomaximumvermogen":            "72",
			"co2_uitstoot_gecombineerd":       "116",
			"uitlaatemissieniveau":            "EURO 6",
			"brandstofverbruik_gecombineerd":  "5.0",
		}},
		"sgfe-77wx": {{
			"kenteken":                              "3TKZ08",
			"meld_datum_door_keuringsinstantie_dt":  inspDate,
			"soort_erkenning_omschrijving":          "GARAGE A",
			"vervaldatum_keuring_dt":                nextAPK,
		}},
		"a34c-vvps": {},
		"3huj-srit": {
			{"kenteken": "3TKZ08", "as_nummer": "1", "spoorbreedte": "1485"},
			{"kenteken": "3TKZ08", "as_nummer": "2", "spoorbreedte": "1480"},
		},
		"vezc-m2t6": {{
			"kenteken":                                 "3TKZ08",
			"type_carrosserie_europese_omschrijving":   "HATCHBACK",
		}},
	})
	defer srv.Close()

	r := check.NewNLPlateResolverWithBase(srv.URL)
	result, err := r.Resolve(context.Background(), "3TKZ08")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Basic
	if result.Make != "TOYOTA" {
		t.Errorf("Make = %q, want TOYOTA", result.Make)
	}
	if result.NumberOfDoors != 5 {
		t.Errorf("NumberOfDoors = %d, want 5", result.NumberOfDoors)
	}
	if result.OdometerStatus != "Logisch" {
		t.Errorf("OdometerStatus = %q, want Logisch", result.OdometerStatus)
	}

	// Fuel enrichment from 8ys7-d773
	if result.FuelType != "Benzine" {
		t.Errorf("FuelType = %q, want Benzine", result.FuelType)
	}
	if result.EuroNorm != "EURO 6" {
		t.Errorf("EuroNorm = %q, want EURO 6", result.EuroNorm)
	}
	if result.PowerKW != 72 {
		t.Errorf("PowerKW = %g, want 72", result.PowerKW)
	}
	if result.CO2GPerKm != 116 {
		t.Errorf("CO2GPerKm = %g, want 116", result.CO2GPerKm)
	}
	if result.FuelConsumptionCombinedL100km != 5.0 {
		t.Errorf("FuelConsumptionCombinedL100km = %g, want 5.0", result.FuelConsumptionCombinedL100km)
	}

	// Axles from 3huj-srit
	if result.NumberOfAxles != 2 {
		t.Errorf("NumberOfAxles = %d, want 2", result.NumberOfAxles)
	}

	// APK history from sgfe-77wx
	if len(result.APKHistory) != 1 {
		t.Fatalf("APKHistory len = %d, want 1", len(result.APKHistory))
	}
	if result.APKHistory[0].Result != "pass" {
		t.Errorf("APKHistory[0].Result = %q, want pass", result.APKHistory[0].Result)
	}
	if result.APKHistory[0].Station != "GARAGE A" {
		t.Errorf("APKHistory[0].Station = %q, want GARAGE A", result.APKHistory[0].Station)
	}
	if result.LastInspectionResult != "pass" {
		t.Errorf("LastInspectionResult = %q, want pass", result.LastInspectionResult)
	}
}

func TestNLPlateResolver_OdometerIllogical(t *testing.T) {
	srv := rdwMultiServer(t, map[string][]map[string]string{
		"m9d7-ebf2": {{"kenteken": "XX0001", "merk": "SEAT", "tellerstandoordeel": "Onlogisch"}},
	})
	defer srv.Close()

	r := check.NewNLPlateResolverWithBase(srv.URL)
	result, err := r.Resolve(context.Background(), "XX0001")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.OdometerStatus != "Onlogisch" {
		t.Errorf("OdometerStatus = %q, want Onlogisch", result.OdometerStatus)
	}
}

func TestNLPlateResolver_APKWithDefects(t *testing.T) {
	inspDate := "2024-06-10T09:00:00.000"

	srv := rdwMultiServer(t, map[string][]map[string]string{
		"m9d7-ebf2": {{"kenteken": "XX0002", "merk": "VW"}},
		"sgfe-77wx": {{
			"kenteken":                              "XX0002",
			"meld_datum_door_keuringsinstantie_dt":  inspDate,
			"soort_erkenning_omschrijving":          "GARAGE B",
		}},
		"a34c-vvps": {{
			"kenteken":                              "XX0002",
			"meld_datum_door_keuringsinstantie_dt":  inspDate,
			"gebrek_identificatie":                  "G123",
			"aantal_gebreken_geconstateerd":         "2",
			"soort_erkenning_omschrijving":          "GARAGE B",
		}},
	})
	defer srv.Close()

	r := check.NewNLPlateResolverWithBase(srv.URL)
	result, err := r.Resolve(context.Background(), "XX0002")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.APKHistory) == 0 {
		t.Fatal("expected APK history entries")
	}
	if result.APKHistory[0].Result != "fail" {
		t.Errorf("APKHistory[0].Result = %q, want fail", result.APKHistory[0].Result)
	}
	if len(result.APKHistory[0].Defects) != 1 {
		t.Fatalf("defects len = %d, want 1", len(result.APKHistory[0].Defects))
	}
	if result.APKHistory[0].Defects[0].Code != "G123" {
		t.Errorf("defect code = %q, want G123", result.APKHistory[0].Defects[0].Code)
	}
	if result.APKHistory[0].Defects[0].Count != 2 {
		t.Errorf("defect count = %d, want 2", result.APKHistory[0].Defects[0].Count)
	}
	if result.LastInspectionResult != "fail" {
		t.Errorf("LastInspectionResult = %q, want fail", result.LastInspectionResult)
	}
}

func TestNLPlateResolver_AxlesIgnoredWhenEmptyAsNummer(t *testing.T) {
	// If the axles endpoint echoes back wrong/empty data, NumberOfAxles must stay 0.
	srv := rdwPlateServer([]map[string]string{
		{"kenteken": "XX0003", "merk": "BMW"},
	})
	defer srv.Close()

	r := check.NewNLPlateResolverWithBase(srv.URL)
	result, err := r.Resolve(context.Background(), "XX0003")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.NumberOfAxles != 0 {
		t.Errorf("NumberOfAxles = %d, want 0 when as_nummer is empty", result.NumberOfAxles)
	}
}

// ── DE plate resolver ─────────────────────────────────────────────────────────

func TestDEPlateResolver_KnownPrefix(t *testing.T) {
	reg := check.NewPlateRegistry("http://localhost:0")

	// Plates use letter combinations (XY suffix) that don't match any 2/3-char UZ prefix,
	// so the 1-char UZ is extracted unambiguously after normalization.
	cases := []struct {
		plate    string // normalised (no dash/space)
		contains string // expected substring in District
	}{
		{"BXY1234", "Berlin"},     // B → Berlin (BX not a valid UZ)
		{"MXY1234", "München"},    // M → München (MX not a valid UZ)
		{"HHX1234", "Hamburg"},    // HH → Hamburg
		{"NXY1234", "Nürnberg"},   // N → Nürnberg (NX not a valid UZ)
		{"SXY1234", "Stuttgart"},  // S → Stuttgart (SX not a valid UZ)
		{"ZWI1234", "Zwickau"},    // ZWI → Zwickau (3-char match)
		{"BADC123", "Baden-Baden"},// BAD → Baden-Baden (3-char match)
	}
	for _, tc := range cases {
		result, err := reg.Resolve(context.Background(), tc.plate, "DE")
		if err != nil {
			t.Errorf("DE %q: unexpected error: %v", tc.plate, err)
			continue
		}
		if !strings.Contains(result.District, tc.contains) {
			t.Errorf("DE %q: District = %q, want it to contain %q", tc.plate, result.District, tc.contains)
		}
		if result.Partial != true {
			t.Errorf("DE %q: Partial should be true", tc.plate)
		}
	}
}

func TestDEPlateResolver_UnknownPrefix(t *testing.T) {
	reg := check.NewPlateRegistry("http://localhost:0")
	_, err := reg.Resolve(context.Background(), "XYZABC123", "DE")
	if !errors.Is(err, check.ErrPlateResolutionUnavailable) {
		t.Errorf("want ErrPlateResolutionUnavailable for unknown DE prefix, got %v", err)
	}
}

// ── CH plate resolver ─────────────────────────────────────────────────────────

func TestCHPlateResolver_EAutoindexCantons(t *testing.T) {
	reg := check.NewPlateRegistry("http://localhost:0")
	for _, canton := range []string{"BE", "BL", "BS", "GE", "GR", "SG", "VD"} {
		plate := canton + "123456"
		_, err := reg.Resolve(context.Background(), plate, "CH")
		if !errors.Is(err, check.ErrPlateResolutionUnavailable) {
			t.Errorf("CH/%s: want ErrPlateResolutionUnavailable (eAutoindex), got %v", canton, err)
		}
	}
}

func TestCHPlateResolver_InvalidFormat(t *testing.T) {
	reg := check.NewPlateRegistry("http://localhost:0")
	_, err := reg.Resolve(context.Background(), "12345", "CH")
	// Should error — pure digits, no canton
	if err == nil {
		t.Error("expected error for invalid CH plate (no letters), got nil")
	}
}

func TestCHPlateResolver_SpecialPlates(t *testing.T) {
	reg := check.NewPlateRegistry("http://localhost:0")
	for _, plate := range []string{"CD12345", "CC1234"} {
		_, err := reg.Resolve(context.Background(), plate, "CH")
		if !errors.Is(err, check.ErrPlateResolutionUnavailable) {
			t.Errorf("CH/%s: want ErrPlateResolutionUnavailable for diplomatic plate, got %v", plate, err)
		}
	}
}

// ── FR plate resolver ─────────────────────────────────────────────────────────

// TestFRPlateResolver_InvalidFormat tests that a too-short plate returns an error.
func TestFRPlateResolver_InvalidFormat(t *testing.T) {
	reg := check.NewPlateRegistry("http://localhost:0")
	_, err := reg.Resolve(context.Background(), "AB", "FR")
	if err == nil {
		t.Error("expected error for too-short FR plate")
	}
}

// ── BE plate resolver ─────────────────────────────────────────────────────────

func TestBEPlateResolver_InvalidFormat(t *testing.T) {
	reg := check.NewPlateRegistry("http://localhost:0")
	_, err := reg.Resolve(context.Background(), "X", "BE")
	if err == nil {
		t.Error("expected error for too-short BE plate")
	}
}

// ── ES plate resolver ─────────────────────────────────────────────────────────

func TestESPlateResolver_InvalidFormat(t *testing.T) {
	reg := check.NewPlateRegistry("http://localhost:0")
	_, err := reg.Resolve(context.Background(), "AB", "ES") // too short
	if err == nil {
		t.Error("expected error for too-short ES plate")
	}
}

// esMockServer wires comprobarmatricula.com page + API + DGT distintivo onto
// a single httptest server so tests can assert on real parsing.
func esMockServer(t *testing.T, cmToken string, cmJSON string, dgtBadge string) *httptest.Server {
	t.Helper()
	mux := http.NewServeMux()

	// Plate page: returns HTML with the hidden _g_tk input. Real CM always
	// serves HTTP 404 here, mirror that quirk.
	mux.HandleFunc("/matricula/", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		fmt.Fprintf(w, `<html><body>
<input type="hidden" id="_g_tk" value="%s">
<input type="text" id="_g_hp" name="_website" value="">
</body></html>`, cmToken)
	})

	// JSON API: echoes the fixture back when token matches.
	mux.HandleFunc("/api/vehiculo.php", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("_tk") != cmToken {
			w.WriteHeader(http.StatusForbidden)
			_, _ = fmt.Fprint(w, `{"ok":0,"err":"Forbidden"}`)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, cmJSON)
	})

	// DGT distintivo ambiental page.
	mux.HandleFunc("/dgt/", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		if dgtBadge == "" {
			_, _ = fmt.Fprint(w, "No se ha encontrado ningún resultado")
			return
		}
		_, _ = fmt.Fprintf(w, `<img src="/img/distintivo_%s_sin_fondo.svg">`, dgtBadge)
	})

	return httptest.NewServer(mux)
}

func TestESPlateResolver_FullResolve(t *testing.T) {
	const token = "1776671834.abcdef.0123456789"
	cmJSON := `{"ok":1,"mat":"8000LVY","brand":"Vw","marca_oficial":"VW",
"model":"Tiguan","modelo_completo":"TIGUAN (5N_)","version":"2.0 TDI 4motion | 170 cv",
"fuel":"Diésel","potencia_cv":170,"potencia_kw":125,"cilindrada_cc":"1968 cc",
"carroceria":"SUV","caja":"Manual","codigo_motor":"CFGB","vin":"WVGZZZ5NZAW021819",
"fecha_matriculacion":"02/09/2009","annee_modelo":"2009","etiq":"B",
"itv_date":"20/10/2027","owners":3}`
	srv := esMockServer(t, token, cmJSON, "C")
	defer srv.Close()

	r := check.NewESPlateResolverWithBases(srv.URL, srv.URL+"/dgt/")
	result, err := r.Resolve(context.Background(), "8000LVY")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if result.VIN != "WVGZZZ5NZAW021819" {
		t.Errorf("VIN = %q, want WVGZZZ5NZAW021819", result.VIN)
	}
	if result.Make != "VW" {
		t.Errorf("Make = %q, want VW", result.Make)
	}
	if result.Model != "TIGUAN (5N_)" {
		t.Errorf("Model = %q, want TIGUAN (5N_)", result.Model)
	}
	if result.Variant != "2.0 TDI 4motion | 170 cv" {
		t.Errorf("Variant = %q, want 2.0 TDI 4motion | 170 cv", result.Variant)
	}
	if result.FuelType != "Diésel" {
		t.Errorf("FuelType = %q, want Diésel", result.FuelType)
	}
	if result.PowerKW != 125 {
		t.Errorf("PowerKW = %v, want 125", result.PowerKW)
	}
	if result.DisplacementCC != 1968 {
		t.Errorf("DisplacementCC = %d, want 1968", result.DisplacementCC)
	}
	if result.BodyType != "SUV" {
		t.Errorf("BodyType = %q, want SUV", result.BodyType)
	}
	if result.PowerCV != 170 {
		t.Errorf("PowerCV = %d, want 170", result.PowerCV)
	}
	if result.Transmission != "Manual" {
		t.Errorf("Transmission = %q, want Manual", result.Transmission)
	}
	if result.EngineCode != "CFGB" {
		t.Errorf("EngineCode = %q, want CFGB", result.EngineCode)
	}
	if result.PreviousOwners != 3 {
		t.Errorf("PreviousOwners = %d, want 3", result.PreviousOwners)
	}
	if result.ModelYear != 2009 {
		t.Errorf("ModelYear = %d, want 2009", result.ModelYear)
	}
	// DGT is the canonical badge source — must win over etiq from CM.
	if result.EnvironmentalBadge != "C" {
		t.Errorf("EnvironmentalBadge = %q, want C (from DGT)", result.EnvironmentalBadge)
	}
	if result.FirstRegistration == nil || result.FirstRegistration.Format("2006-01-02") != "2009-09-02" {
		t.Errorf("FirstRegistration = %v, want 2009-09-02", result.FirstRegistration)
	}
	if result.NextInspectionDate == nil || result.NextInspectionDate.Format("2006-01-02") != "2027-10-20" {
		t.Errorf("NextInspectionDate = %v, want 2027-10-20", result.NextInspectionDate)
	}
	if result.Partial {
		t.Error("expected Partial=false when CM returned data")
	}
	if !strings.Contains(result.Source, "comprobarmatricula") || !strings.Contains(result.Source, "dgt") {
		t.Errorf("Source = %q, want both CM and DGT mentioned", result.Source)
	}
}

func TestESPlateResolver_DGTOnlyPartial(t *testing.T) {
	const token = "tok"
	srv := esMockServer(t, token, `{"ok":0}`, "CERO")
	defer srv.Close()

	r := check.NewESPlateResolverWithBases(srv.URL, srv.URL+"/dgt/")
	result, err := r.Resolve(context.Background(), "1234BCJ")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.EnvironmentalBadge != "0" {
		t.Errorf("EnvironmentalBadge = %q, want 0 (CERO)", result.EnvironmentalBadge)
	}
	if result.VIN != "" {
		t.Errorf("VIN should be empty when CM didn't return data, got %q", result.VIN)
	}
	if !result.Partial {
		t.Error("expected Partial=true when only DGT returned data")
	}
}

func TestESPlateResolver_AllSourcesFail(t *testing.T) {
	// Both endpoints return no data.
	const token = "tok"
	srv := esMockServer(t, token, `{"ok":0}`, "")
	defer srv.Close()

	r := check.NewESPlateResolverWithBases(srv.URL, srv.URL+"/dgt/")
	_, err := r.Resolve(context.Background(), "9999AAA")
	if !errors.Is(err, check.ErrPlateNotFound) {
		t.Errorf("want ErrPlateNotFound, got %v", err)
	}
}

// TestESPlateResolver_CacheServesAfterCMRateLimit verifies the persistent
// plate cache: once comprobarmatricula.com succeeds, subsequent lookups
// should be served from cache even when CM later starts rate-limiting.
func TestESPlateResolver_CacheServesAfterCMRateLimit(t *testing.T) {
	const token = "tok-cache"
	const cmSuccessJSON = `{"ok":1,"mat":"8000LVY","marca_oficial":"VW","model":"Tiguan",
"modelo_completo":"TIGUAN (5N_)","version":"2.0 TDI 4motion","fuel":"Diésel",
"potencia_cv":170,"potencia_kw":125,"cilindrada_cc":"1968 cc","carroceria":"SUV",
"caja":"Manual","codigo_motor":"CFGB","vin":"WVGZZZ5NZAW021819",
"fecha_matriculacion":"02/09/2009","annee_modelo":"2009","owners":3}`

	// Serve success on first CM API call, then switch to limit=true.
	var cmCalls int32
	mux := http.NewServeMux()
	mux.HandleFunc("/matricula/", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		fmt.Fprintf(w, `<html><input type="hidden" id="_g_tk" value="%s"></html>`, token)
	})
	mux.HandleFunc("/api/vehiculo.php", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("_tk") != token {
			w.WriteHeader(http.StatusForbidden)
			_, _ = fmt.Fprint(w, `{"ok":0,"err":"Forbidden"}`)
			return
		}
		if atomic.AddInt32(&cmCalls, 1) == 1 {
			w.Header().Set("Content-Type", "application/json")
			_, _ = fmt.Fprint(w, cmSuccessJSON)
			return
		}
		_, _ = fmt.Fprint(w, `{"ok":0,"limit":true,"err":"limit"}`)
	})
	mux.HandleFunc("/dgt/", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = fmt.Fprint(w, `<img src="/img/distintivo_B_sin_fondo.svg">`)
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	cache := newCache(t)
	r := check.NewESPlateResolverWithBases(srv.URL, srv.URL+"/dgt/").WithCache(cache)

	// First call: live fetch, should succeed with full CM data.
	r1, err := r.Resolve(context.Background(), "8000LVY")
	if err != nil {
		t.Fatalf("first resolve: %v", err)
	}
	if r1.VIN != "WVGZZZ5NZAW021819" {
		t.Fatalf("first VIN = %q, want WVGZZZ5NZAW021819", r1.VIN)
	}
	if r1.Partial {
		t.Fatal("first resolve should not be partial")
	}

	// Second call: CM would now rate-limit, but cache should serve.
	r2, err := r.Resolve(context.Background(), "8000LVY")
	if err != nil {
		t.Fatalf("second resolve: %v", err)
	}
	if r2.VIN != "WVGZZZ5NZAW021819" {
		t.Errorf("second VIN = %q, want cached WVGZZZ5NZAW021819", r2.VIN)
	}
	if r2.Make != "VW" || r2.Model != "TIGUAN (5N_)" || r2.PowerKW != 125 {
		t.Errorf("cached fields lost: make=%q model=%q kw=%v", r2.Make, r2.Model, r2.PowerKW)
	}
	if !strings.Contains(r2.Source, "cached") {
		t.Errorf("second Source = %q, want marker \"cached\"", r2.Source)
	}
	// Exactly one CM API call should have happened.
	if got := atomic.LoadInt32(&cmCalls); got != 1 {
		t.Errorf("CM API calls = %d, want 1 (second should be served from cache)", got)
	}
}

// TestESPlateResolver_CachePartialUpgrades checks that a partial (DGT-only)
// cache entry does NOT prevent a later successful CM call from populating
// rich data.
func TestESPlateResolver_CachePartialUpgrades(t *testing.T) {
	const token = "tok-upgrade"
	var cmOK int32 // 0 = limit, 1 = success

	mux := http.NewServeMux()
	mux.HandleFunc("/matricula/", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		fmt.Fprintf(w, `<html><input type="hidden" id="_g_tk" value="%s"></html>`, token)
	})
	mux.HandleFunc("/api/vehiculo.php", func(w http.ResponseWriter, _ *http.Request) {
		if atomic.LoadInt32(&cmOK) == 0 {
			_, _ = fmt.Fprint(w, `{"ok":0,"limit":true}`)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{"ok":1,"mat":"1234BCJ","marca_oficial":"Seat","model":"Ibiza","vin":"VSSZZZ6KZ1R113828"}`)
	})
	mux.HandleFunc("/dgt/", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = fmt.Fprint(w, `<img src="/img/distintivo_B_sin_fondo.svg">`)
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	cache := newCache(t)
	r := check.NewESPlateResolverWithBases(srv.URL, srv.URL+"/dgt/").WithCache(cache)

	// First: CM rate-limits → partial (DGT only) cached.
	r1, err := r.Resolve(context.Background(), "1234BCJ")
	if err != nil {
		t.Fatalf("first resolve: %v", err)
	}
	if !r1.Partial || r1.VIN != "" {
		t.Fatalf("first resolve should be partial with no VIN, got partial=%v vin=%q", r1.Partial, r1.VIN)
	}

	// Flip CM to success; a second live lookup should upgrade the cache.
	atomic.StoreInt32(&cmOK, 1)

	r2, err := r.Resolve(context.Background(), "1234BCJ")
	if err != nil {
		t.Fatalf("second resolve: %v", err)
	}
	if r2.VIN != "VSSZZZ6KZ1R113828" {
		t.Errorf("second VIN = %q, want VSSZZZ6KZ1R113828 (upgrade)", r2.VIN)
	}
	if r2.Partial {
		t.Error("second resolve should be non-partial after CM success")
	}
}

// TestESPlateResolver_Live hits the real production endpoints. It is skipped
// unless CARDEX_LIVE_ES=1 to keep the default test run hermetic.
func TestESPlateResolver_Live(t *testing.T) {
	if os.Getenv("CARDEX_LIVE_ES") != "1" {
		t.Skip("live ES test skipped; set CARDEX_LIVE_ES=1 to enable")
	}
	reg := check.NewPlateRegistry("http://localhost:0")
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	result, err := reg.Resolve(ctx, "8000LVY", "ES")
	if err != nil {
		t.Fatalf("live resolve failed: %v", err)
	}
	// DGT must always work — it has no rate limit.
	if result.EnvironmentalBadge == "" {
		t.Error("live result missing DGT environmental badge")
	}
	t.Logf("live result: VIN=%s make=%s model=%s variant=%s fuel=%s kW=%v cc=%d body=%s badge=%s firstReg=%v itv=%v partial=%v source=%s",
		result.VIN, result.Make, result.Model, result.Variant, result.FuelType,
		result.PowerKW, result.DisplacementCC, result.BodyType, result.EnvironmentalBadge,
		result.FirstRegistration, result.NextInspectionDate, result.Partial, result.Source)
	// Rate-limited CM response → VIN absent is legitimate. Do not fail.
	if result.VIN == "" {
		t.Log("VIN absent — likely CM rate-limit; DGT-only partial is expected fallback")
	}
}

// ── Handler plate endpoint ────────────────────────────────────────────────────

// mockPlateResolver implements PlateResolver for handler tests.
type mockPlateResolver struct {
	result *check.PlateResult
	err    error
}

func (m *mockPlateResolver) Resolve(_ context.Context, _ string) (*check.PlateResult, error) {
	return m.result, m.err
}

func newTestEngineForPlate(t *testing.T) *check.Engine {
	t.Helper()
	nhtsa := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"Count":   1,
			"Results": []map[string]string{{"Make": "BMW", "Model": "3 Series"}},
		})
	}))
	t.Cleanup(nhtsa.Close)

	rdw := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprint(w, "[]")
	}))
	t.Cleanup(rdw.Close)

	cache := newCache(t)
	decoder := check.NewVINDecoderWithBase(nhtsa.URL)
	providers := []check.RegistryProvider{check.NewNLProviderWithBase(rdw.URL)}
	return check.NewEngine(cache, decoder, providers)
}

func TestHandlerPlateRoute_OK_WithVIN(t *testing.T) {
	engine := newTestEngineForPlate(t)
	cache := newCache(t)
	reg := check.NewPlateRegistryFromMap(map[string]check.PlateResolver{
		"NL": &mockPlateResolver{result: &check.PlateResult{VIN: validVIN, Make: "BMW", Country: "NL"}},
	})
	h := check.NewHandlerWithValidatorAndPlates(engine, cache, nil, reg)

	mux := http.NewServeMux()
	h.Register(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/check/plate/NL/GV123B", nil)
	rr := httptest.NewRecorder()
	mux.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("want 200, got %d — body: %s", rr.Code, rr.Body.String())
	}
	if rr.Header().Get("X-Plate-Resolved-VIN") != validVIN {
		t.Errorf("X-Plate-Resolved-VIN header: got %q, want %q",
			rr.Header().Get("X-Plate-Resolved-VIN"), validVIN)
	}

	var report map[string]interface{}
	if err := json.NewDecoder(rr.Body).Decode(&report); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if report["vin"] != validVIN {
		t.Errorf("response vin = %v, want %q", report["vin"], validVIN)
	}
}

func TestHandlerPlateRoute_OK_PartialNoVIN(t *testing.T) {
	engine := newTestEngineForPlate(t)
	cache := newCache(t)

	now := time.Now().UTC()
	reg := check.NewPlateRegistryFromMap(map[string]check.PlateResolver{
		"ES": &mockPlateResolver{result: &check.PlateResult{
			Plate:              "1234BCJ",
			Make:               "SEAT",
			EnvironmentalBadge: "C",
			Country:            "ES",
			FirstRegistration:  &now,
			Partial:            true,
		}},
	})
	h := check.NewHandlerWithValidatorAndPlates(engine, cache, nil, reg)

	mux := http.NewServeMux()
	h.Register(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/check/plate/ES/1234BCJ", nil)
	rr := httptest.NewRecorder()
	mux.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("want 200, got %d — body: %s", rr.Code, rr.Body.String())
	}
	// No VIN resolved → X-Plate-Resolved-VIN header should be absent/empty.
	if vin := rr.Header().Get("X-Plate-Resolved-VIN"); vin != "" {
		t.Errorf("expected no X-Plate-Resolved-VIN header for partial result, got %q", vin)
	}

	var report map[string]interface{}
	if err := json.NewDecoder(rr.Body).Decode(&report); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	// plateInfo should be present with make = "SEAT"
	plateInfo, ok := report["plateInfo"].(map[string]interface{})
	if !ok {
		t.Fatalf("plateInfo not present in partial response: %v", report)
	}
	if plateInfo["make"] != "SEAT" {
		t.Errorf("plateInfo.make = %v, want SEAT", plateInfo["make"])
	}
}

func TestHandlerPlateRoute_PlateNotFound(t *testing.T) {
	engine := newTestEngineForPlate(t)
	cache := newCache(t)
	reg := check.NewPlateRegistryFromMap(map[string]check.PlateResolver{
		"NL": &mockPlateResolver{err: fmt.Errorf("%w: plate NOTFOUND", check.ErrPlateNotFound)},
	})
	h := check.NewHandlerWithValidatorAndPlates(engine, cache, nil, reg)

	mux := http.NewServeMux()
	h.Register(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/check/plate/NL/NOTFOUND", nil)
	rr := httptest.NewRecorder()
	mux.ServeHTTP(rr, req)

	if rr.Code != http.StatusNotFound {
		t.Errorf("want 404, got %d", rr.Code)
	}
}

func TestHandlerPlateRoute_CountryUnavailable(t *testing.T) {
	engine := newTestEngineForPlate(t)
	cache := newCache(t)
	reg := check.NewPlateRegistryFromMap(map[string]check.PlateResolver{
		"FR": &mockPlateResolver{err: check.ErrPlateResolutionUnavailable},
	})
	h := check.NewHandlerWithValidatorAndPlates(engine, cache, nil, reg)

	mux := http.NewServeMux()
	h.Register(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/check/plate/FR/AB123CD", nil)
	rr := httptest.NewRecorder()
	mux.ServeHTTP(rr, req)

	if rr.Code != http.StatusServiceUnavailable {
		t.Errorf("want 503, got %d", rr.Code)
	}
}

func TestHandlerPlateRoute_UnknownCountryReturns503(t *testing.T) {
	engine := newTestEngineForPlate(t)
	cache := newCache(t)
	reg := check.NewPlateRegistry("http://localhost:0")
	h := check.NewHandlerWithValidatorAndPlates(engine, cache, nil, reg)

	mux := http.NewServeMux()
	h.Register(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/check/plate/IT/AB123CD", nil)
	rr := httptest.NewRecorder()
	mux.ServeHTTP(rr, req)

	if rr.Code != http.StatusServiceUnavailable {
		t.Errorf("want 503 for unknown country, got %d", rr.Code)
	}
}

func TestHandlerPlateRoute_RateLimit(t *testing.T) {
	engine := newTestEngineForPlate(t)
	cache := newCache(t)
	reg := check.NewPlateRegistryFromMap(map[string]check.PlateResolver{
		"NL": &mockPlateResolver{result: &check.PlateResult{VIN: validVIN}},
	})
	rl := check.NewRateLimiter(0, time.Hour) // zero capacity → always deny
	h := check.NewHandlerWithLimitAndValidatorAndPlates(engine, cache, rl, nil, reg)

	mux := http.NewServeMux()
	h.Register(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/check/plate/NL/GV123B", nil)
	rr := httptest.NewRecorder()
	mux.ServeHTTP(rr, req)

	if rr.Code != http.StatusTooManyRequests {
		t.Errorf("want 429, got %d", rr.Code)
	}
}
