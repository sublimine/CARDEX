package wayback_test

import (
	"context"
	"database/sql"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	_ "modernc.org/sqlite"

	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/db"
	"cardex.eu/discovery/internal/families/familia_c/wayback"
	"cardex.eu/discovery/internal/kg"
)

func openTestDB(t *testing.T) *sql.DB {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("openTestDB: %v", err)
	}
	t.Cleanup(func() { _ = database.Close() })
	return database
}

func loadFixture(t *testing.T, name string) []byte {
	t.Helper()
	// discovery/internal/families/familia_c/wayback/ → ../../../../testdata
	path := filepath.Join("..", "..", "..", "..", "testdata", name)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("loadFixture %q: %v", name, err)
	}
	return data
}

// seedWebPresence inserts a dealer entity and web presence entry for testing.
func seedWebPresence(t *testing.T, database *sql.DB, graph kg.KnowledgeGraph, country, domain string) string {
	t.Helper()
	now := time.Now().UTC()
	dealerID := ulid.Make().String()

	entity := &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     domain,
		NormalizedName:    strings.ToLower(domain),
		CountryCode:       country,
		Status:            kg.StatusUnverified,
		ConfidenceScore:   0.10,
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}
	if err := graph.UpsertDealer(context.Background(), entity); err != nil {
		t.Fatalf("seedWebPresence UpsertDealer: %v", err)
	}

	wp := &kg.DealerWebPresence{
		WebID:                ulid.Make().String(),
		DealerID:             dealerID,
		Domain:               domain,
		URLRoot:              "https://" + domain,
		DiscoveredByFamilies: "C",
	}
	if err := graph.UpsertWebPresence(context.Background(), wp); err != nil {
		t.Fatalf("seedWebPresence UpsertWebPresence: %v", err)
	}
	return dealerID
}

// TestWayback_RunForDomain_Available verifies that when all 3 probe timestamps
// return snapshots, the WaybackResult has Available=true and SnapshotCount=3.
func TestWayback_RunForDomain_Available(t *testing.T) {
	fixture := loadFixture(t, "wayback_available.json")

	callCount := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(fixture)
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	wb := wayback.NewWithBaseURL(graph, srv.URL, 0) // interval=0 for fast tests

	result, err := wb.RunForDomain(context.Background(), "autohaus-example.de")
	if err != nil {
		t.Fatalf("RunForDomain: %v", err)
	}

	// 3 probes × 1 HTTP call each = 3 total requests
	if callCount != 3 {
		t.Errorf("callCount = %d, want 3", callCount)
	}
	if !result.Available {
		t.Errorf("Available = false, want true")
	}
	if result.SnapshotCount != 3 {
		t.Errorf("SnapshotCount = %d, want 3", result.SnapshotCount)
	}
	if result.FirstSnapshot == "" {
		t.Errorf("FirstSnapshot should not be empty")
	}
	if result.LastSnapshot == "" {
		t.Errorf("LastSnapshot should not be empty")
	}
	// No probable closure when newest probe also has a snapshot.
	if result.ProbableClosure {
		t.Errorf("ProbableClosure = true, want false (all probes returned snapshots)")
	}
}

// TestWayback_RunForDomain_Unavailable verifies that when no probe timestamps
// return snapshots, Available=false and SnapshotCount=0.
func TestWayback_RunForDomain_Unavailable(t *testing.T) {
	noSnap := []byte(`{"url":"newsite.de","archived_snapshots":{},"timestamp":"20230101"}`)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(noSnap)
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	wb := wayback.NewWithBaseURL(graph, srv.URL, 0)

	result, err := wb.RunForDomain(context.Background(), "newsite.de")
	if err != nil {
		t.Fatalf("RunForDomain: %v", err)
	}
	if result.Available {
		t.Errorf("Available = true, want false")
	}
	if result.SnapshotCount != 0 {
		t.Errorf("SnapshotCount = %d, want 0", result.SnapshotCount)
	}
}

// TestWayback_RunForDomain_ProbableClosure verifies that when the oldest probe
// (6yr ago, request #3) finds a snapshot but the newest probe (1yr ago,
// request #1) does not, ProbableClosure is set.
func TestWayback_RunForDomain_ProbableClosure(t *testing.T) {
	available := []byte(`{
		"archived_snapshots": {
			"closest": {"available":true,"timestamp":"20180610120000","status":"200","url":"http://..."}
		}
	}`)
	unavailable := []byte(`{"archived_snapshots":{}}`)

	callCount := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		// Call 1 = newest probe (1yr ago) → unavailable
		// Call 2 = middle probe (3yr ago) → unavailable
		// Call 3 = oldest probe (6yr ago) → available
		if callCount == 3 {
			_, _ = w.Write(available)
		} else {
			_, _ = w.Write(unavailable)
		}
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	wb := wayback.NewWithBaseURL(graph, srv.URL, 0)

	result, err := wb.RunForDomain(context.Background(), "old-closed-dealer.de")
	if err != nil {
		t.Fatalf("RunForDomain: %v", err)
	}
	if !result.Available {
		t.Errorf("Available = false, want true (oldest probe found snapshot)")
	}
	if result.SnapshotCount != 1 {
		t.Errorf("SnapshotCount = %d, want 1", result.SnapshotCount)
	}
	if !result.ProbableClosure {
		t.Errorf("ProbableClosure = false, want true (oldest has snapshot, newest doesn't)")
	}
}

// TestWayback_RunAll verifies that RunAll updates metadata_json for each
// domain in dealer_web_presence for the given country.
func TestWayback_RunAll(t *testing.T) {
	fixture := loadFixture(t, "wayback_available.json")

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(fixture)
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	wb := wayback.NewWithBaseURL(graph, srv.URL, 0)

	// Seed one dealer+web_presence for DE.
	seedWebPresence(t, database, graph, "DE", "autohaus-test.de")

	result, err := wb.RunAll(context.Background(), "DE")
	if err != nil {
		t.Fatalf("RunAll: %v", err)
	}
	if result.Errors != 0 {
		t.Errorf("Errors = %d, want 0", result.Errors)
	}

	// metadata_json must be set on the web presence entry.
	var metaJSON string
	row := database.QueryRowContext(context.Background(),
		`SELECT metadata_json FROM dealer_web_presence WHERE domain = ?`,
		"autohaus-test.de")
	if err := row.Scan(&metaJSON); err != nil {
		t.Fatalf("scan metadata_json: %v", err)
	}
	if metaJSON == "" {
		t.Fatal("metadata_json is empty after RunAll")
	}

	// Verify it's valid JSON with a wayback_coverage key.
	var m map[string]interface{}
	if err := json.Unmarshal([]byte(metaJSON), &m); err != nil {
		t.Fatalf("metadata_json is not valid JSON: %v", err)
	}
	if _, ok := m["wayback_coverage"]; !ok {
		t.Errorf("metadata_json missing 'wayback_coverage' key: %s", metaJSON)
	}

	// A different country must not be touched.
	result2, err := wb.RunAll(context.Background(), "FR")
	if err != nil {
		t.Fatalf("RunAll FR: %v", err)
	}
	if result2.Confirmed != 0 {
		t.Errorf("RunAll FR: Confirmed = %d, want 0 (no FR presences seeded)", result2.Confirmed)
	}
}

// TestWayback_HTTPError verifies that a non-200 response from the Wayback API
// propagates as an error.
func TestWayback_HTTPError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	wb := wayback.NewWithBaseURL(graph, srv.URL, 0)

	_, err := wb.RunForDomain(context.Background(), "example.de")
	if err == nil {
		t.Fatal("expected error on HTTP 503, got nil")
	}
}
