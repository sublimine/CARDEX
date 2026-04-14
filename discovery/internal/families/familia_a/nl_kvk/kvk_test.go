package nl_kvk_test

import (
	"context"
	"database/sql"
	"net/http"
	"net/http/httptest"
	"testing"

	_ "modernc.org/sqlite"

	"cardex.eu/discovery/internal/db"
	"cardex.eu/discovery/internal/families/familia_a/nl_kvk"
	"cardex.eu/discovery/internal/kg"
)

func openTestKGDB(t *testing.T) *sql.DB {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("openTestKGDB: %v", err)
	}
	t.Cleanup(func() { _ = database.Close() })
	return database
}

// Minimal Zoeken API v2 response — one automotive company.
const zoekenResponse = `{
  "pagina": 1,
  "aantalResultaten": 1,
  "resultaten": [
    {
      "kvkNummer": "12345678",
      "naam": "Auto Centrum Utrecht BV",
      "adres": {
        "binnenlandsAdres": {
          "type": "binnenlandsAdres",
          "straatnaam": "Autoweg",
          "huisnummer": 42,
          "postcode": "3512AB",
          "plaats": "Utrecht"
        }
      },
      "rechtsvorm": "BV",
      "activiteitenOmschrijving": "Handel in en reparatie van personenautos"
    }
  ]
}`

func TestKvK_Path2_KeywordSearch(t *testing.T) {
	// First call per keyword returns one result; subsequent calls return empty page
	// to stop pagination.
	callCount := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if ua := r.Header.Get("User-Agent"); ua == "" {
			t.Error("missing User-Agent")
		}
		callCount++
		w.Header().Set("Content-Type", "application/json")
		if callCount%2 == 1 {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(zoekenResponse))
		} else {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"pagina":2,"aantalResultaten":0,"resultaten":[]}`))
		}
	}))
	defer srv.Close()

	kgDB := openTestKGDB(t)
	graph := kg.NewSQLiteGraph(kgDB)

	// NewWithBaseURL(graph, db, apiKey, apiBase, bulkURL)
	// bulk is empty — runBulkDensity will fail gracefully (non-fatal).
	k := nl_kvk.NewWithBaseURL(graph, kgDB, "test-api-key", srv.URL, "")
	result, err := k.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}

	if result.Discovered == 0 {
		t.Error("expected Discovered > 0")
	}
	if result.Errors != 0 {
		t.Errorf("Errors = %d, want 0", result.Errors)
	}

	ctx := context.Background()
	dealerID, err := graph.FindDealerByIdentifier(ctx, kg.IdentifierKvK, "12345678")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier: %v", err)
	}
	if dealerID == "" {
		t.Error("KvK 12345678 not found in KG")
	}
}

func TestKvK_RateLimitExhausted(t *testing.T) {
	kgDB := openTestKGDB(t)

	// Pre-seed rate_limit_state with today's quota exhausted.
	// The KvK implementation uses api_name='kvk' as the key.
	_, err := kgDB.Exec(`
		CREATE TABLE IF NOT EXISTS rate_limit_state (
			api_name     TEXT PRIMARY KEY,
			reqs_today   INTEGER NOT NULL DEFAULT 0,
			window_start TEXT NOT NULL
		);
		INSERT INTO rate_limit_state (api_name, reqs_today, window_start)
		VALUES ('kvk', 100, date('now'));
	`)
	if err != nil {
		t.Fatalf("seed rate_limit_state: %v", err)
	}

	graph := kg.NewSQLiteGraph(kgDB)

	apiCallMade := false
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		apiCallMade = true
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"pagina":1,"aantalResultaten":0,"resultaten":[]}`))
	}))
	defer srv.Close()

	k := nl_kvk.NewWithBaseURL(graph, kgDB, "test-key", srv.URL, "")
	result, err := k.Run(context.Background())
	if err != nil {
		t.Fatalf("Run with exhausted rate limit: %v", err)
	}
	if result.Discovered != 0 {
		t.Errorf("Discovered = %d, want 0 (rate limit exhausted)", result.Discovered)
	}
	if apiCallMade {
		t.Error("Zoeken API was called despite exhausted daily quota")
	}
}
