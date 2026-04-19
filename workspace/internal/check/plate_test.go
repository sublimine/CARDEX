package check_test

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
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
	}
	for _, tc := range cases {
		got := check.NormalizePlate(tc.in)
		if got != tc.want {
			t.Errorf("NormalizePlate(%q) = %q, want %q", tc.in, got, tc.want)
		}
	}
}

// ── NLPlateResolver ───────────────────────────────────────────────────────────

func rdwPlateServer(rows []map[string]string) *httptest.Server {
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(rows)
	}))
}

func TestNLPlateResolver_OK(t *testing.T) {
	srv := rdwPlateServer([]map[string]string{
		{"kenteken": "GV123B", "voertuigidentificatienummer": validVIN},
	})
	defer srv.Close()

	r := check.NewNLPlateResolverWithBase(srv.URL)
	got, err := r.Resolve(context.Background(), "GV123B", "NL")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got != validVIN {
		t.Errorf("got VIN %q, want %q", got, validVIN)
	}
}

func TestNLPlateResolver_NormalizesBeforeQuery(t *testing.T) {
	var gotPath string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.RawQuery
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode([]map[string]string{
			{"kenteken": "GV123B", "voertuigidentificatienummer": validVIN},
		})
	}))
	defer srv.Close()

	// PlateRegistry normalizes before calling resolver
	reg := check.NewPlateRegistry(srv.URL)
	_, err := reg.Resolve(context.Background(), "gv-123-b", "NL")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if gotPath != "kenteken=GV123B" {
		t.Errorf("expected query kenteken=GV123B, got %q", gotPath)
	}
}

func TestNLPlateResolver_NotFound(t *testing.T) {
	srv := rdwPlateServer(nil) // empty array
	defer srv.Close()

	r := check.NewNLPlateResolverWithBase(srv.URL)
	_, err := r.Resolve(context.Background(), "NOTFOUND", "NL")
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !errors.Is(err, check.ErrPlateNotFound) {
		t.Errorf("want ErrPlateNotFound, got %v", err)
	}
}

func TestNLPlateResolver_EmptyVINField(t *testing.T) {
	srv := rdwPlateServer([]map[string]string{
		{"kenteken": "XX0000", "voertuigidentificatienummer": ""},
	})
	defer srv.Close()

	r := check.NewNLPlateResolverWithBase(srv.URL)
	_, err := r.Resolve(context.Background(), "XX0000", "NL")
	if !errors.Is(err, check.ErrPlateNotFound) {
		t.Errorf("want ErrPlateNotFound for empty VIN field, got %v", err)
	}
}

func TestNLPlateResolver_ServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	r := check.NewNLPlateResolverWithBase(srv.URL)
	_, err := r.Resolve(context.Background(), "XX1234", "NL")
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
	got, err := r.Resolve(context.Background(), "XX1234", "NL")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got != "WBA3C5C5XDF773941" {
		t.Errorf("VIN not uppercased: got %q", got)
	}
}

// ── PlateRegistry ─────────────────────────────────────────────────────────────

func TestPlateRegistry_NL_Live(t *testing.T) {
	srv := rdwPlateServer([]map[string]string{
		{"kenteken": "GV123B", "voertuigidentificatienummer": validVIN},
	})
	defer srv.Close()

	reg := check.NewPlateRegistry(srv.URL)
	vin, err := reg.Resolve(context.Background(), "GV-123-B", "NL")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if vin != validVIN {
		t.Errorf("got %q, want %q", vin, validVIN)
	}
}

func TestPlateRegistry_ScaffoldCountriesUnavailable(t *testing.T) {
	reg := check.NewPlateRegistry("http://localhost:0") // URL unused for scaffolds
	for _, country := range []string{"FR", "BE", "ES", "DE", "CH"} {
		_, err := reg.Resolve(context.Background(), "AB1234", country)
		if !errors.Is(err, check.ErrPlateResolutionUnavailable) {
			t.Errorf("%s: want ErrPlateResolutionUnavailable, got %v", country, err)
		}
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
	// Lowercase country code should still resolve
	_, err := reg.Resolve(context.Background(), "XX1234", "nl")
	if err != nil {
		t.Errorf("lowercase country code should work: %v", err)
	}
}

// ── Handler plate endpoint ────────────────────────────────────────────────────

// mockPlateResolver implements PlateResolver for handler tests.
type mockPlateResolver struct {
	vin string
	err error
}

func (m *mockPlateResolver) Resolve(_ context.Context, _, _ string) (string, error) {
	return m.vin, m.err
}

func newTestEngineForPlate(t *testing.T) *check.Engine {
	t.Helper()
	// Minimal NHTSA mock — returns empty results so enrichment is skipped.
	nhtsa := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"Count":   1,
			"Results": []map[string]string{{"Make": "BMW", "Model": "3 Series"}},
		})
	}))
	t.Cleanup(nhtsa.Close)

	// Minimal RDW mock — returns empty for all dataset queries.
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

func TestHandlerPlateRoute_OK(t *testing.T) {
	engine := newTestEngineForPlate(t)
	cache := newCache(t)
	reg := check.NewPlateRegistryFromMap(map[string]check.PlateResolver{
		"NL": &mockPlateResolver{vin: validVIN},
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
	// Registry has no IT entry — Resolve returns ErrPlateResolutionUnavailable
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
		"NL": &mockPlateResolver{vin: validVIN},
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
