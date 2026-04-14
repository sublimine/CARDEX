package vies_test

import (
	"context"
	"encoding/json"
	"math"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"cardex.eu/discovery/internal/families/familia_m/vies"
	"cardex.eu/discovery/internal/kg"
)

// ── KG stub ──────────────────────────────────────────────────────────────────

type stubGraph struct {
	kg.KnowledgeGraph
	candidates    []*kg.DealerVATCandidate
	validations   map[string]string // dealerID → status
	confidences   map[string]float64
}

func newStubGraph(candidates []*kg.DealerVATCandidate) *stubGraph {
	return &stubGraph{
		candidates:  candidates,
		validations: make(map[string]string),
		confidences: make(map[string]float64),
	}
}

func (g *stubGraph) FindDealersForVATValidation(_ context.Context, _ []string, _ int) ([]*kg.DealerVATCandidate, error) {
	return g.candidates, nil
}
func (g *stubGraph) UpdateVATValidation(_ context.Context, dealerID string, _ time.Time, status string) error {
	g.validations[dealerID] = status
	return nil
}
func (g *stubGraph) UpdateConfidenceScore(_ context.Context, dealerID string, score float64) error {
	g.confidences[dealerID] = score
	return nil
}

// ── Tests ─────────────────────────────────────────────────────────────────────

func viesServer(t *testing.T, responses map[string]map[string]interface{}) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// URL pattern: /ms/{country}/vat/{vat}
		parts := strings.Split(strings.TrimPrefix(r.URL.Path, "/"), "/")
		// parts: ["ms", country, "vat", vatNum]
		if len(parts) < 4 {
			http.NotFound(w, r)
			return
		}
		country := parts[1]
		vatNum := parts[3]
		key := country + ":" + vatNum
		body, ok := responses[key]
		if !ok {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(body)
	}))
}

func TestValidateVAT_Valid(t *testing.T) {
	srv := viesServer(t, map[string]map[string]interface{}{
		"FR:12345678901": {
			"isValid":     true,
			"requestDate": "2026-04-15T10:00:00",
			"userError":   "VALID",
			"name":        "GARAGE DUPONT SA",
			"address":     "12 RUE DE LA PAIX\n75001 PARIS",
		},
	})
	defer srv.Close()

	v := vies.NewWithBaseURL(nil, srv.URL, 0)
	status, err := v.ValidateVAT(context.Background(), "FR", "FR12345678901")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !status.Valid {
		t.Errorf("want Valid=true, got false")
	}
	if status.UserError != "VALID" {
		t.Errorf("UserError = %q, want VALID", status.UserError)
	}
	if status.Name != "GARAGE DUPONT SA" {
		t.Errorf("Name = %q, want GARAGE DUPONT SA", status.Name)
	}
}

func TestValidateVAT_Invalid(t *testing.T) {
	srv := viesServer(t, map[string]map[string]interface{}{
		"DE:999999999": {
			"isValid":   false,
			"userError": "INVALID",
			"name":      "---",
			"address":   "---",
		},
	})
	defer srv.Close()

	v := vies.NewWithBaseURL(nil, srv.URL, 0)
	status, err := v.ValidateVAT(context.Background(), "DE", "999999999")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if status.Valid {
		t.Error("want Valid=false, got true")
	}
	if status.UserError != "INVALID" {
		t.Errorf("UserError = %q, want INVALID", status.UserError)
	}
}

func TestRun_ValidatesAndBumpsConfidence(t *testing.T) {
	srv := viesServer(t, map[string]map[string]interface{}{
		"FR:12345678901": {
			"isValid":   true,
			"userError": "VALID",
			"name":      "DUPONT SA",
			"address":   "PARIS",
		},
		"DE:999999999": {
			"isValid":   false,
			"userError": "INVALID",
			"name":      "---",
			"address":   "---",
		},
	})
	defer srv.Close()

	candidates := []*kg.DealerVATCandidate{
		{DealerID: "D1", PrimaryVAT: "FR12345678901", CountryCode: "FR", CanonicalName: "Dupont SA", ConfidenceScore: 0.35},
		{DealerID: "D2", PrimaryVAT: "DE999999999", CountryCode: "DE", CanonicalName: "Unknown GmbH", ConfidenceScore: 0.20},
	}
	graph := newStubGraph(candidates)
	v := vies.NewWithBaseURL(graph, srv.URL, 0)

	result, err := v.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Errors != 0 {
		t.Errorf("want 0 errors, got %d", result.Errors)
	}
	if result.Confirmed != 1 {
		t.Errorf("want 1 confirmed, got %d", result.Confirmed)
	}

	// D1: VALID — confidence bumped
	if graph.validations["D1"] != "VALID" {
		t.Errorf("D1 validation = %q, want VALID", graph.validations["D1"])
	}
	if math.Abs(graph.confidences["D1"]-0.45) > 1e-9 { // 0.35 + 0.10
		t.Errorf("D1 confidence = %f, want 0.45", graph.confidences["D1"])
	}

	// D2: INVALID — confidence unchanged
	if graph.validations["D2"] != "INVALID" {
		t.Errorf("D2 validation = %q, want INVALID", graph.validations["D2"])
	}
	if _, bumped := graph.confidences["D2"]; bumped {
		t.Error("D2 confidence should not be bumped for invalid VAT")
	}
}

func TestRun_NoCandidates(t *testing.T) {
	graph := newStubGraph(nil)
	v := vies.NewWithBaseURL(graph, "http://localhost:0", 0)

	result, err := v.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Confirmed != 0 || result.Errors != 0 {
		t.Errorf("want empty result, got %+v", result)
	}
}
