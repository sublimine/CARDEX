package bovag_test

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
	"cardex.eu/discovery/internal/families/familia_g/bovag"
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
	// bovag/ → ../../../../testdata
	p := filepath.Join("..", "..", "..", "..", "testdata", name)
	data, err := os.ReadFile(p)
	if err != nil {
		t.Fatalf("loadFixture %q: %v", name, err)
	}
	return data
}

// TestBOVAG_ParseAndUpsert verifies that the sitemap is parsed, member pages are
// fetched, and dealer records are correctly upserted into the KG.
func TestBOVAG_ParseAndUpsert(t *testing.T) {
	sitemapFixture := loadFixture(t, "bovag_sitemap.xml")
	memberFixture := loadFixture(t, "bovag_member.html")
	noWebsiteFixture := loadFixture(t, "bovag_member_no_website.html")

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		switch {
		case r.URL.Path == "/sitemap.xml":
			w.Header().Set("Content-Type", "application/xml")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write(sitemapFixture)
		case r.URL.Path == "/leden/autohaus-test-bv":
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write(memberFixture)
		case r.URL.Path == "/leden/garage-fixture-two":
			// Reuse the same member fixture with different slug — should confirm, not duplicate.
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write(memberFixture)
		case r.URL.Path == "/leden/bedrijf-no-website":
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write(noWebsiteFixture)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer srv.Close()

	// Rewrite sitemap fixture URLs to point to the test server.
	sitemapRewritten := strings.ReplaceAll(string(sitemapFixture), "https://www.bovag.nl", srv.URL)

	// Serve rewritten sitemap.
	srv2 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		switch {
		case r.URL.Path == "/sitemap.xml":
			w.Header().Set("Content-Type", "application/xml")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(sitemapRewritten))
		case strings.HasPrefix(r.URL.Path, "/leden/autohaus-test-bv"):
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write(memberFixture)
		case strings.HasPrefix(r.URL.Path, "/leden/garage-fixture-two"):
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write(memberFixture)
		case strings.HasPrefix(r.URL.Path, "/leden/bedrijf-no-website"):
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write(noWebsiteFixture)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer srv2.Close()

	_ = srv // unused — use srv2 which serves rewritten sitemap

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	b := bovag.NewWithBaseURL(graph, srv2.URL, 0)

	result, err := b.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}

	// Fixture sitemap has 3 /leden/ URLs: autohaus-test-bv, garage-fixture-two,
	// bedrijf-no-website. garage-fixture-two serves the same member record as
	// autohaus-test-bv (same memberId "12345678"), so it will be confirmed, not new.
	// bedrijf-no-website has memberId "99887766" → new.
	// autohaus-test-bv has memberId "12345678" → new.
	// Total new = 2.
	if result.Discovered < 2 {
		t.Errorf("Discovered = %d, want >= 2", result.Discovered)
	}
	if result.Errors != 0 {
		t.Errorf("Errors = %d, want 0", result.Errors)
	}

	// Verify "Autohaus Test B.V." is findable by MEMBER_BOVAG identifier.
	dealerID, err := graph.FindDealerByIdentifier(context.Background(),
		kg.IdentifierMemberBOVAG, "12345678")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier BOVAG: %v", err)
	}
	if dealerID == "" {
		t.Error("dealer '12345678' not found by MEMBER_BOVAG")
	}

	// Verify KvK cross-reference was also registered.
	dealerIDByKvK, err := graph.FindDealerByIdentifier(context.Background(),
		kg.IdentifierKvK, "12345678")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier KvK: %v", err)
	}
	if dealerIDByKvK == "" {
		t.Error("dealer not found by KVK identifier (cross-reference missing)")
	}
}

// TestBOVAG_NoWebsiteDealer verifies that a member with no website or phone
// is still upserted correctly without panicking.
func TestBOVAG_NoWebsiteDealer(t *testing.T) {
	noWebsiteFixture := loadFixture(t, "bovag_member_no_website.html")

	sitemap := `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>BASEURL/leden/bedrijf-no-website</loc></url>
</urlset>`

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		if r.URL.Path == "/sitemap.xml" {
			w.Header().Set("Content-Type", "application/xml")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(strings.ReplaceAll(sitemap, "BASEURL", "http://"+r.Host)))
		} else if strings.HasPrefix(r.URL.Path, "/leden/bedrijf-no-website") {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write(noWebsiteFixture)
		} else {
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	b := bovag.NewWithBaseURL(graph, srv.URL, 0)

	result, err := b.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if result.Discovered != 1 {
		t.Errorf("Discovered = %d, want 1", result.Discovered)
	}
	if result.Errors != 0 {
		t.Errorf("Errors = %d, want 0", result.Errors)
	}

	// Member ID "99887766" must be present.
	dealerID, err := graph.FindDealerByIdentifier(context.Background(),
		kg.IdentifierMemberBOVAG, "99887766")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier: %v", err)
	}
	if dealerID == "" {
		t.Error("no-website dealer '99887766' not found in KG")
	}
}

// TestBOVAG_SitemapHTTP500 verifies that a server error on the sitemap returns
// an error and does not panic.
func TestBOVAG_SitemapHTTP500(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	b := bovag.NewWithBaseURL(graph, srv.URL, 0)

	result, err := b.Run(context.Background())
	if err == nil {
		t.Error("expected error on sitemap HTTP 500, got nil")
	}
	if result == nil {
		t.Error("expected non-nil result even on error")
	}
}

// TestBOVAG_MemberPageGone verifies that a 404 on a member page is skipped
// gracefully (non-fatal).
func TestBOVAG_MemberPageGone(t *testing.T) {
	sitemap := `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>BASEURL/leden/gone-dealer</loc></url>
</urlset>`

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/sitemap.xml" {
			w.Header().Set("Content-Type", "application/xml")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(strings.ReplaceAll(sitemap, "BASEURL", "http://"+r.Host)))
		} else {
			// Simulate member page removed.
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer srv.Close()

	database := openTestDB(t)
	graph := kg.NewSQLiteGraph(database)
	b := bovag.NewWithBaseURL(graph, srv.URL, 0)

	result, err := b.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: unexpected error: %v", err)
	}
	// 404 on member page is silently skipped — no errors, no discoveries.
	if result.Errors != 0 {
		t.Errorf("Errors = %d, want 0 (404 should be skipped)", result.Errors)
	}
	if result.Discovered != 0 {
		t.Errorf("Discovered = %d, want 0", result.Discovered)
	}
}
