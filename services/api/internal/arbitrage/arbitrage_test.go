package arbitrage

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"log/slog"

	"cardex.eu/api/internal/store"
)

// fakeStore is an in-memory Store for testing handlers/services without PostgreSQL.
type fakeStore struct {
	stats    []store.CountryStats
	listings map[string][]store.Listing
	err      error
}

func (f *fakeStore) MarketStats(_ context.Context, _ store.Filter) ([]store.CountryStats, error) {
	return f.stats, f.err
}

func (f *fakeStore) CheapestListings(_ context.Context, _ store.Filter, country string, _ int) ([]store.Listing, error) {
	return f.listings[country], f.err
}

func (f *fakeStore) Ping(_ context.Context) error { return f.err }

func fixedNow() time.Time { return time.Date(2026, 6, 5, 0, 0, 0, 0, time.UTC) }

func newFakeStore() *fakeStore {
	return &fakeStore{
		stats: []store.CountryStats{
			{Country: "DE", Count: 50, P50: 20000, P25: 18500, P10: 17000},
			{Country: "ES", Count: 40, P50: 25000, P25: 23000, P10: 21000},
		},
		listings: map[string][]store.Listing{
			"DE": {{
				ID: "v1", Make: "BMW", Model: "3 Series", Year: 2020, MileageKm: 60000,
				FuelType: "Petrol", CO2gkm: 130, PriceEUR: 18000, SourceCountry: "DE",
				SourceURL: "https://dealer.de/v1",
			}},
			"ES": {},
		},
	}
}

func TestFindDiscoversCrossBorderOpportunity(t *testing.T) {
	svc := New(newFakeStore())
	svc.now = fixedNow

	resp, err := svc.Find(context.Background(), store.Filter{Make: "BMW", Model: "3 Series"}, nil, Options{})
	if err != nil {
		t.Fatalf("Find: %v", err)
	}
	if len(resp.Opportunities) != 1 {
		t.Fatalf("expected 1 opportunity, got %d", len(resp.Opportunities))
	}
	op := resp.Opportunities[0]
	if op.BuyCountry != "DE" || op.SellCountry != "ES" {
		t.Errorf("got %s→%s, want DE→ES", op.BuyCountry, op.SellCountry)
	}
	// landed cost = 18000 + transport 1500 + VAT 0 + IEDMT 4.75%*18000=855 + admin 100 = 20455
	// net margin = sell P50 25000 - 20455 = 4545
	if op.NetMarginEUR != 4545.00 {
		t.Errorf("net margin = %.2f, want 4545.00 (landed=%.2f)", op.NetMarginEUR, op.LandedCost.TotalLandedCostEUR)
	}
	if op.Listing.SourceURL != "https://dealer.de/v1" {
		t.Errorf("missing actionable listing URL, got %q", op.Listing.SourceURL)
	}
}

func TestFindRespectsMinMargin(t *testing.T) {
	svc := New(newFakeStore())
	svc.now = fixedNow
	// 30% min margin should exclude the ~22% opportunity.
	resp, err := svc.Find(context.Background(), store.Filter{Make: "BMW", Model: "3 Series"}, nil, Options{MinMarginPct: 30})
	if err != nil {
		t.Fatalf("Find: %v", err)
	}
	if len(resp.Opportunities) != 0 {
		t.Fatalf("expected 0 opportunities at 30%% min margin, got %d", len(resp.Opportunities))
	}
}

func TestFindSkipsLowSampleCountries(t *testing.T) {
	fs := newFakeStore()
	fs.stats = []store.CountryStats{
		{Country: "DE", Count: 50, P50: 20000},
		{Country: "ES", Count: 1, P50: 25000}, // below MinSample → ignored as sell market
	}
	svc := New(fs)
	svc.now = fixedNow
	resp, err := svc.Find(context.Background(), store.Filter{Make: "BMW", Model: "3 Series"}, nil, Options{})
	if err != nil {
		t.Fatalf("Find: %v", err)
	}
	if len(resp.Opportunities) != 0 {
		t.Fatalf("expected 0 opportunities (ES under-sampled), got %d", len(resp.Opportunities))
	}
}

func TestHandlerRequiresMakeModel(t *testing.T) {
	svc := New(newFakeStore())
	h := Handler(svc, nil, time.Minute, 20*time.Second, slog.New(slog.DiscardHandler))

	req := httptest.NewRequest(http.MethodGet, "/api/v1/arbitrage?make=BMW", nil)
	rec := httptest.NewRecorder()
	h(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", rec.Code)
	}
}

func TestHandlerReturnsOpportunities(t *testing.T) {
	svc := New(newFakeStore())
	svc.now = fixedNow
	h := Handler(svc, nil, time.Minute, 20*time.Second, slog.New(slog.DiscardHandler))

	req := httptest.NewRequest(http.MethodGet, "/api/v1/arbitrage?make=BMW&model=3+Series", nil)
	rec := httptest.NewRecorder()
	h(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200; body=%s", rec.Code, rec.Body.String())
	}
	var resp Response
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(resp.Opportunities) != 1 {
		t.Fatalf("expected 1 opportunity, got %d", len(resp.Opportunities))
	}
	if resp.Currency != "EUR" {
		t.Errorf("currency = %q, want EUR", resp.Currency)
	}
}
