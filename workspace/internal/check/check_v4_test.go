package check_test

// Track C v4 — additional functional correctness verifications.
// All tests here are NEW beyond check_test.go baseline.
// TestHandler_RateLimitRetryAfterHeader is the TDD failing test for the
// Retry-After bug — written first, fixed in ratelimit.go + handler.go.

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"cardex.eu/workspace/internal/check"
)

// ── VIN year-table tests ──────────────────────────────────────────────────────

// TestDecodeVIN_YearCodes verifies every year code in the current-cycle
// table (2010–2030 letters, 2001–2009 digits). Spot-checks J/K/L/M/N.
func TestDecodeVIN_YearCodes(t *testing.T) {
	// DecodeVIN does not re-validate; any 17-char string is accepted.
	// Base = WBA3C5C5X  (indices 0–8, last char is a dummy check digit)
	// Index 9 = year code, indices 10–16 = fixed suffix.
	base   := "WBA3C5C5X" // 9 chars (0-8)
	suffix := "F773941"   // 7 chars (10-16)
	tests := []struct {
		code byte
		want int
	}{
		{'J', 2018},
		{'K', 2019},
		{'L', 2020},
		{'M', 2021},
		{'N', 2022},
		{'D', 2013}, // sanity-check against existing TestDecodeVIN_Year2013
	}
	for _, tc := range tests {
		vin := base + string(tc.code) + suffix
		if len(vin) != 17 {
			t.Fatalf("fixture VIN length: want 17, got %d", len(vin))
		}
		info := check.DecodeVIN(vin)
		if info.ModelYear != tc.want {
			t.Errorf("year code %c: want %d, got %d", tc.code, tc.want, info.ModelYear)
		}
	}
}

// ── WMI table tests ───────────────────────────────────────────────────────────

func TestDecodeVIN_WMI_Renault(t *testing.T) {
	// VF1 → Renault, France
	vin := "VF13C5C5XDF773941"
	info := check.DecodeVIN(vin)
	if info.WMI != "VF1" {
		t.Errorf("WMI: want VF1, got %s", info.WMI)
	}
	if !strings.Contains(info.Manufacturer, "Renault") {
		t.Errorf("Manufacturer: want Renault, got %q", info.Manufacturer)
	}
	if info.Country != "FR" {
		t.Errorf("Country: want FR, got %s", info.Country)
	}
}

func TestDecodeVIN_WMI_VW(t *testing.T) {
	// WVW → Volkswagen, Germany
	vin := "WVW3C5C5XDF773941"
	info := check.DecodeVIN(vin)
	if !strings.Contains(info.Manufacturer, "Volkswagen") {
		t.Errorf("Manufacturer: want Volkswagen, got %q", info.Manufacturer)
	}
	if info.Country != "DE" {
		t.Errorf("Country: want DE, got %s", info.Country)
	}
}

func TestDecodeVIN_UnknownWMI_ReturnsUnknown(t *testing.T) {
	// ZZZ is not in the WMI table; lookupWMI must return "Unknown" and "".
	vin := "ZZZ3C5C5XDF773941"
	info := check.DecodeVIN(vin)
	if info.Manufacturer != "Unknown" {
		t.Errorf("unknown WMI: want manufacturer=Unknown, got %q", info.Manufacturer)
	}
	if info.Country != "" {
		t.Errorf("unknown WMI: want empty country, got %q", info.Country)
	}
}

// ── NL provider additional tests ──────────────────────────────────────────────

// newStolenRDWServer returns a mock RDW server where the vehicle IS in the
// stolen dataset (8ys7-d773 returns a non-empty array).
func newStolenRDWServer(t *testing.T) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		path := r.URL.Path
		switch {
		case strings.Contains(path, "m9d7-ebf2"):
			_ = json.NewEncoder(w).Encode(rdwFixtureVehicle)
		case strings.Contains(path, "sgfe-77wx"):
			_ = json.NewEncoder(w).Encode(rdwFixtureAPK)
		case strings.Contains(path, "8ys7-d773"):
			// Vehicle IS reported stolen — return non-empty list.
			_ = json.NewEncoder(w).Encode([]map[string]string{{"kenteken": "AB-123-C"}})
		default:
			http.NotFound(w, r)
		}
	}))
}

func TestNLProvider_StolenFlagTrue(t *testing.T) {
	srv := newStolenRDWServer(t)
	defer srv.Close()

	p := check.NewNLProviderWithBase(srv.URL + "/resource")
	data, err := p.FetchHistory(ctx(), validVIN)
	if err != nil {
		t.Fatalf("FetchHistory: %v", err)
	}
	if !data.StolenFlag {
		t.Error("want StolenFlag=true when vehicle appears in stolen registry")
	}
}

func TestNLProvider_ContextCancelled_ReturnsError(t *testing.T) {
	// Server that sleeps long enough for the context to expire first.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(300 * time.Millisecond)
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode([]map[string]string{})
	}))
	defer srv.Close()

	reqCtx, cancel := context.WithTimeout(context.Background(), 30*time.Millisecond)
	defer cancel()

	p := check.NewNLProviderWithBase(srv.URL + "/resource")
	_, err := p.FetchHistory(reqCtx, validVIN)
	if err == nil {
		t.Error("want error when context deadline exceeded")
	}
}

// ── Scaffold provider Country() tests ────────────────────────────────────────

func TestBEProvider_Country(t *testing.T) {
	if got := check.NewBEProvider().Country(); got != "BE" {
		t.Errorf("BEProvider.Country: want BE, got %s", got)
	}
}

func TestCHProvider_Country(t *testing.T) {
	if got := check.NewCHProvider().Country(); got != "CH" {
		t.Errorf("CHProvider.Country: want CH, got %s", got)
	}
}

func TestESProvider_Country(t *testing.T) {
	if got := check.NewESProvider().Country(); got != "ES" {
		t.Errorf("ESProvider.Country: want ES, got %s", got)
	}
}

func TestDEProvider_Country(t *testing.T) {
	if got := check.NewDEProvider().Country(); got != "DE" {
		t.Errorf("DEProvider.Country: want DE, got %s", got)
	}
}

func TestScaffoldProviders_SupportsVIN_ReturnsFalse(t *testing.T) {
	// All scaffold providers declare SupportsVIN=false because they require
	// a license plate, not a VIN, for lookup.
	providers := []check.RegistryProvider{
		check.NewFRProvider(),
		check.NewBEProvider(),
		check.NewCHProvider(),
		check.NewESProvider(),
		check.NewDEProvider(),
	}
	for _, p := range providers {
		if p.SupportsVIN(validVIN) {
			t.Errorf("%s: SupportsVIN should return false for scaffold providers", p.Country())
		}
	}
}

// ── Engine aggregator tests ───────────────────────────────────────────────────

func TestEngine_PartialFailure_OtherProvidersSucceed(t *testing.T) {
	// One provider errors; the other succeeds. Engine must return a report
	// with the successful provider's data and a StatusError DataSource entry.
	nlData := &check.RegistryData{
		Registrations: []check.Registration{{
			Date:    time.Date(2020, 1, 1, 0, 0, 0, 0, time.UTC),
			Country: "NL",
			Type:    check.EventFirstRegistration,
		}},
	}
	eng, _ := newTestEngine(t,
		&stubProvider{country: "NL", data: nlData},
		&stubProvider{country: "DE", err: fmt.Errorf("DE registry timeout")},
	)
	report, err := eng.GenerateReport(ctx(), validVIN)
	if err != nil {
		t.Fatalf("GenerateReport must succeed even when one provider errors: %v", err)
	}
	if len(report.Countries) == 0 {
		t.Error("want CountryReport from the successful NL provider")
	}
	if len(report.DataSources) != 2 {
		t.Errorf("want 2 DataSources, got %d", len(report.DataSources))
	}
}

func TestEngine_DataSources_CorrectStatus(t *testing.T) {
	// Three providers: success / unavailable / transient-error.
	eng, _ := newTestEngine(t,
		&stubProvider{country: "NL", data: &check.RegistryData{}},
		&stubProvider{country: "DE", err: check.ErrProviderUnavailable},
		&stubProvider{country: "FR", err: fmt.Errorf("network timeout")},
	)
	report, err := eng.GenerateReport(ctx(), validVIN)
	if err != nil {
		t.Fatalf("GenerateReport: %v", err)
	}

	status := map[string]check.DataSourceStatus{}
	for _, ds := range report.DataSources {
		status[ds.Country] = ds.Status
	}
	if status["NL"] != check.StatusSuccess {
		t.Errorf("NL: want %s, got %s", check.StatusSuccess, status["NL"])
	}
	if status["DE"] != check.StatusUnavailable {
		t.Errorf("DE: want %s, got %s", check.StatusUnavailable, status["DE"])
	}
	if status["FR"] != check.StatusError {
		t.Errorf("FR: want %s, got %s", check.StatusError, status["FR"])
	}
}

func TestEngine_MileageSortedChronologically(t *testing.T) {
	// Provider 1 has a LATER mileage record; provider 2 has an EARLIER one.
	// After aggregation, MileageHistory must be sorted oldest-first.
	t1 := time.Date(2021, 1, 1, 0, 0, 0, 0, time.UTC) // earlier
	t2 := time.Date(2022, 6, 1, 0, 0, 0, 0, time.UTC) // later

	eng, _ := newTestEngine(t,
		&stubProvider{country: "NL", data: &check.RegistryData{
			MileageRecords: []check.MileageRecord{{Date: t2, Mileage: 80_000, Source: "APK", Country: "NL"}},
		}},
		&stubProvider{country: "DE", data: &check.RegistryData{
			MileageRecords: []check.MileageRecord{{Date: t1, Mileage: 50_000, Source: "TUV", Country: "DE"}},
		}},
	)
	report, err := eng.GenerateReport(ctx(), validVIN)
	if err != nil {
		t.Fatalf("GenerateReport: %v", err)
	}
	if len(report.MileageHistory) != 2 {
		t.Fatalf("want 2 mileage records, got %d", len(report.MileageHistory))
	}
	if !report.MileageHistory[0].Date.Equal(t1) {
		t.Errorf("first record: want %v (earliest), got %v", t1, report.MileageHistory[0].Date)
	}
	if !report.MileageHistory[1].Date.Equal(t2) {
		t.Errorf("second record: want %v (latest), got %v", t2, report.MileageHistory[1].Date)
	}
}

func TestEngine_MileageRollbackAlert(t *testing.T) {
	t1 := time.Date(2020, 1, 1, 0, 0, 0, 0, time.UTC)
	t2 := time.Date(2021, 1, 1, 0, 0, 0, 0, time.UTC)
	data := &check.RegistryData{
		MileageRecords: []check.MileageRecord{
			{Date: t1, Mileage: 80_000, Source: "APK", Country: "NL"},
			{Date: t2, Mileage: 40_000, Source: "APK", Country: "NL"}, // rollback
		},
	}
	eng, _ := newTestEngine(t, &stubProvider{country: "NL", data: data})
	report, err := eng.GenerateReport(ctx(), validVIN)
	if err != nil {
		t.Fatalf("GenerateReport: %v", err)
	}
	for _, a := range report.Alerts {
		if a.Type == check.AlertMileageRollback {
			return // found — test passes
		}
	}
	t.Error("want AlertMileageRollback in report.Alerts for rollback data")
}

func TestEngine_MileageGapAlert(t *testing.T) {
	t1 := time.Date(2020, 1, 1, 0, 0, 0, 0, time.UTC)
	t2 := time.Date(2021, 1, 1, 0, 0, 0, 0, time.UTC)
	data := &check.RegistryData{
		MileageRecords: []check.MileageRecord{
			{Date: t1, Mileage: 10_000, Source: "APK", Country: "NL"},
			{Date: t2, Mileage: 90_000, Source: "APK", Country: "NL"}, // 80k/yr > 50k threshold
		},
	}
	eng, _ := newTestEngine(t, &stubProvider{country: "NL", data: data})
	report, err := eng.GenerateReport(ctx(), validVIN)
	if err != nil {
		t.Fatalf("GenerateReport: %v", err)
	}
	for _, a := range report.Alerts {
		if a.Type == check.AlertMileageGap {
			return // found
		}
	}
	t.Error("want AlertMileageGap in report.Alerts for high-annual-km data")
}

// ── Cache RecordRequest tests ─────────────────────────────────────────────────

func TestCache_RecordRequest_InsertsRow(t *testing.T) {
	db := openDB(t)
	c := check.NewCache(db)

	c.RecordRequest(ctx(), validVIN, "1.2.3.4", "tenant-1", false)

	var n int
	if err := db.QueryRow(`SELECT COUNT(*) FROM check_requests WHERE vin=?`, validVIN).Scan(&n); err != nil {
		t.Fatalf("query: %v", err)
	}
	if n != 1 {
		t.Errorf("want 1 row in check_requests, got %d", n)
	}
}

func TestCache_RecordRequest_CacheHitTrue(t *testing.T) {
	db := openDB(t)
	c := check.NewCache(db)

	c.RecordRequest(ctx(), validVIN, "1.2.3.4", "tenant-1", true)

	var hit bool
	if err := db.QueryRow(`SELECT cache_hit FROM check_requests WHERE vin=?`, validVIN).Scan(&hit); err != nil {
		t.Fatalf("query: %v", err)
	}
	if !hit {
		t.Error("want cache_hit=true in check_requests")
	}
}

func TestCache_RecordRequest_CacheHitFalse(t *testing.T) {
	db := openDB(t)
	c := check.NewCache(db)

	c.RecordRequest(ctx(), validVIN, "1.2.3.4", "tenant-1", false)

	var hit bool
	if err := db.QueryRow(`SELECT cache_hit FROM check_requests WHERE vin=?`, validVIN).Scan(&hit); err != nil {
		t.Fatalf("query: %v", err)
	}
	if hit {
		t.Error("want cache_hit=false in check_requests")
	}
}

// ── Rate limiter correctness tests ───────────────────────────────────────────

func TestRateLimiter_TenPassEleventhBlocked(t *testing.T) {
	rl := check.NewRateLimiter(10, time.Hour)
	ip := "192.168.55.1"
	for i := 0; i < 10; i++ {
		if !rl.Allow(ip) {
			t.Errorf("request %d of 10 should be allowed", i+1)
		}
	}
	if rl.Allow(ip) {
		t.Error("11th request must be blocked (limit=10)")
	}
}

// ── Handler endpoint tests ────────────────────────────────────────────────────

func TestHandler_Summary_ReturnsSubset(t *testing.T) {
	// /summary must return SummaryReport (vin, alerts, mileage_consistency,
	// data_sources) but NOT the full Countries / Recalls / MileageHistory fields.
	data := &check.RegistryData{
		Registrations: []check.Registration{{
			Date: time.Date(2020, 1, 1, 0, 0, 0, 0, time.UTC), Country: "NL",
			Type: check.EventFirstRegistration,
		}},
	}
	eng, c := newTestEngine(t, &stubProvider{country: "NL", data: data})
	h := check.NewHandler(eng, c)
	mux := http.NewServeMux()
	h.Register(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/check/"+validVIN+"/summary", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d: %s", w.Code, w.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	// Required fields.
	for _, f := range []string{"vin", "generated_at", "data_sources"} {
		if body[f] == nil {
			t.Errorf("summary missing required field %q", f)
		}
	}
	// Prohibited fields (full report only).
	for _, f := range []string{"countries", "recalls", "mileage_history"} {
		if _, present := body[f]; present {
			t.Errorf("summary must not include field %q", f)
		}
	}
}

func TestHandler_AuthenticatedBypassesRateLimit(t *testing.T) {
	// limit=1: the first unauthenticated request uses the only slot;
	// the second unauthenticated request is blocked (429).
	// An authenticated request with a valid token must bypass the limiter
	// entirely and succeed regardless of the per-IP counter.
	eng, c := newTestEngine(t, &stubProvider{country: "NL", data: &check.RegistryData{}})
	rl := check.NewRateLimiter(1, time.Hour)
	const validToken = "test-valid-token"
	h := check.NewHandlerWithLimitAndValidator(eng, c, rl, func(tok string) bool {
		return tok == validToken
	})
	mux := http.NewServeMux()
	h.Register(mux)

	ip := "77.88.99.11"

	// First unauthenticated request: uses the single allowed slot.
	r1 := httptest.NewRequest(http.MethodGet, "/api/v1/check/"+validVIN, nil)
	r1.Header.Set("X-Forwarded-For", ip)
	w1 := httptest.NewRecorder()
	mux.ServeHTTP(w1, r1)
	if w1.Code != http.StatusOK {
		t.Fatalf("first request must succeed, got %d", w1.Code)
	}

	// Second unauthenticated request: rate limit exhausted → 429.
	r2 := httptest.NewRequest(http.MethodGet, "/api/v1/check/"+validVIN, nil)
	r2.Header.Set("X-Forwarded-For", ip)
	w2 := httptest.NewRecorder()
	mux.ServeHTTP(w2, r2)
	if w2.Code != http.StatusTooManyRequests {
		t.Errorf("second unauthenticated request: want 429, got %d", w2.Code)
	}

	// Authenticated request with valid token: bypass — must succeed.
	r3 := httptest.NewRequest(http.MethodGet, "/api/v1/check/"+validVIN, nil)
	r3.Header.Set("X-Forwarded-For", ip)
	r3.Header.Set("Authorization", "Bearer "+validToken)
	w3 := httptest.NewRecorder()
	mux.ServeHTTP(w3, r3)
	if w3.Code != http.StatusOK {
		t.Errorf("authenticated request must bypass rate limit, got %d: %s", w3.Code, w3.Body.String())
	}
}

// TestHandler_RateLimitRetryAfterHeader is the TDD failing test for the
// Retry-After header bug.  Written FIRST; handler.go must be fixed to pass it.
func TestHandler_RateLimitRetryAfterHeader(t *testing.T) {
	eng, c := newTestEngine(t, &stubProvider{country: "NL", data: &check.RegistryData{}})
	rl := check.NewRateLimiter(1, time.Hour)
	h := check.NewHandlerWithLimit(eng, c, rl)
	mux := http.NewServeMux()
	h.Register(mux)

	ip := "55.66.77.88"

	// Use up the single allowed slot.
	r1 := httptest.NewRequest(http.MethodGet, "/api/v1/check/"+validVIN, nil)
	r1.Header.Set("X-Forwarded-For", ip)
	httptest.NewRecorder() // discard
	w1 := httptest.NewRecorder()
	mux.ServeHTTP(w1, r1)

	// Second request triggers 429.
	r2 := httptest.NewRequest(http.MethodGet, "/api/v1/check/"+validVIN, nil)
	r2.Header.Set("X-Forwarded-For", ip)
	w2 := httptest.NewRecorder()
	mux.ServeHTTP(w2, r2)

	if w2.Code != http.StatusTooManyRequests {
		t.Fatalf("want 429, got %d", w2.Code)
	}
	if w2.Header().Get("Retry-After") == "" {
		t.Error("BUG: 429 response must include Retry-After header (RFC 6585 §4)")
	}
}
