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
