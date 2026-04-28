package passive_dns_test

import (
	"context"
	"database/sql"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	_ "modernc.org/sqlite"

	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/db"
	"cardex.eu/discovery/internal/families/familia_c/passive_dns"
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

// TestHackerTarget_RunForDomain verifies CSV parsing and record extraction.
func TestHackerTarget_RunForDomain(t *testing.T) {
	csvResponse := "www.autohaus-example.de,1.2.3.4\nmail.autohaus-example.de,1.2.3.5\nautohaus-example.de,1.2.3.6\n"

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Verify the domain query param is present.
		if q := r.URL.Query().Get("q"); q == "" {
			t.Errorf("missing q param")
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(csvResponse))
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	ht := passive_dns.NewWithBaseURL(graph, database, srv.URL, 0)

	records, err := ht.RunForDomain(context.Background(), "autohaus-example.de")
	if err != nil {
		t.Fatalf("RunForDomain: %v", err)
	}
	if len(records) != 3 {
		t.Fatalf("got %d records, want 3", len(records))
	}

	// Verify both subdomains and root are present.
	domains := make(map[string]string)
	for _, r := range records {
		domains[r.Subdomain] = r.IP
	}
	if domains["www.autohaus-example.de"] != "1.2.3.4" {
		t.Errorf("www subdomain has IP %q, want 1.2.3.4", domains["www.autohaus-example.de"])
	}
	if domains["mail.autohaus-example.de"] != "1.2.3.5" {
		t.Errorf("mail subdomain has IP %q, want 1.2.3.5", domains["mail.autohaus-example.de"])
	}
}

// TestHackerTarget_RunAll verifies that subdomains are upserted into the KG.
func TestHackerTarget_RunAll(t *testing.T) {
	csvResponse := "www.autohaus-test.de,10.0.0.1\nautohaus-test.de,10.0.0.2\n"

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(csvResponse))
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	ht := passive_dns.NewWithBaseURL(graph, database, srv.URL, 0)

	seedWebPresence(t, database, graph, "DE", "autohaus-test.de")

	result, err := ht.RunAll(context.Background(), "DE")
	if err != nil {
		t.Fatalf("RunAll: %v", err)
	}
	if result.Errors != 0 {
		t.Errorf("Errors = %d, want 0", result.Errors)
	}
	// www subdomain should have been added.
	if result.Confirmed < 1 {
		t.Errorf("Confirmed = %d, want >= 1", result.Confirmed)
	}

	// Verify www is now in KG.
	dealerID, err := graph.FindDealerIDByDomain(context.Background(), "www.autohaus-test.de")
	if err != nil {
		t.Fatalf("FindDealerIDByDomain: %v", err)
	}
	if dealerID == "" {
		t.Error("www.autohaus-test.de not found in KG after RunAll")
	}
}

// TestHackerTarget_QuotaExhausted verifies that when the daily limit is already
// reached, RunAll stops processing without making HTTP requests.
func TestHackerTarget_QuotaExhausted(t *testing.T) {
	requestCount := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestCount++
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(""))
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	ht := passive_dns.NewWithBaseURL(graph, database, srv.URL, 0)

	// Pre-seed the rate_limit_state table with today's quota exhausted.
	todayKey := time.Now().UTC().Format("2006-01-02")
	_, err := database.ExecContext(context.Background(), `
		CREATE TABLE IF NOT EXISTS rate_limit_state (
		  api_name     TEXT PRIMARY KEY,
		  reqs_today   INTEGER NOT NULL DEFAULT 0,
		  window_start TEXT NOT NULL
		)`)
	if err != nil {
		t.Fatalf("create rate_limit_state: %v", err)
	}
	_, err = database.ExecContext(context.Background(),
		`INSERT INTO rate_limit_state(api_name, reqs_today, window_start) VALUES('hackertarget_dns', 50, ?)`,
		todayKey)
	if err != nil {
		t.Fatalf("seed rate_limit_state: %v", err)
	}

	seedWebPresence(t, database, graph, "DE", "some-dealer.de")

	result, err := ht.RunAll(context.Background(), "DE")
	if err != nil {
		t.Fatalf("RunAll: %v", err)
	}
	if requestCount != 0 {
		t.Errorf("expected 0 HTTP requests when quota is exhausted, got %d", requestCount)
	}
	if result.Confirmed != 0 {
		t.Errorf("Confirmed = %d, want 0 (quota exhausted)", result.Confirmed)
	}
}

// TestHackerTarget_HTTPError verifies that a non-200 response propagates as error.
func TestHackerTarget_HTTPError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	ht := passive_dns.NewWithBaseURL(graph, database, srv.URL, 0)

	_, err := ht.RunForDomain(context.Background(), "example.de")
	if err == nil {
		t.Fatal("expected error on HTTP 429, got nil")
	}
}

// TestHackerTarget_ErrorLineSkipped verifies that Hackertarget "error" response
// lines (e.g. "error check your api key") are silently skipped.
func TestHackerTarget_ErrorLineSkipped(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("error check your api key\n"))
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	ht := passive_dns.NewWithBaseURL(graph, database, srv.URL, 0)

	records, err := ht.RunForDomain(context.Background(), "example.de")
	if err != nil {
		t.Fatalf("RunForDomain: %v", err)
	}
	if len(records) != 0 {
		t.Errorf("expected 0 records for error response, got %d", len(records))
	}
}
