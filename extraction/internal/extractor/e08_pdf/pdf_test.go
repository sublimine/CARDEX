package e08_pdf_test

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"cardex.eu/extraction/internal/extractor/e08_pdf"
	"cardex.eu/extraction/internal/pipeline"
)

// TestE08_PDFLinkDiscovery verifies that a homepage containing a PDF link with
// a vehicle keyword (e.g. "catalogue") is discovered and fetched by E08.
func TestE08_PDFLinkDiscovery(t *testing.T) {
	fetched := false

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/":
			host := "http://" + r.Host
			w.Header().Set("Content-Type", "text/html")
			// Homepage contains a link to a PDF catalog.
			fmt.Fprintf(w, `<!DOCTYPE html><html><body>
<a href="%s/catalogue.pdf">Download Vehicle Catalogue</a>
</body></html>`, host)
		case "/catalogue.pdf":
			// Serve minimal content — PDF parse may yield 0 vehicles,
			// but the fetch must happen (no 404/crash).
			fetched = true
			w.Header().Set("Content-Type", "application/pdf")
			// Minimal well-formed PDF header.
			w.Write([]byte("%PDF-1.4\n%%EOF"))
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	strategy := e08_pdf.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:      "D1",
		Domain:  srv.Listener.Addr().String(),
		URLRoot: srv.URL,
	}

	_, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !fetched {
		t.Error("want PDF link to be discovered and fetched, but fetch never happened")
	}
}

// TestE08_ProbePath verifies that E08 finds a PDF at a known probe path
// when the homepage contains no PDF links.
func TestE08_ProbePath(t *testing.T) {
	probed := false

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/":
			// Empty homepage — no PDF links.
			w.Header().Set("Content-Type", "text/html")
			w.Write([]byte(`<!DOCTYPE html><html><body><h1>Dealer</h1></body></html>`))
		case "/catalog.pdf":
			probed = true
			w.Header().Set("Content-Type", "application/pdf")
			w.Write([]byte("%PDF-1.4\n%%EOF"))
		default:
			// HEAD probe for all other paths — return 404.
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer srv.Close()

	strategy := e08_pdf.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:      "D2",
		Domain:  srv.Listener.Addr().String(),
		URLRoot: srv.URL,
	}

	_, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !probed {
		t.Error("want /catalog.pdf to be probed and fetched")
	}
}

// TestE08_NoPDF_NoCrash verifies that when no PDF is found (all 404),
// E08 returns an empty result with a NO_PDF error and does not panic.
func TestE08_NoPDF_NoCrash(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	strategy := e08_pdf.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:      "D3",
		Domain:  srv.Listener.Addr().String(),
		URLRoot: srv.URL,
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) != 0 {
		t.Errorf("want 0 vehicles, got %d", len(result.Vehicles))
	}
	hasNoPDF := false
	for _, e := range result.Errors {
		if e.Code == "NO_PDF" {
			hasNoPDF = true
		}
	}
	if !hasNoPDF {
		t.Error("want NO_PDF error recorded, got none")
	}
	if result.Strategy != "E08" {
		t.Errorf("want strategy E08, got %q", result.Strategy)
	}
}

// TestE08_HTTP429_Graceful verifies that a 429 on the PDF endpoint is handled
// gracefully: error recorded, 0 vehicles, no panic.
func TestE08_HTTP429_Graceful(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/":
			host := "http://" + r.Host
			fmt.Fprintf(w, `<html><body><a href="%s/catalog.pdf">catalog</a></body></html>`, host)
		default:
			w.WriteHeader(http.StatusTooManyRequests)
		}
	}))
	defer srv.Close()

	strategy := e08_pdf.NewWithClient(srv.Client(), 0)
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
		t.Errorf("want 0 vehicles from 429, got %d", len(result.Vehicles))
	}
	if len(result.Errors) == 0 {
		t.Error("want at least 1 error for 429 PDF response")
	}
}
