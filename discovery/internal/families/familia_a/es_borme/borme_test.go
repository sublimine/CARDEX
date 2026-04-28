package es_borme_test

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
	"cardex.eu/discovery/internal/families/familia_a/es_borme"
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
	path := filepath.Join("..", "..", "..", "..", "testdata", name)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("loadFixture %q: %v", name, err)
	}
	return data
}

func TestBORME_Run_MockServer(t *testing.T) {
	fixture := loadFixture(t, "borme_sumario.xml")

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Verify required headers.
		ua := r.Header.Get("User-Agent")
		if !contains(ua, "CardexBot") {
			t.Errorf("expected CardexBot UA, got %q", ua)
		}
		accept := r.Header.Get("Accept")
		if !contains(accept, "application/xml") {
			t.Errorf("expected Accept: application/xml, got %q", accept)
		}
		w.Header().Set("Content-Type", "application/xml")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(fixture)
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)

	b := es_borme.NewWithBaseURL(graph, srv.URL+"/")
	result, err := b.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}

	if result.Discovered == 0 {
		t.Error("expected Discovered > 0, got 0")
	}
	if result.Errors != 0 {
		t.Errorf("expected Errors = 0, got %d", result.Errors)
	}

	// Verify a BORME_ACT identifier was stored in the KG.
	ctx := context.Background()
	dealerID, err := graph.FindDealerByIdentifier(ctx, kg.IdentifierBORMEAct, "BORME-A-2024-001-1")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier: %v", err)
	}
	if dealerID == "" {
		t.Error("BORME-A-2024-001-1 identifier not found in KG")
	}
}

func TestBORME_Run_404_Skipped(t *testing.T) {
	callCount := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)

	b := es_borme.NewWithBaseURL(graph, srv.URL+"/")
	result, err := b.Run(context.Background())
	if err != nil {
		t.Fatalf("Run returned unexpected error: %v", err)
	}
	// 404s are silently skipped — no errors counted, no discoveries.
	if result.Errors != 0 {
		t.Errorf("expected Errors = 0 for all-404 server, got %d", result.Errors)
	}
	if result.Discovered != 0 {
		t.Errorf("expected Discovered = 0 for all-404 server, got %d", result.Discovered)
	}
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(substr) == 0 ||
		func() bool {
			for i := 0; i <= len(s)-len(substr); i++ {
				if s[i:i+len(substr)] == substr {
					return true
				}
			}
			return false
		}())
}
