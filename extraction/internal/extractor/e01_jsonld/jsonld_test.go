package e01_jsonld_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"cardex.eu/extraction/internal/extractor/e01_jsonld"
	"cardex.eu/extraction/internal/pipeline"
)

// inventoryPage returns an HTML page containing the given JSON-LD block.
func inventoryPage(jsonLD string) []byte {
	return []byte(`<!DOCTYPE html><html><head>
<script type="application/ld+json">` + jsonLD + `</script>
</head><body><h1>Inventory</h1></body></html>`)
}

// TestE01_SingleCar_HappyPath verifies that a single Car JSON-LD block is
// extracted with all critical fields.
func TestE01_SingleCar_HappyPath(t *testing.T) {
	const jsonLD = `{
  "@context": "https://schema.org",
  "@type": "Car",
  "name": "BMW 320d",
  "brand": { "@type": "Brand", "name": "BMW" },
  "vehicleModel": "3 Series",
  "vehicleModelDate": "2021",
  "mileageFromOdometer": { "@type": "QuantitativeValue", "value": 45000, "unitCode": "KMT" },
  "fuelType": "diesel",
  "vehicleTransmission": "Automatic",
  "offers": {
    "@type": "Offer",
    "price": "28500",
    "priceCurrency": "EUR"
  },
  "url": "https://dealer.example.de/cars/bmw-320d-2021",
  "image": ["https://img.dealer.example.de/bmw-320d-1.jpg", "https://img.dealer.example.de/bmw-320d-2.jpg"]
}`
	srv := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		w.Write(inventoryPage(jsonLD))
	}))
	defer srv.Close()

	strategy := e01_jsonld.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:           "D1",
		Domain:       srv.Listener.Addr().String(),
		URLRoot:      srv.URL,
		PlatformType: "UNKNOWN",
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) != 1 {
		t.Fatalf("want 1 vehicle, got %d", len(result.Vehicles))
	}
	v := result.Vehicles[0]
	if v.Make == nil || *v.Make != "BMW" {
		t.Errorf("want Make=BMW, got %v", v.Make)
	}
	if v.Model == nil || *v.Model != "3 Series" {
		t.Errorf("want Model=3 Series, got %v", v.Model)
	}
	if v.Year == nil || *v.Year != 2021 {
		t.Errorf("want Year=2021, got %v", v.Year)
	}
	if v.FuelType == nil || *v.FuelType != "diesel" {
		t.Errorf("want FuelType=diesel, got %v", v.FuelType)
	}
	if v.Transmission == nil || *v.Transmission != "automatic" {
		t.Errorf("want Transmission=automatic, got %v", v.Transmission)
	}
	if v.PriceGross == nil || *v.PriceGross != 28500 {
		t.Errorf("want PriceGross=28500, got %v", v.PriceGross)
	}
	if len(v.ImageURLs) != 2 {
		t.Errorf("want 2 images, got %d", len(v.ImageURLs))
	}
}

// TestE01_ItemList_ExtractsMultiple verifies that an ItemList containing
// multiple Car entries is fully extracted.
func TestE01_ItemList_ExtractsMultiple(t *testing.T) {
	const jsonLD = `{
  "@context": "https://schema.org",
  "@type": "ItemList",
  "itemListElement": [
    {
      "@type": "Car",
      "brand": { "name": "Renault" },
      "vehicleModel": "Clio",
      "vehicleModelDate": "2020",
      "offers": { "price": 9500, "priceCurrency": "EUR" },
      "url": "https://dealer.example.fr/voitures/renault-clio",
      "image": "https://img.dealer.example.fr/clio.jpg"
    },
    {
      "@type": "Car",
      "brand": { "name": "Peugeot" },
      "vehicleModel": "308",
      "vehicleModelDate": "2019",
      "offers": { "price": 12900, "priceCurrency": "EUR" },
      "url": "https://dealer.example.fr/voitures/peugeot-308",
      "image": "https://img.dealer.example.fr/308.jpg"
    }
  ]
}`
	srv := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		w.Write(inventoryPage(jsonLD))
	}))
	defer srv.Close()

	strategy := e01_jsonld.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:      "D2",
		URLRoot: srv.URL,
		Domain:  srv.Listener.Addr().String(),
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) != 2 {
		t.Fatalf("want 2 vehicles from ItemList, got %d", len(result.Vehicles))
	}
	makes := map[string]bool{}
	for _, v := range result.Vehicles {
		if v.Make != nil {
			makes[*v.Make] = true
		}
	}
	if !makes["Renault"] {
		t.Error("want Renault in extracted vehicles")
	}
	if !makes["Peugeot"] {
		t.Error("want Peugeot in extracted vehicles")
	}
}

// TestE01_MalformedJSONLD verifies graceful handling of malformed JSON-LD
// (no panic, no error, zero vehicles returned).
func TestE01_MalformedJSONLD(t *testing.T) {
	// Missing closing brace — invalid JSON.
	const malformed = `{ "@type": "Car", "brand": { "name": "Broken" `
	srv := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		w.Write(inventoryPage(malformed))
	}))
	defer srv.Close()

	strategy := e01_jsonld.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:      "D3",
		URLRoot: srv.URL,
		Domain:  srv.Listener.Addr().String(),
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Should return 0 vehicles (parse fails gracefully).
	if len(result.Vehicles) != 0 {
		t.Errorf("want 0 vehicles from malformed JSON-LD, got %d", len(result.Vehicles))
	}
}

// TestE01_RelativePhotoURLs verifies that relative photo URLs are resolved to
// absolute URLs using the dealer's base URL.
func TestE01_RelativePhotoURLs(t *testing.T) {
	const jsonLD = `{
  "@context": "https://schema.org",
  "@type": "Car",
  "brand": { "name": "Volkswagen" },
  "vehicleModel": "Golf",
  "vehicleModelDate": "2022",
  "offers": { "price": 22000, "priceCurrency": "EUR" },
  "url": "/cars/vw-golf-2022",
  "image": ["/images/golf-front.jpg", "/images/golf-side.jpg"]
}`
	srv := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		w.Write(inventoryPage(jsonLD))
	}))
	defer srv.Close()

	strategy := e01_jsonld.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:      "D4",
		URLRoot: srv.URL,
		Domain:  srv.Listener.Addr().String(),
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) == 0 {
		t.Fatal("want at least 1 vehicle")
	}
	v := result.Vehicles[0]
	for _, imgURL := range v.ImageURLs {
		if !hasPrefix(imgURL, "https://") && !hasPrefix(imgURL, "http://") {
			t.Errorf("want absolute image URL, got %q", imgURL)
		}
	}
	if v.SourceURL != "" && !hasPrefix(v.SourceURL, "http") {
		t.Errorf("want absolute source URL, got %q", v.SourceURL)
	}
}

func hasPrefix(s, prefix string) bool {
	return len(s) >= len(prefix) && s[:len(prefix)] == prefix
}
