package ch_uid_test

import (
	"context"
	"math"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"cardex.eu/discovery/internal/families/familia_m/ch_uid"
	"cardex.eu/discovery/internal/kg"
)

// ── KG stub ───────────────────────────────────────────────────────────────────

type stubGraph struct {
	kg.KnowledgeGraph
	candidates  []*kg.DealerVATCandidate
	validations map[string]string
	confidences map[string]float64
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

// ── SOAP response fixtures ────────────────────────────────────────────────────

const soapValidResponse = `<?xml version="1.0" encoding="utf-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
  <soap12:Body>
    <GetByUIDResponse xmlns="http://www.uid-wse.admin.ch/V3.0/">
      <GetByUIDResult>
        <organisation>
          <uid><uidOrganisationId>123456789</uidOrganisationId></uid>
          <nameData><name>Garage Mueller AG</name></nameData>
          <address>
            <street>Hauptstrasse</street>
            <houseNumber>42</houseNumber>
            <swissZipCode>8001</swissZipCode>
            <town>Zürich</town>
          </address>
          <uidEntityStatus>1</uidEntityStatus>
        </organisation>
      </GetByUIDResult>
    </GetByUIDResponse>
  </soap12:Body>
</soap12:Envelope>`

const soapNotFoundResponse = `<?xml version="1.0" encoding="utf-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
  <soap12:Body>
    <GetByUIDResponse xmlns="http://www.uid-wse.admin.ch/V3.0/">
      <GetByUIDResult/>
    </GetByUIDResponse>
  </soap12:Body>
</soap12:Envelope>`

// ── Tests ─────────────────────────────────────────────────────────────────────

func TestValidateUID_Active(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/soap+xml; charset=utf-8")
		w.Write([]byte(soapValidResponse))
	}))
	defer srv.Close()

	c := ch_uid.NewWithEndpoint(nil, srv.URL, 0)
	status, err := c.ValidateUID(context.Background(), "CHE-123.456.789")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !status.Valid {
		t.Error("want Valid=true")
	}
	if !status.Active {
		t.Error("want Active=true (status 1)")
	}
	if status.Name != "Garage Mueller AG" {
		t.Errorf("Name = %q, want Garage Mueller AG", status.Name)
	}
	if status.City != "Zürich" {
		t.Errorf("City = %q, want Zürich", status.City)
	}
}

func TestValidateUID_NotFound(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/soap+xml; charset=utf-8")
		w.Write([]byte(soapNotFoundResponse))
	}))
	defer srv.Close()

	c := ch_uid.NewWithEndpoint(nil, srv.URL, 0)
	status, err := c.ValidateUID(context.Background(), "CHE-999.999.999")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if status.Valid {
		t.Error("want Valid=false for missing UID")
	}
}

func TestRun_BumpsConfidenceOnMatch(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/soap+xml; charset=utf-8")
		w.Write([]byte(soapValidResponse))
	}))
	defer srv.Close()

	candidates := []*kg.DealerVATCandidate{
		{DealerID: "D1", PrimaryVAT: "CHE-123.456.789", CountryCode: "CH",
			CanonicalName: "Mueller AG", ConfidenceScore: 0.40},
	}
	graph := newStubGraph(candidates)
	c := ch_uid.NewWithEndpoint(graph, srv.URL, 0)

	result, err := c.Run(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Confirmed != 1 {
		t.Errorf("want 1 confirmed, got %d", result.Confirmed)
	}
	if graph.validations["D1"] != "VALID" {
		t.Errorf("D1 validation = %q, want VALID", graph.validations["D1"])
	}
	if math.Abs(graph.confidences["D1"]-0.50) > 1e-9 { // 0.40 + 0.10
		t.Errorf("D1 confidence = %f, want 0.50", graph.confidences["D1"])
	}
}
