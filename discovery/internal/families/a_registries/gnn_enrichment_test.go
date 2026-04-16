package a_registries

import (
	"context"
	"database/sql"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	_ "modernc.org/sqlite"
)

// ── Helpers ───────────────────────────────────────────────────────────────────

func openTestDB(t *testing.T) *sql.DB {
	t.Helper()
	db, err := sql.Open("sqlite", ":memory:?_journal_mode=WAL")
	if err != nil {
		t.Fatalf("open test db: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	if err := EnsureLinksSchema(db); err != nil {
		t.Fatalf("ensure schema: %v", err)
	}
	return db
}

func mockGNNServer(t *testing.T, resp any, statusCode int) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(statusCode)
		if err := json.NewEncoder(w).Encode(resp); err != nil {
			t.Logf("mock server encode error: %v", err)
		}
	}))
}

// ── Schema tests ──────────────────────────────────────────────────────────────

func TestEnsureLinksSchema_Idempotent(t *testing.T) {
	db := openTestDB(t) // already calls EnsureLinksSchema once
	if err := EnsureLinksSchema(db); err != nil {
		t.Fatalf("second EnsureLinksSchema: %v", err)
	}
}

// ── PersistLinks tests ────────────────────────────────────────────────────────

func TestPersistLinks_InsertsRows(t *testing.T) {
	db := openTestDB(t)
	links := []PredictedLink{
		{DealerA: "D001", DealerB: "D002", Probability: 0.91, ModelVersion: "v1", PredictedAt: time.Now()},
		{DealerA: "D001", DealerB: "D003", Probability: 0.75, ModelVersion: "v1", PredictedAt: time.Now()},
	}
	if err := PersistLinks(context.Background(), db, links); err != nil {
		t.Fatalf("PersistLinks: %v", err)
	}
	var count int
	if err := db.QueryRow(`SELECT COUNT(*) FROM dealer_predicted_links WHERE dealer_a = 'D001'`).Scan(&count); err != nil {
		t.Fatalf("count: %v", err)
	}
	if count != 2 {
		t.Errorf("want 2 rows, got %d", count)
	}
}

func TestPersistLinks_Upsert(t *testing.T) {
	db := openTestDB(t)
	link := PredictedLink{DealerA: "D001", DealerB: "D002", Probability: 0.70, ModelVersion: "v1", PredictedAt: time.Now()}
	if err := PersistLinks(context.Background(), db, []PredictedLink{link}); err != nil {
		t.Fatalf("first insert: %v", err)
	}
	link.Probability = 0.95
	link.ModelVersion = "v2"
	if err := PersistLinks(context.Background(), db, []PredictedLink{link}); err != nil {
		t.Fatalf("upsert: %v", err)
	}
	var prob float64
	var ver string
	if err := db.QueryRow(`SELECT probability, model_version FROM dealer_predicted_links WHERE dealer_a='D001' AND dealer_b='D002'`).Scan(&prob, &ver); err != nil {
		t.Fatalf("scan: %v", err)
	}
	if prob != 0.95 {
		t.Errorf("want probability 0.95, got %.2f", prob)
	}
	if ver != "v2" {
		t.Errorf("want model_version v2, got %q", ver)
	}
}

func TestPersistLinks_Empty(t *testing.T) {
	db := openTestDB(t)
	if err := PersistLinks(context.Background(), db, nil); err != nil {
		t.Errorf("PersistLinks(nil) should not error: %v", err)
	}
}

// ── PredictLinks (HTTP) tests ─────────────────────────────────────────────────

func TestPredictLinks_Success(t *testing.T) {
	srv := mockGNNServer(t, map[string]any{
		"dealer_id": "D001",
		"predicted_links": []map[string]any{
			{"dst_dealer_id": "D002", "probability": 0.88},
			{"dst_dealer_id": "D003", "probability": 0.71},
		},
	}, http.StatusOK)
	defer srv.Close()

	client := &GNNClient{
		baseURL: srv.URL,
		topK:    5,
		client:  &http.Client{Timeout: 5 * time.Second},
	}
	links, err := client.PredictLinks(context.Background(), "D001")
	if err != nil {
		t.Fatalf("PredictLinks: %v", err)
	}
	if len(links) != 2 {
		t.Errorf("want 2 links, got %d", len(links))
	}
	if links[0].DealerA != "D001" {
		t.Errorf("want DealerA=D001, got %q", links[0].DealerA)
	}
	if links[0].DealerB != "D002" {
		t.Errorf("want DealerB=D002, got %q", links[0].DealerB)
	}
	if links[0].Probability != 0.88 {
		t.Errorf("want Probability=0.88, got %.2f", links[0].Probability)
	}
}

func TestPredictLinks_ServiceError(t *testing.T) {
	srv := mockGNNServer(t, map[string]any{"error": "model not loaded"}, http.StatusServiceUnavailable)
	defer srv.Close()

	client := &GNNClient{
		baseURL: srv.URL,
		topK:    5,
		client:  &http.Client{Timeout: 5 * time.Second},
	}
	_, err := client.PredictLinks(context.Background(), "D001")
	if err == nil {
		t.Error("expected error for 503 response, got nil")
	}
}

func TestPredictLinks_EmptyLinks(t *testing.T) {
	srv := mockGNNServer(t, map[string]any{
		"dealer_id":       "D001",
		"predicted_links": []any{},
		"warning":         "dealer not in index",
	}, http.StatusOK)
	defer srv.Close()

	client := &GNNClient{
		baseURL: srv.URL,
		topK:    5,
		client:  &http.Client{Timeout: 5 * time.Second},
	}
	links, err := client.PredictLinks(context.Background(), "D001")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(links) != 0 {
		t.Errorf("want 0 links for empty response, got %d", len(links))
	}
}

func TestPredictLinks_SkipEnv(t *testing.T) {
	t.Setenv("GNN_SKIP", "true")
	client := NewGNNClient()
	links, err := client.PredictLinks(context.Background(), "D001")
	if err != nil {
		t.Fatalf("unexpected error with GNN_SKIP: %v", err)
	}
	if links != nil {
		t.Errorf("want nil links with GNN_SKIP=true, got %v", links)
	}
}

// ── EnrichDealer integration test ─────────────────────────────────────────────

func TestEnrichDealer_E2E(t *testing.T) {
	srv := mockGNNServer(t, map[string]any{
		"dealer_id": "D001",
		"predicted_links": []map[string]any{
			{"dst_dealer_id": "D002", "probability": 0.90},
			{"dst_dealer_id": "D003", "probability": 0.65},
			{"dst_dealer_id": "D004", "probability": 0.55},
		},
	}, http.StatusOK)
	defer srv.Close()

	db := openTestDB(t)
	client := &GNNClient{
		baseURL: srv.URL,
		topK:    3,
		client:  &http.Client{Timeout: 5 * time.Second},
	}
	if err := EnrichDealer(context.Background(), db, client, "D001"); err != nil {
		t.Fatalf("EnrichDealer: %v", err)
	}

	var count int
	if err := db.QueryRow(`SELECT COUNT(*) FROM dealer_predicted_links WHERE dealer_a='D001'`).Scan(&count); err != nil {
		t.Fatalf("count: %v", err)
	}
	if count != 3 {
		t.Errorf("want 3 persisted links, got %d", count)
	}

	// Verify probability ordering in DB
	rows, err := db.Query(`SELECT dealer_b, probability FROM dealer_predicted_links WHERE dealer_a='D001' ORDER BY probability DESC`)
	if err != nil {
		t.Fatalf("query: %v", err)
	}
	defer rows.Close()
	var prevProb = 1.0
	for rows.Next() {
		var b string
		var prob float64
		if err := rows.Scan(&b, &prob); err != nil {
			t.Fatalf("scan: %v", err)
		}
		if prob > prevProb {
			t.Errorf("probability not descending: %.2f > %.2f", prob, prevProb)
		}
		prevProb = prob
	}
}
