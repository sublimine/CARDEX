package e06_microdata_test

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"cardex.eu/extraction/internal/extractor/e06_microdata"
	"cardex.eu/extraction/internal/pipeline"
)

// TestE06_Microdata_FlatProperties verifies that a page with a flat Microdata
// Car block (no nested Offer) is correctly parsed into a VehicleRaw.
func TestE06_Microdata_FlatProperties(t *testing.T) {
	htmlPage := `<!DOCTYPE html><html><body>
<div itemscope itemtype="https://schema.org/Car">
  <span itemprop="brand">BMW</span>
  <span itemprop="model">320d</span>
  <meta itemprop="vehicleModelDate" content="2021"/>
  <meta itemprop="vehicleIdentificationNumber" content="WBAWBAWBA12345001"/>
  <meta itemprop="mileageFromOdometer" content="45000"/>
  <span itemprop="color">Blue Metallic</span>
</div>
</body></html>`

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/":
			w.Header().Set("Content-Type", "text/html")
			fmt.Fprint(w, htmlPage)
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	strategy := e06_microdata.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:      "D1",
		Domain:  srv.Listener.Addr().String(),
		URLRoot: srv.URL,
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) == 0 {
		t.Fatal("want >=1 vehicle from Microdata, got 0")
	}
	v := result.Vehicles[0]
	if v.Make == nil || *v.Make == "" {
		t.Error("want Make set from itemprop=brand, got nil/empty")
	}
	if v.Model == nil || *v.Model == "" {
		t.Error("want Model set from itemprop=model, got nil/empty")
	}
	if v.VIN == nil {
		t.Error("want VIN set from itemprop=vehicleIdentificationNumber, got nil")
	}
	if result.Strategy != "E06" {
		t.Errorf("want strategy E06, got %q", result.Strategy)
	}
}

// TestE06_Microdata_NestedOffer verifies that a Microdata Car block with a nested
// Offer scope correctly extracts price and currency.
func TestE06_Microdata_NestedOffer(t *testing.T) {
	htmlPage := `<!DOCTYPE html><html><body>
<article itemscope itemtype="http://schema.org/Car">
  <span itemprop="brand">Renault</span>
  <span itemprop="model">Clio</span>
  <meta itemprop="vehicleModelDate" content="2020"/>
  <div itemprop="offers" itemscope itemtype="http://schema.org/Offer">
    <meta itemprop="price" content="9500"/>
    <meta itemprop="priceCurrency" content="EUR"/>
  </div>
</article>
</body></html>`

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/":
			w.Header().Set("Content-Type", "text/html")
			fmt.Fprint(w, htmlPage)
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	strategy := e06_microdata.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:      "D2",
		Domain:  srv.Listener.Addr().String(),
		URLRoot: srv.URL,
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) == 0 {
		t.Fatal("want >=1 vehicle, got 0")
	}
	v := result.Vehicles[0]
	if v.PriceGross == nil || *v.PriceGross <= 0 {
		t.Error("want PriceGross set from nested Offer, got nil/zero")
	}
	if v.Currency == nil || *v.Currency != "EUR" {
		t.Errorf("want Currency=EUR from nested Offer, got %v", v.Currency)
	}
}

// TestE06_RDFa_Vehicle verifies that an RDFa typeof="Car" block is parsed into
// a VehicleRaw. RDFa uses vocab/typeof/property instead of itemscope/itemtype/itemprop.
func TestE06_RDFa_Vehicle(t *testing.T) {
	htmlPage := `<!DOCTYPE html><html><body>
<div vocab="https://schema.org/" typeof="Car">
  <span property="brand">Toyota</span>
  <span property="model">Yaris</span>
  <meta property="vehicleModelDate" content="2022"/>
  <meta property="vehicleIdentificationNumber" content="JTDBXZZE2A3012345"/>
  <meta property="price" content="15900"/>
  <span property="color">White</span>
</div>
</body></html>`

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/":
			w.Header().Set("Content-Type", "text/html")
			fmt.Fprint(w, htmlPage)
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	strategy := e06_microdata.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:      "D3",
		Domain:  srv.Listener.Addr().String(),
		URLRoot: srv.URL,
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) == 0 {
		t.Fatal("want >=1 vehicle from RDFa, got 0")
	}
	v := result.Vehicles[0]
	if v.Make == nil || *v.Make == "" {
		t.Error("want Make set from RDFa property=brand, got nil/empty")
	}
	if v.Model == nil {
		t.Error("want Model set from RDFa property=model, got nil")
	}
}

// TestE06_HTTP429_Graceful verifies that a 429 response is handled gracefully:
// 0 vehicles returned, error recorded, no panic.
func TestE06_HTTP429_Graceful(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	defer srv.Close()

	strategy := e06_microdata.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:      "D4",
		Domain:  srv.Listener.Addr().String(),
		URLRoot: srv.URL,
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected top-level error: %v", err)
	}
	if len(result.Vehicles) != 0 {
		t.Errorf("want 0 vehicles from 429 response, got %d", len(result.Vehicles))
	}
	if len(result.Errors) == 0 {
		t.Error("want at least 1 error recorded for 429 page response")
	}
}
