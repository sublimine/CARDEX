package osm_test

import (
	"context"
	"database/sql"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	_ "modernc.org/sqlite"

	"cardex.eu/discovery/internal/db"
	"cardex.eu/discovery/internal/families/familia_b/osm"
	"cardex.eu/discovery/internal/kg"
)

// openTestDB opens an in-memory SQLite database with the full KG schema applied.
func openTestDB(t *testing.T) *sql.DB {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("openTestDB: %v", err)
	}
	t.Cleanup(func() { _ = database.Close() })
	return database
}

// loadFixture reads a JSON fixture from the shared testdata directory.
// Path resolution: this package is at discovery/internal/families/familia_b/osm/,
// so ../../../../testdata resolves to discovery/testdata/.
func loadFixture(t *testing.T, name string) []byte {
	t.Helper()
	path := filepath.Join("..", "..", "..", "..", "testdata", name)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("loadFixture %q: %v", name, err)
	}
	return data
}

// TestOverpass_RunForCountry verifies that a 2-element fixture response
// (1 named node + 1 unnamed node) results in exactly 1 dealer upserted,
// with the correct OSM_ID identifier, lat/lon location, and discovery record.
func TestOverpass_RunForCountry(t *testing.T) {
	fixture := loadFixture(t, "overpass_response_DE.json")

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST, got %s", r.Method)
		}
		ct := r.Header.Get("Content-Type")
		if ct != "application/x-www-form-urlencoded" {
			t.Errorf("unexpected Content-Type: %q", ct)
		}
		ua := r.Header.Get("User-Agent")
		if len(ua) < 9 || ua[:9] != "CardexBot" {
			t.Errorf("unexpected User-Agent: %q", ua)
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(fixture)
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	op := osm.NewWithBaseURL(graph, srv.URL)

	result, err := op.RunForCountry(context.Background(), "DE")
	if err != nil {
		t.Fatalf("RunForCountry: %v", err)
	}

	// Fixture has 2 nodes: "Auto Müller GmbH" (named) + unnamed node.
	// Only the named node must be upserted.
	if result.Discovered != 1 {
		t.Errorf("Discovered = %d, want 1", result.Discovered)
	}
	if result.Errors != 0 {
		t.Errorf("Errors = %d, want 0", result.Errors)
	}
	if result.Country != "DE" {
		t.Errorf("Country = %q, want %q", result.Country, "DE")
	}

	// OSM_ID identifier must be present: "node/12345678"
	dealerID, err := graph.FindDealerByIdentifier(context.Background(),
		kg.IdentifierOSMID, "node/12345678")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier: %v", err)
	}
	if dealerID == "" {
		t.Fatal("expected dealer to be found by OSM_ID node/12345678, got empty")
	}

	// Location with lat/lon must exist in the database.
	var lat, lon float64
	row := database.QueryRowContext(context.Background(),
		`SELECT lat, lon FROM dealer_location WHERE dealer_id = ?`, dealerID)
	if err := row.Scan(&lat, &lon); err != nil {
		t.Fatalf("scan location: %v", err)
	}
	if lat < 50.12 || lat > 50.13 {
		t.Errorf("lat = %f, want ~50.1234567", lat)
	}
	if lon < 8.56 || lon > 8.58 {
		t.Errorf("lon = %f, want ~8.5678901", lon)
	}

	// Discovery record must exist with confidence = 0.15 (B base weight).
	var confidence float64
	row = database.QueryRowContext(context.Background(),
		`SELECT confidence_contributed FROM discovery_record
		 WHERE dealer_id = ? AND family = 'B' AND sub_technique = 'B.1'`, dealerID)
	if err := row.Scan(&confidence); err != nil {
		t.Fatalf("scan discovery record: %v", err)
	}
	if confidence != 0.15 {
		t.Errorf("confidence_contributed = %f, want 0.15", confidence)
	}
}

// TestOverpass_RateLimit429 verifies that a 429 response results in a
// descriptive error and zero discoveries.
func TestOverpass_RateLimit429(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	op := osm.NewWithBaseURL(graph, srv.URL)

	result, err := op.RunForCountry(context.Background(), "FR")
	if err == nil {
		t.Fatal("expected error on 429 response, got nil")
	}
	if result == nil {
		t.Fatal("expected non-nil result even on error")
	}
	if result.Discovered != 0 {
		t.Errorf("Discovered = %d, want 0", result.Discovered)
	}
}

// TestOverpass_NoName verifies that an element with no name, operator, or brand
// tag is silently skipped and does not produce a dealer entity.
func TestOverpass_NoName(t *testing.T) {
	fixture := []byte(`{
		"elements": [
			{"type":"node","id":99999,"lat":52.0,"lon":13.0,"tags":{"shop":"car"}}
		]
	}`)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(fixture)
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	op := osm.NewWithBaseURL(graph, srv.URL)

	result, err := op.RunForCountry(context.Background(), "DE")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("Discovered = %d, want 0 (unnamed element must be skipped)", result.Discovered)
	}
	if result.Errors != 0 {
		t.Errorf("Errors = %d, want 0 (skip is not an error)", result.Errors)
	}

	// Confirm nothing was written to the KG.
	dealerID, err := graph.FindDealerByIdentifier(context.Background(),
		kg.IdentifierOSMID, "node/99999")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier: %v", err)
	}
	if dealerID != "" {
		t.Errorf("expected no dealer for unnamed node, got dealerID=%q", dealerID)
	}
}

// TestOverpass_WayElement verifies that a way element (with center coordinates)
// is correctly handled, using center.lat/center.lon for the location.
func TestOverpass_WayElement(t *testing.T) {
	fixture := []byte(`{
		"elements": [
			{
				"type": "way",
				"id": 55555555,
				"center": {"lat": 48.8566, "lon": 2.3522},
				"tags": {
					"name": "Concessionnaire Paris Centre",
					"shop": "car"
				}
			}
		]
	}`)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(fixture)
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	op := osm.NewWithBaseURL(graph, srv.URL)

	result, err := op.RunForCountry(context.Background(), "FR")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Discovered != 1 {
		t.Errorf("Discovered = %d, want 1", result.Discovered)
	}

	dealerID, err := graph.FindDealerByIdentifier(context.Background(),
		kg.IdentifierOSMID, "way/55555555")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier: %v", err)
	}
	if dealerID == "" {
		t.Fatal("expected dealer found by OSM_ID way/55555555")
	}

	// Location must use center coordinates.
	var lat, lon float64
	row := database.QueryRowContext(context.Background(),
		`SELECT lat, lon FROM dealer_location WHERE dealer_id = ?`, dealerID)
	if err := row.Scan(&lat, &lon); err != nil {
		t.Fatalf("scan location: %v", err)
	}
	if lat < 48.85 || lat > 48.87 {
		t.Errorf("lat = %f, want ~48.8566", lat)
	}
}
