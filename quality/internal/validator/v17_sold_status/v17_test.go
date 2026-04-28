package v17_sold_status_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v17_sold_status"
)

func serve(status int, body string) *httptest.Server {
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(status)
		_, _ = w.Write([]byte(body))
	}))
}

func vehicle(url string) *pipeline.Vehicle {
	return &pipeline.Vehicle{InternalID: "T1", SourceURL: url}
}

// TestV17_ActiveListing verifies that a live listing passes.
func TestV17_ActiveListing(t *testing.T) {
	srv := serve(200, "<html><body>2019 BMW 3 Series, great condition, call now!</body></html>")
	defer srv.Close()
	val := v17_sold_status.NewWithClient(srv.Client())

	res, err := val.Validate(context.Background(), vehicle(srv.URL))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for active listing, got false: %s", res.Issue)
	}
}

// TestV17_HTTP410 verifies that a 410 Gone response → CRITICAL.
func TestV17_HTTP410(t *testing.T) {
	srv := serve(410, "Gone")
	defer srv.Close()
	val := v17_sold_status.NewWithClient(srv.Client())

	res, err := val.Validate(context.Background(), vehicle(srv.URL))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for HTTP 410, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want CRITICAL for 410, got %s", res.Severity)
	}
}

// TestV17_EnglishSoldKeyword verifies English "sold" keyword detection.
func TestV17_EnglishSoldKeyword(t *testing.T) {
	srv := serve(200, "<html><body><h1>This vehicle has been SOLD</h1></body></html>")
	defer srv.Close()
	val := v17_sold_status.NewWithClient(srv.Client())

	res, err := val.Validate(context.Background(), vehicle(srv.URL))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for 'sold' keyword, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want CRITICAL, got %s", res.Severity)
	}
}

// TestV17_GermanSoldKeyword verifies German "verkauft" keyword detection.
func TestV17_GermanSoldKeyword(t *testing.T) {
	srv := serve(200, "<html><body><p>Dieses Fahrzeug wurde verkauft. Bitte schauen Sie unsere anderen Angebote an.</p></body></html>")
	defer srv.Close()
	val := v17_sold_status.NewWithClient(srv.Client())

	res, err := val.Validate(context.Background(), vehicle(srv.URL))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for German 'verkauft', got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want CRITICAL for sold keyword, got %s", res.Severity)
	}
}

// TestV17_SchemaOrgSoldOut verifies schema.org ItemAvailability SoldOut detection.
func TestV17_SchemaOrgSoldOut(t *testing.T) {
	body := `<html><head>
<script type="application/ld+json">
{"@type":"Car","availability":"http://schema.org/SoldOut","name":"BMW 3"}
</script></head><body>BMW 3</body></html>`
	srv := serve(200, body)
	defer srv.Close()
	val := v17_sold_status.NewWithClient(srv.Client())

	res, err := val.Validate(context.Background(), vehicle(srv.URL))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for schema.org SoldOut, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want CRITICAL for schema.org SoldOut, got %s", res.Severity)
	}
}

// TestV17_NoURL verifies that a vehicle with no SourceURL passes (skipped).
func TestV17_NoURL(t *testing.T) {
	val := v17_sold_status.New()
	res, err := val.Validate(context.Background(), &pipeline.Vehicle{InternalID: "V1"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for empty SourceURL, got false: %s", res.Issue)
	}
}
