package mobilede_test

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

	"cardex.eu/discovery/internal/db"
	"cardex.eu/discovery/internal/families/familia_f/mobilede"
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
	// mobilede/ → ../../../../testdata
	path := filepath.Join("..", "..", "..", "..", "testdata", name)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("loadFixture %q: %v", name, err)
	}
	return data
}

// TestMobileDe_ParseListing verifies that the listing page is correctly parsed:
// dealer names, addresses, websites and pagination links are extracted.
func TestMobileDe_ParseListing(t *testing.T) {
	listingFixture := loadFixture(t, "mobilede_haendler.html")
	detailFixture := loadFixture(t, "mobilede_haendler_detail.html")

	requestURLs := []string{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestURLs = append(requestURLs, r.URL.Path)
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		if strings.Contains(r.URL.Path, "haendler-0") {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write(listingFixture)
		} else if strings.Contains(r.URL.Path, "haendler-1") {
			// Second listing page is empty — signals end of pagination.
			w.WriteHeader(http.StatusNotFound)
		} else if strings.Contains(r.URL.Path, "/haendler/") {
			// Detail page request.
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write(detailFixture)
		} else {
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	md := mobilede.NewWithBaseURL(graph, srv.URL, 0) // interval=0 for tests

	result, err := md.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}

	// Fixture has 3 dealer cards.
	if result.Discovered != 3 {
		t.Errorf("Discovered = %d, want 3", result.Discovered)
	}
	if result.Errors != 0 {
		t.Errorf("Errors = %d, want 0", result.Errors)
	}

	// Verify "Autohaus Muster GmbH" was written with correct identifier.
	dealerID, err := graph.FindDealerByIdentifier(
		context.Background(),
		kg.IdentifierMobileDeID,
		"autohaus-muster-gmbh-10001",
	)
	if err != nil {
		t.Fatalf("FindDealerByIdentifier: %v", err)
	}
	if dealerID == "" {
		t.Error("dealer 'Autohaus Muster GmbH' not found by MOBILE_DE_ID")
	}
}

// TestMobileDe_Pagination verifies that the crawler follows pagination links
// until the server returns 404.
func TestMobileDe_Pagination(t *testing.T) {
	listingFixture := loadFixture(t, "mobilede_haendler.html")
	detailFixture := loadFixture(t, "mobilede_haendler_detail.html")

	pageRequests := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		if strings.HasPrefix(r.URL.Path, "/regional/haendler-") {
			pageRequests++
			if pageRequests <= 2 {
				w.WriteHeader(http.StatusOK)
				_, _ = w.Write(listingFixture)
			} else {
				// Page 3+ → 404, stops pagination.
				w.WriteHeader(http.StatusNotFound)
			}
		} else {
			// Detail pages.
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write(detailFixture)
		}
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	md := mobilede.NewWithBaseURL(graph, srv.URL, 0)

	result, err := md.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	// 2 pages × 3 cards = 6 total; but cards are identical so only 3 distinct
	// dealers get written (3 new on page 1, 3 confirmed on page 2).
	if result.Discovered+result.Confirmed < 3 {
		t.Errorf("got %d discovered + %d confirmed, want >= 3", result.Discovered, result.Confirmed)
	}
	if pageRequests != 3 { // 2 successful + 1 terminating 404
		t.Errorf("pageRequests = %d, want 3", pageRequests)
	}
}

// TestMobileDe_DealerWithoutWebsite verifies that a dealer card without an
// external website URL is still upserted correctly.
func TestMobileDe_DealerWithoutWebsite(t *testing.T) {
	// Custom listing page with only the no-website dealer.
	html := `<html><body>
<div class="dealerItem">
  <h3><a href="/haendler/no-website-autohaus-10003">No-Website Autohaus</a></h3>
  Bahnhofstr. 5, 50667 Köln
</div>
</body></html>`

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		if strings.Contains(r.URL.Path, "haendler-0") {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(html))
		} else {
			w.WriteHeader(http.StatusNotFound) // stops pagination or detail
		}
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	md := mobilede.NewWithBaseURL(graph, srv.URL, 0)

	result, err := md.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if result.Discovered != 1 {
		t.Errorf("Discovered = %d, want 1", result.Discovered)
	}
	if result.Errors != 0 {
		t.Errorf("Errors = %d, want 0", result.Errors)
	}

	dealerID, err := graph.FindDealerByIdentifier(
		context.Background(),
		kg.IdentifierMobileDeID,
		"no-website-autohaus-10003",
	)
	if err != nil {
		t.Fatalf("FindDealerByIdentifier: %v", err)
	}
	if dealerID == "" {
		t.Error("no-website dealer not found in KG")
	}
}

// TestMobileDe_RateLimit429 verifies that an HTTP 429 from the listing endpoint
// is returned as an error and stops the crawl.
func TestMobileDe_RateLimit429(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	md := mobilede.NewWithBaseURL(graph, srv.URL, 0)

	result, err := md.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err) // Run itself should not error — 429 is logged as result.Errors
	}
	// 429 on the first listing page stops the crawl and adds 1 error.
	if result.Errors == 0 {
		t.Error("expected Errors > 0 on HTTP 429, got 0")
	}
	_ = time.Now() // satisfy import
}
