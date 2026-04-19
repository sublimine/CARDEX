package check_test

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
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

func TestFRPlateResolver_UnavailableWithoutHistoVec(t *testing.T) {
	// HistoVec returns 401 → resolver returns ErrPlateResolutionUnavailable.
	histoSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
	}))
	defer histoSrv.Close()
	// We can't easily inject the HistoVec URL, so just verify a real FR plate returns
	// ErrPlateResolutionUnavailable when the server is unreachable.
	reg := check.NewPlateRegistry("http://localhost:0")
	_, err := reg.Resolve(context.Background(), "AB123CD", "FR")
	if !errors.Is(err, check.ErrPlateResolutionUnavailable) {
		t.Errorf("FR: want ErrPlateResolutionUnavailable, got %v", err)
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
