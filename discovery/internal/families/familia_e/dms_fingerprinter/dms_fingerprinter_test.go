package dms_fingerprinter_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"cardex.eu/discovery/internal/families/familia_e/dms_fingerprinter"
	"cardex.eu/discovery/internal/kg"
)

// stubGraph satisfies kg.KnowledgeGraph for E.1 tests.
type stubGraph struct {
	kg.KnowledgeGraph
	presences   []*kg.DealerWebPresence
	dmsSet      map[string]string // domain -> provider
	dmsSetCalls int
}

func (g *stubGraph) ListWebPresencesForInfraScan(_ context.Context, _ string, _ int) ([]*kg.DealerWebPresence, error) {
	return g.presences, nil
}

func (g *stubGraph) SetDMSProvider(_ context.Context, domain, provider string) error {
	if g.dmsSet == nil {
		g.dmsSet = map[string]string{}
	}
	g.dmsSet[domain] = provider
	g.dmsSetCalls++
	return nil
}

func ptr(s string) *string { return &s }

// TestE1_PromoteFromHints verifies that a D.3 hint is promoted without HTTP requests.
func TestE1_PromoteFromHints(t *testing.T) {
	// No HTTP server needed — the hint path makes zero HTTP requests.
	graph := &stubGraph{
		presences: []*kg.DealerWebPresence{
			{
				Domain:              "dealer.example.de",
				ExtractionHintsJSON: ptr(`{"dms_provider":"dealerconnect.de"}`),
			},
		},
	}
	fp := dms_fingerprinter.NewWithClient(graph, &http.Client{})
	result, err := fp.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 1 {
		t.Errorf("want 1 discovered (hint promotion), got %d", result.Discovered)
	}
	if graph.dmsSet["dealer.example.de"] != "dealerconnect.de" {
		t.Errorf("want dms_provider=dealerconnect.de, got %q", graph.dmsSet["dealer.example.de"])
	}
}

// TestE1_SkipsAlreadySet verifies that presences with an existing dms_provider are counted
// as Confirmed and not re-fetched.
func TestE1_SkipsAlreadySet(t *testing.T) {
	graph := &stubGraph{
		presences: []*kg.DealerWebPresence{
			{
				Domain:      "dealer.example.de",
				DMSProvider: ptr("modix.de"),
			},
		},
	}
	fp := dms_fingerprinter.NewWithClient(graph, &http.Client{})
	result, err := fp.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Confirmed != 1 {
		t.Errorf("want 1 confirmed (already set), got %d", result.Confirmed)
	}
	if graph.dmsSetCalls != 0 {
		t.Errorf("want 0 SetDMSProvider calls, got %d", graph.dmsSetCalls)
	}
}

// TestE1_FingerprintFromBody verifies that a known DMS provider string in the HTML
// body is detected. Uses a TLS test server because fingerprintDomain requests https://.
func TestE1_FingerprintFromBody(t *testing.T) {
	// NewTLSServer issues self-signed cert; srv.Client() trusts it.
	srv := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		_, _ = w.Write([]byte(`<html><body>powered by <a href="https://www.modix.com">Modix</a></body></html>`))
	}))
	defer srv.Close()

	graph := &stubGraph{
		presences: []*kg.DealerWebPresence{
			{Domain: srv.Listener.Addr().String()},
		},
	}
	fp := dms_fingerprinter.NewWithClient(graph, srv.Client())
	result, err := fp.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 1 {
		t.Errorf("want 1 discovered (body detection), got %d", result.Discovered)
	}
	for domain, prov := range graph.dmsSet {
		if prov != "modix.com" {
			t.Errorf("want provider=modix.com for %s, got %q", domain, prov)
		}
	}
}

// TestE1_NoProviderDetected verifies that a response with no DMS signals is handled gracefully.
func TestE1_NoProviderDetected(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		_, _ = w.Write([]byte(`<html><body>Welcome to our dealership</body></html>`))
	}))
	defer srv.Close()

	graph := &stubGraph{
		presences: []*kg.DealerWebPresence{
			{Domain: srv.Listener.Addr().String()},
		},
	}
	fp := dms_fingerprinter.NewWithClient(graph, srv.Client())
	result, err := fp.Run(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("want 0 discovered (no DMS signal), got %d", result.Discovered)
	}
	if graph.dmsSetCalls != 0 {
		t.Errorf("want 0 SetDMSProvider calls, got %d", graph.dmsSetCalls)
	}
}
