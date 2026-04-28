package wikidata_test

import (
	"context"
	"database/sql"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"

	_ "modernc.org/sqlite"

	"cardex.eu/discovery/internal/db"
	"cardex.eu/discovery/internal/families/familia_b/wikidata"
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
// discovery/internal/families/familia_b/wikidata/ → ../../../../testdata → discovery/testdata/
func loadFixture(t *testing.T, name string) []byte {
	t.Helper()
	path := filepath.Join("..", "..", "..", "..", "testdata", name)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("loadFixture %q: %v", name, err)
	}
	return data
}

// TestWikidata_RunForCountry verifies that a 2-binding fixture produces exactly
// 2 dealers with the correct identifiers (WIKIDATA_QID, VIES_VAT where present),
// location with lat/lon from WKT, and discovery record with confidence 0.15.
func TestWikidata_RunForCountry(t *testing.T) {
	fixture := loadFixture(t, "wikidata_sparql_response_DE.json")

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			t.Errorf("expected GET, got %s", r.Method)
		}
		accept := r.Header.Get("Accept")
		if accept != "application/sparql-results+json" {
			t.Errorf("unexpected Accept header: %q", accept)
		}
		ua := r.Header.Get("User-Agent")
		if len(ua) < 9 || ua[:9] != "CardexBot" {
			t.Errorf("unexpected User-Agent: %q", ua)
		}
		w.Header().Set("Content-Type", "application/sparql-results+json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(fixture)
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	wd := wikidata.NewWithBaseURL(graph, srv.URL)

	result, err := wd.RunForCountry(context.Background(), "DE")
	if err != nil {
		t.Fatalf("RunForCountry: %v", err)
	}

	// Fixture has 2 bindings: Q12345 (full data) + Q67890 (label only).
	if result.Discovered != 2 {
		t.Errorf("Discovered = %d, want 2", result.Discovered)
	}
	if result.Errors != 0 {
		t.Errorf("Errors = %d, want 0", result.Errors)
	}

	// ── Q12345 — full binding (coords + website + vatID) ──────────────────────

	dealerID1, err := graph.FindDealerByIdentifier(context.Background(),
		kg.IdentifierWikidataQID, "Q12345")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier Q12345: %v", err)
	}
	if dealerID1 == "" {
		t.Fatal("expected dealer found by WIKIDATA_QID Q12345")
	}

	// VIES_VAT identifier must be present.
	vatDealerID, err := graph.FindDealerByIdentifier(context.Background(),
		kg.IdentifierVAT, "DE123456789")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier VIES_VAT: %v", err)
	}
	if vatDealerID != dealerID1 {
		t.Errorf("VIES_VAT points to dealer %q, want %q", vatDealerID, dealerID1)
	}

	// Location with lat/lon from "Point(8.5678 50.1234)" → lon=8.5678, lat=50.1234.
	var lat, lon float64
	row := database.QueryRowContext(context.Background(),
		`SELECT lat, lon FROM dealer_location WHERE dealer_id = ?`, dealerID1)
	if err := row.Scan(&lat, &lon); err != nil {
		t.Fatalf("scan location Q12345: %v", err)
	}
	if lat < 50.12 || lat > 50.13 {
		t.Errorf("lat = %f, want ~50.1234 (WKT Point second field)", lat)
	}
	if lon < 8.56 || lon > 8.58 {
		t.Errorf("lon = %f, want ~8.5678 (WKT Point first field)", lon)
	}

	// Discovery record with confidence = 0.15.
	var confidence float64
	row = database.QueryRowContext(context.Background(),
		`SELECT confidence_contributed FROM discovery_record
		 WHERE dealer_id = ? AND family = 'B' AND sub_technique = 'B.2'`, dealerID1)
	if err := row.Scan(&confidence); err != nil {
		t.Fatalf("scan discovery record Q12345: %v", err)
	}
	if confidence != 0.15 {
		t.Errorf("confidence_contributed = %f, want 0.15", confidence)
	}

	// ── Q67890 — minimal binding (label only, no coords/vatID) ───────────────

	dealerID2, err := graph.FindDealerByIdentifier(context.Background(),
		kg.IdentifierWikidataQID, "Q67890")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier Q67890: %v", err)
	}
	if dealerID2 == "" {
		t.Fatal("expected dealer found by WIKIDATA_QID Q67890")
	}
	if dealerID2 == dealerID1 {
		t.Errorf("Q67890 and Q12345 resolve to the same dealer ID — should be distinct")
	}
}

// TestWikidata_ParseWKT verifies the WKT Point parser handles the Wikidata
// "Point(lon lat)" convention correctly (longitude first, latitude second).
func TestWikidata_ParseWKT(t *testing.T) {
	tests := []struct {
		input   string
		wantLat float64
		wantLon float64
		wantErr bool
	}{
		// Wikidata standard: Point(longitude latitude)
		{"Point(8.5678 50.1234)", 50.1234, 8.5678, false},
		{"Point(2.3522 48.8566)", 48.8566, 2.3522, false},
		{"Point(-3.7038 40.4168)", 40.4168, -3.7038, false}, // Madrid
		{"POINT(7.4474 46.9480)", 46.9480, 7.4474, false},   // Bern, uppercase
		{"Point(0 0)", 0, 0, false},
		{"Point(6.1234 50.5678)", 50.5678, 6.1234, false},
		// Error cases
		{"Point(1)", 0, 0, true},
		{"bad format", 0, 0, true},
		{"Point(a b)", 0, 0, true},
	}
	for _, tc := range tests {
		lat, lon, err := wikidata.ParseWKTPoint(tc.input)
		if tc.wantErr {
			if err == nil {
				t.Errorf("ParseWKTPoint(%q): expected error, got lat=%f lon=%f", tc.input, lat, lon)
			}
			continue
		}
		if err != nil {
			t.Errorf("ParseWKTPoint(%q): unexpected error: %v", tc.input, err)
			continue
		}
		if lat != tc.wantLat {
			t.Errorf("ParseWKTPoint(%q): lat = %f, want %f", tc.input, lat, tc.wantLat)
		}
		if lon != tc.wantLon {
			t.Errorf("ParseWKTPoint(%q): lon = %f, want %f", tc.input, lon, tc.wantLon)
		}
	}
}

// TestWikidata_Timeout verifies that a slow server triggers context cancellation
// and the error is propagated cleanly.
func TestWikidata_Timeout(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Deliberately do not respond — will be cancelled by the test context.
		<-r.Context().Done()
		w.WriteHeader(http.StatusGatewayTimeout)
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	wd := wikidata.NewWithBaseURL(graph, srv.URL)

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	result, err := wd.RunForCountry(ctx, "DE")
	if err == nil {
		t.Fatal("expected error on context cancellation, got nil")
	}
	if result == nil {
		t.Fatal("expected non-nil result even on error")
	}
	if result.Discovered != 0 {
		t.Errorf("Discovered = %d, want 0", result.Discovered)
	}
}

// TestWikidata_UnsupportedCountry verifies that an unknown country code
// returns a descriptive error immediately.
func TestWikidata_UnsupportedCountry(t *testing.T) {
	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	wd := wikidata.NewWithBaseURL(graph, "http://localhost:0")

	_, err := wd.RunForCountry(context.Background(), "XX")
	if err == nil {
		t.Fatal("expected error for unsupported country 'XX', got nil")
	}
}
