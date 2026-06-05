package marketprice

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"cardex.eu/api/internal/store"
)

type fakeStore struct {
	stats []store.CountryStats
}

func (f *fakeStore) MarketStats(_ context.Context, _ store.Filter) ([]store.CountryStats, error) {
	return f.stats, nil
}
func (f *fakeStore) CheapestListings(_ context.Context, _ store.Filter, _ string, _ int) ([]store.Listing, error) {
	return nil, nil
}
func (f *fakeStore) Ping(_ context.Context) error { return nil }

func TestHandlerRequiresMakeModel(t *testing.T) {
	svc := New(&fakeStore{})
	h := Handler(svc, nil, time.Minute, 15*time.Second, slog.New(slog.DiscardHandler))
	rec := httptest.NewRecorder()
	h(rec, httptest.NewRequest(http.MethodGet, "/api/v1/market-price?make=BMW", nil))
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", rec.Code)
	}
}

func TestHandlerReturnsPercentiles(t *testing.T) {
	svc := New(&fakeStore{stats: []store.CountryStats{
		{Country: "DE", Count: 100, P10: 17000, P25: 18500, P50: 20000, P75: 22000, P90: 24500},
		{Country: "ES", Count: 80, P10: 19000, P25: 21000, P50: 24000, P75: 27000, P90: 30000},
	}})
	h := Handler(svc, nil, time.Minute, 15*time.Second, slog.New(slog.DiscardHandler))
	rec := httptest.NewRecorder()
	h(rec, httptest.NewRequest(http.MethodGet, "/api/v1/market-price?make=BMW&model=320d&year=2020", nil))

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200; body=%s", rec.Code, rec.Body.String())
	}
	var resp Response
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if resp.Currency != "EUR" {
		t.Errorf("currency = %q, want EUR", resp.Currency)
	}
	if len(resp.Countries) != 2 {
		t.Fatalf("got %d countries, want 2", len(resp.Countries))
	}
	if resp.Countries[0].P50 != 20000 {
		t.Errorf("DE P50 = %v, want 20000", resp.Countries[0].P50)
	}
	if resp.Query.Make != "BMW" || resp.Query.YearMin != 2020 {
		t.Errorf("query echo wrong: %+v", resp.Query)
	}
}
