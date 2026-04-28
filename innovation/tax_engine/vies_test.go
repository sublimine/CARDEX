package tax_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	tax "cardex.eu/tax"
)

// mockVIESServer returns a test server that responds to VIES REST queries.
func mockVIESServer(t *testing.T, validNumbers map[string]bool) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// URL: /ms/{country}/vat/{number}
		vatNumber := r.URL.Path[len("/ms/"):]
		if len(vatNumber) > 3 {
			idx := 0
			for i, c := range vatNumber {
				if c == '/' {
					idx = i
				}
			}
			vatNumber = vatNumber[idx+1:]
		}
		w.Header().Set("Content-Type", "application/json")
		resp := struct {
			IsValid   bool   `json:"isValid"`
			UserError string `json:"userError"`
		}{
			IsValid:   validNumbers[vatNumber],
			UserError: "VALID",
		}
		if err := json.NewEncoder(w).Encode(resp); err != nil {
			t.Errorf("mock VIES: encode: %v", err)
		}
	}))
}

func TestVIESValidate_ValidID(t *testing.T) {
	t.Parallel()
	srv := mockVIESServer(t, map[string]bool{"123456789": true})
	defer srv.Close()

	client := tax.NewVIESClientWithTTL(
		&http.Client{Transport: &proxyTransport{base: srv.URL}},
		time.Minute,
	)

	valid, err := client.Validate(context.Background(), "DE123456789")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !valid {
		t.Error("expected valid=true")
	}
}

func TestVIESValidate_InvalidID(t *testing.T) {
	t.Parallel()
	srv := mockVIESServer(t, map[string]bool{})
	defer srv.Close()

	client := tax.NewVIESClientWithTTL(
		&http.Client{Transport: &proxyTransport{base: srv.URL}},
		time.Minute,
	)

	valid, err := client.Validate(context.Background(), "FR999999999")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if valid {
		t.Error("expected valid=false for unknown number")
	}
}

func TestVIESValidate_EmptyID(t *testing.T) {
	t.Parallel()
	client := tax.NewVIESClient()
	valid, err := client.Validate(context.Background(), "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if valid {
		t.Error("empty ID should return false")
	}
}

func TestVIESValidate_CHNotInVIES(t *testing.T) {
	t.Parallel()
	client := tax.NewVIESClient()
	valid, err := client.Validate(context.Background(), "CHE-123.456.789")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if valid {
		t.Error("CH VAT ID should not be VIES-valid")
	}
}

func TestVIESValidate_CachePreventsSecondCall(t *testing.T) {
	t.Parallel()
	callCount := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(struct {
			IsValid   bool   `json:"isValid"`
			UserError string `json:"userError"`
		}{IsValid: true, UserError: "VALID"})
	}))
	defer srv.Close()

	client := tax.NewVIESClientWithTTL(
		&http.Client{Transport: &proxyTransport{base: srv.URL}},
		time.Hour,
	)

	ctx := context.Background()
	client.Validate(ctx, "DE123456789")
	client.Validate(ctx, "DE123456789") // second call — should hit cache

	if callCount != 1 {
		t.Errorf("expected 1 HTTP call (cached), got %d", callCount)
	}
}

func TestVIESValidateBoth_BothValid(t *testing.T) {
	t.Parallel()
	srv := mockVIESServer(t, map[string]bool{"111": true, "222": true})
	defer srv.Close()

	client := tax.NewVIESClientWithTTL(
		&http.Client{Transport: &proxyTransport{base: srv.URL}},
		time.Minute,
	)

	status := client.ValidateBoth(context.Background(), "DE111", "FR222")
	if !status["DE111"] {
		t.Error("DE111 should be valid")
	}
	if !status["FR222"] {
		t.Error("FR222 should be valid")
	}
}

func TestVIESValidateBoth_OneInvalid_FallbackToMarginScheme(t *testing.T) {
	t.Parallel()
	srv := mockVIESServer(t, map[string]bool{"111": true}) // "222" not valid
	defer srv.Close()

	client := tax.NewVIESClientWithTTL(
		&http.Client{Transport: &proxyTransport{base: srv.URL}},
		time.Minute,
	)

	status := client.ValidateBoth(context.Background(), "DE111", "ES222")

	req := tax.CalculationRequest{
		FromCountry:       "DE",
		ToCountry:         "ES",
		VehiclePriceCents: 1_500_000,
		MarginCents:       200_000,
		SellerVATID:       "DE111",
		BuyerVATID:        "ES222",
	}
	resp := tax.Calculate(req, status)

	if len(resp.Routes) != 1 {
		t.Fatalf("expected 1 route (margin scheme), got %d", len(resp.Routes))
	}
	if resp.Routes[0].Route.Regime != tax.RegimeMarginScheme {
		t.Errorf("expected MarginScheme, got %s", resp.Routes[0].Route.Regime)
	}
}

func TestVIESValidateBoth_EmptyIDs(t *testing.T) {
	t.Parallel()
	client := tax.NewVIESClient()
	status := client.ValidateBoth(context.Background(), "", "")
	if len(status) != 0 {
		t.Errorf("expected empty map for empty IDs, got %v", status)
	}
}

// proxyTransport rewrites requests to go to a fixed base URL (mock server).
type proxyTransport struct {
	base string
}

func (p *proxyTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	mockURL := p.base + req.URL.Path
	if req.URL.RawQuery != "" {
		mockURL += "?" + req.URL.RawQuery
	}
	newReq, err := http.NewRequestWithContext(req.Context(), req.Method, mockURL, req.Body)
	if err != nil {
		return nil, err
	}
	newReq.Header = req.Header
	return http.DefaultTransport.RoundTrip(newReq)
}
