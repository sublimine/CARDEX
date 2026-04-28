package crtsh_test

import (
	"context"
	"database/sql"
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
	"cardex.eu/discovery/internal/families/familia_c/crtsh"
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
	// discovery/internal/families/familia_c/crtsh/ → ../../../../testdata
	path := filepath.Join("..", "..", "..", "..", "testdata", name)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("loadFixture %q: %v", name, err)
	}
	return data
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

// TestCrtSh_RunForDomain verifies that SAN entries from the fixture are
// returned for the queried domain.
func TestCrtSh_RunForDomain(t *testing.T) {
	fixture := loadFixture(t, "crtsh_response.json")

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Verify correct query parameters.
		q := r.URL.Query()
		if q.Get("output") != "json" {
			t.Errorf("missing output=json, got %q", q.Get("output"))
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(fixture)
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	c := crtsh.NewWithBaseURL(graph, srv.URL, 0)

	sans, err := c.RunForDomain(context.Background(), "autohaus-example.de")
	if err != nil {
		t.Fatalf("RunForDomain: %v", err)
	}

	// The fixture contains:
	//   "autohaus-example.de\nwww.autohaus-example.de\nshop.autohaus-example.de"
	//   "*.autohaus-example.de\nautohaus-example.de"
	// Expected unique SANs related to autohaus-example.de:
	wantSANs := map[string]bool{
		"autohaus-example.de":       true,
		"www.autohaus-example.de":   true,
		"shop.autohaus-example.de":  true,
		"*.autohaus-example.de":     true,
	}

	if len(sans) == 0 {
		t.Fatal("RunForDomain returned no SANs")
	}
	for _, s := range sans {
		if !wantSANs[s] {
			t.Errorf("unexpected SAN %q returned", s)
		}
	}
	// All expected SANs should be present.
	found := make(map[string]bool)
	for _, s := range sans {
		found[s] = true
	}
	for want := range wantSANs {
		if !found[want] {
			t.Errorf("expected SAN %q not found in result", want)
		}
	}
}

// TestCrtSh_RunEnumerationForCountry verifies that subdomain web presence rows
// are created for subdomains discovered via CT enumeration.
func TestCrtSh_RunEnumerationForCountry(t *testing.T) {
	fixture := loadFixture(t, "crtsh_response.json")

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(fixture)
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	c := crtsh.NewWithBaseURL(graph, srv.URL, 0)

	// Seed root domain for DE.
	dealerID := seedWebPresence(t, database, graph, "DE", "autohaus-example.de")
	_ = dealerID

	result, err := c.RunEnumerationForCountry(context.Background(), "DE")
	if err != nil {
		t.Fatalf("RunEnumerationForCountry: %v", err)
	}
	if result.Errors != 0 {
		t.Errorf("Errors = %d, want 0", result.Errors)
	}
	// Subdomains: www.autohaus-example.de and shop.autohaus-example.de should be added.
	// Root domain and wildcard should be skipped.
	if result.Confirmed < 2 {
		t.Errorf("Confirmed = %d, want >= 2 (www + shop subdomains)", result.Confirmed)
	}

	// Verify www subdomain is in the KG.
	subDealerID, err := graph.FindDealerIDByDomain(context.Background(), "www.autohaus-example.de")
	if err != nil {
		t.Fatalf("FindDealerIDByDomain: %v", err)
	}
	if subDealerID == "" {
		t.Error("www.autohaus-example.de not found in KG after enumeration")
	}
}

// TestCrtSh_RunKeywordScan verifies that keyword scan returns unique domains
// from all name_value entries.
func TestCrtSh_RunKeywordScan(t *testing.T) {
	fixture := loadFixture(t, "crtsh_response.json")

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(fixture)
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	c := crtsh.NewWithBaseURL(graph, srv.URL, 0)

	result, err := c.RunKeywordScan(context.Background(), "%.autohaus-example.de")
	if err != nil {
		t.Fatalf("RunKeywordScan: %v", err)
	}
	if result.Query != "%.autohaus-example.de" {
		t.Errorf("Query = %q, want %q", result.Query, "%.autohaus-example.de")
	}
	if len(result.Domains) == 0 {
		t.Error("RunKeywordScan returned no domains")
	}
}

// TestCrtSh_HTTPError verifies that a non-200 response is propagated as an error.
func TestCrtSh_HTTPError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	c := crtsh.NewWithBaseURL(graph, srv.URL, 0)

	_, err := c.RunForDomain(context.Background(), "example.de")
	if err == nil {
		t.Fatal("expected error on HTTP 503, got nil")
	}
}

// TestCrtSh_EmptyResponse verifies that an empty JSON array from crt.sh
// results in zero SANs and no error.
func TestCrtSh_EmptyResponse(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("[]"))
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	c := crtsh.NewWithBaseURL(graph, srv.URL, 0)

	sans, err := c.RunForDomain(context.Background(), "unknown-dealer.de")
	if err != nil {
		t.Fatalf("RunForDomain: %v", err)
	}
	if len(sans) != 0 {
		t.Errorf("expected 0 SANs for empty response, got %d", len(sans))
	}
}
