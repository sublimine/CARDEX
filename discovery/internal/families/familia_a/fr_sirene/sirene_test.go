package fr_sirene_test

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
	"cardex.eu/discovery/internal/families/familia_a/fr_sirene"
	"cardex.eu/discovery/internal/kg"
)

// openTestDB opens an in-memory SQLite database and applies the KG schema.
func openTestDB(t *testing.T) *sql.DB {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("openTestDB: %v", err)
	}
	t.Cleanup(func() { _ = database.Close() })
	return database
}

// loadFixture reads a JSON fixture from ../../testdata/<name>.
func loadFixture(t *testing.T, name string) []byte {
	t.Helper()
	// Resolve relative to the package directory.
	path := filepath.Join("..", "..", "..", "..", "testdata", name)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("loadFixture %q: %v", name, err)
	}
	return data
}

func TestSirene_Run_MockServer(t *testing.T) {
	fixture := loadFixture(t, "sirene_response.json")

	// httptest server that returns the fixture once, then empty pages.
	callCount := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Verify CardexBot UA
		ua := r.Header.Get("User-Agent")
		if ua == "" || ua[:9] != "CardexBot" {
			t.Errorf("unexpected User-Agent: %q", ua)
		}

		callCount++
		if callCount == 1 {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write(fixture)
			return
		}
		// Second call — return empty page to terminate pagination.
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"header":{"total":2,"debut":2,"nombre":0},"etablissements":[]}`))
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)

	// Build Sirene with the test server URL injected via the package-level
	// override hook.
	s := fr_sirene.NewWithBaseURL(graph, "", 60, srv.URL+"/entreprises/sirene/V3/siret")

	result, err := s.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}

	if result.Discovered != 2 {
		t.Errorf("Discovered = %d, want 2", result.Discovered)
	}
	if result.Errors != 0 {
		t.Errorf("Errors = %d, want 0", result.Errors)
	}

	// Verify the SIRET identifiers made it into the KG.
	ctx := context.Background()
	id1, err := graph.FindDealerByIdentifier(ctx, kg.IdentifierSIRET, "12345678900014")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier: %v", err)
	}
	if id1 == "" {
		t.Error("SIRET 12345678900014 not found in KG")
	}

	id2, err := graph.FindDealerByIdentifier(ctx, kg.IdentifierSIRET, "98765432100021")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier: %v", err)
	}
	if id2 == "" {
		t.Error("SIRET 98765432100021 not found in KG")
	}
}
