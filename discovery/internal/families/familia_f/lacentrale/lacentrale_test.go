package lacentrale_test

import (
	"context"
	"database/sql"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	_ "modernc.org/sqlite"

	"cardex.eu/discovery/internal/db"
	"cardex.eu/discovery/internal/families/familia_f/lacentrale"
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
	// lacentrale/ → ../../../../testdata
	path := filepath.Join("..", "..", "..", "..", "testdata", name)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("loadFixture %q: %v", name, err)
	}
	return data
}

// TestLaCentrale_Run_ParsesGarages verifies that the full two-level crawl
// (region index → garage listing) correctly upserts dealers into the KG.
func TestLaCentrale_Run_ParsesGarages(t *testing.T) {
	regionsFixture := loadFixture(t, "lacentrale_annuaire_regions.html")
	garagesFixture := loadFixture(t, "lacentrale_annuaire_garages.html")

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		switch {
		case r.URL.Path == "/annuaire/garages-regions":
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write(regionsFixture)
		case strings.HasPrefix(r.URL.Path, "/annuaire/garages-regions/"):
			// Garage listing for any region — return the garages fixture once,
			// then 404 for any ?page=2 to stop pagination.
			if r.URL.Query().Get("page") != "" {
				w.WriteHeader(http.StatusNotFound)
			} else {
				w.WriteHeader(http.StatusOK)
				_, _ = w.Write(garagesFixture)
			}
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	lc := lacentrale.NewWithBaseURL(graph, srv.URL, 0)

	result, err := lc.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if result.Errors != 0 {
		t.Errorf("Errors = %d, want 0", result.Errors)
	}

	// The regions fixture has 3 regions; each returns 3 garage cards = 9 total.
	// But garage IDs are the same across regions, so only 3 distinct dealers.
	if result.Discovered < 3 {
		t.Errorf("Discovered = %d, want >= 3", result.Discovered)
	}

	// Verify "Garage Dupont" (lc-75001) is in the KG.
	dealerID, err := graph.FindDealerByIdentifier(
		context.Background(),
		kg.IdentifierLaCentraleProID,
		"lc-75001",
	)
	if err != nil {
		t.Fatalf("FindDealerByIdentifier: %v", err)
	}
	if dealerID == "" {
		t.Error("garage lc-75001 not found in KG")
	}

	// Verify web presence for garage-dupont.fr was created.
	existing, err := graph.FindDealerIDByDomain(context.Background(), "garage-dupont.fr")
	if err != nil {
		t.Fatalf("FindDealerIDByDomain: %v", err)
	}
	if existing == "" {
		t.Error("web presence for garage-dupont.fr not found in KG")
	}
}

// TestLaCentrale_Pagination verifies that the crawler follows pagination
// (next-page link) until no more pages are available.
func TestLaCentrale_Pagination(t *testing.T) {
	regionsFixture := loadFixture(t, "lacentrale_annuaire_regions.html")

	// Listing page 1 has garages and a next-page link.
	page1 := `<!DOCTYPE html><html><body>
<section class="garageListings">
  <article class="garageCard" data-garage-id="lc-p1a">
    <h2 class="garageName"><a href="/annuaire/garage/garage-p1a">Garage Page1A</a></h2>
    <address class="garageAddress">1 rue Test, 75001 Paris</address>
  </article>
</section>
<nav class="pagination">
  <a href="/annuaire/garages-regions/ile-de-france?page=2" class="pagination-next">Page suivante</a>
</nav>
</body></html>`

	// Listing page 2 has garages and no next-page link.
	page2 := `<!DOCTYPE html><html><body>
<section class="garageListings">
  <article class="garageCard" data-garage-id="lc-p2a">
    <h2 class="garageName"><a href="/annuaire/garage/garage-p2a">Garage Page2A</a></h2>
    <address class="garageAddress">2 rue Test, 75002 Paris</address>
  </article>
</section>
</body></html>`

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		switch {
		case r.URL.Path == "/annuaire/garages-regions":
			// Return regions fixture but override with only 1 region for simplicity.
			singleRegion := `<!DOCTYPE html><html><body>
<ul class="regionList">
  <li class="regionItem">
    <a href="/annuaire/garages-regions/ile-de-france" class="regionLink">Île-de-France</a>
  </li>
</ul>
</body></html>`
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(singleRegion))
			_ = regionsFixture // suppress unused warning
		case r.URL.Path == "/annuaire/garages-regions/ile-de-france" && r.URL.Query().Get("page") == "":
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(page1))
		case r.URL.Query().Get("page") == "2":
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(page2))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	lc := lacentrale.NewWithBaseURL(graph, srv.URL, 0)

	result, err := lc.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	// Expect 2 dealers — one from each page.
	if result.Discovered != 2 {
		t.Errorf("Discovered = %d, want 2", result.Discovered)
	}
}

// TestLaCentrale_GarageWithoutWebsite verifies that a garage without an
// external website is still upserted correctly.
func TestLaCentrale_GarageWithoutWebsite(t *testing.T) {
	html := `<!DOCTYPE html><html><body>
<ul class="regionList">
  <li class="regionItem">
    <a href="/annuaire/garages-regions/test-region" class="regionLink">Test</a>
  </li>
</ul>
</body></html>`
	listing := `<!DOCTYPE html><html><body>
<section class="garageListings">
  <article class="garageCard" data-garage-id="lc-nosite">
    <h2 class="garageName"><a href="#">Garage Sans Site</a></h2>
    <address class="garageAddress">99 impasse des Lilas, 69001 Lyon</address>
    <p class="garagePhone">04 72 00 00 00</p>
  </article>
</section>
</body></html>`

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		if r.URL.Path == "/annuaire/garages-regions" {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(html))
		} else {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(listing))
		}
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	lc := lacentrale.NewWithBaseURL(graph, srv.URL, 0)

	result, err := lc.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if result.Discovered != 1 {
		t.Errorf("Discovered = %d, want 1", result.Discovered)
	}

	dealerID, err := graph.FindDealerByIdentifier(
		context.Background(),
		kg.IdentifierLaCentraleProID,
		"lc-nosite",
	)
	if err != nil {
		t.Fatalf("FindDealerByIdentifier: %v", err)
	}
	if dealerID == "" {
		t.Error("no-website garage not found in KG")
	}
}

// TestLaCentrale_RateLimit429 verifies that a 429 from the region index
// is returned as an error (not silently swallowed).
func TestLaCentrale_RateLimit429(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	lc := lacentrale.NewWithBaseURL(graph, srv.URL, 0)

	_, err := lc.Run(context.Background())
	if err == nil {
		t.Fatal("expected error on HTTP 429 from region index, got nil")
	}
	if !strings.Contains(err.Error(), "429") {
		t.Errorf("error should mention 429, got: %v", err)
	}
}
