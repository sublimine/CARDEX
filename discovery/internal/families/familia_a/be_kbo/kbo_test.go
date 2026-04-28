package be_kbo_test

import (
	"archive/zip"
	"bytes"
	"context"
	"database/sql"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	_ "modernc.org/sqlite"

	"cardex.eu/discovery/internal/db"
	"cardex.eu/discovery/internal/families/familia_a/be_kbo"
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

// buildKBOZip creates an in-memory zip containing the four KBO CSV files.
//
// Pipe-delimited rows, UTF-8. Two automotive enterprises (NACE 45111, 45190)
// and one non-automotive (NACE 56101 — restaurant).
func buildKBOZip(t *testing.T) []byte {
	t.Helper()

	files := map[string]string{
		"enterprise.csv": strings.Join([]string{
			"EnterpriseNumber|Status|JuridicalSituation|TypeOfEnterprise|JuridicalForm|StartDate",
			"0123.456.789|AC|000|2|017|2010-01-15",
			"0987.654.321|AC|000|2|017|2015-03-20",
			"0111.222.333|AC|000|2|017|2018-07-01",
		}, "\n"),
		"activity.csv": strings.Join([]string{
			"EntityNumber|ActivityGroup|NaceVersion|NaceCode|Classification",
			"0123.456.789|001|2008|45111|MAIN",
			"0987.654.321|001|2008|45190|MAIN",
			"0111.222.333|001|2008|56101|MAIN",
		}, "\n"),
		"denomination.csv": strings.Join([]string{
			"EntityNumber|Language|TypeOfDenomination|Denomination",
			"0123.456.789|FR|001|GARAGE DU MIDI SA",
			"0987.654.321|NL|001|AUTOHUIS BRUSSEL BV",
			"0111.222.333|FR|001|RESTAURANT CHEZ PIERRE SPRL",
		}, "\n"),
		"address.csv": strings.Join([]string{
			"EntityNumber|TypeOfAddress|CountryNL|Zipcode|MunicipalityNL|StreetNL|HouseNumber",
			"0123.456.789|REGO|België|1000|Bruxelles|Rue du Midi|10",
			"0987.654.321|REGO|België|1050|Bruxelles|Autostraat|25",
			"0111.222.333|REGO|België|2000|Antwerpen|Kookstraat|3",
		}, "\n"),
	}

	var buf bytes.Buffer
	zw := zip.NewWriter(&buf)
	for name, content := range files {
		// KBO zips nest files inside a dated sub-directory.
		w, err := zw.Create("KboOpenData/" + name)
		if err != nil {
			t.Fatalf("zip create %s: %v", name, err)
		}
		if _, err := fmt.Fprint(w, content); err != nil {
			t.Fatalf("zip write %s: %v", name, err)
		}
	}
	if err := zw.Close(); err != nil {
		t.Fatalf("zip close: %v", err)
	}
	return buf.Bytes()
}

func TestKBO_Run_MockServer(t *testing.T) {
	zipBytes := buildKBOZip(t)

	// Three-endpoint mock:
	//   POST /login       → 302 redirect to /download
	//   GET  /login       → login HTML form
	//   GET  /download    → HTML page with zip download link
	//   GET  /files/…     → zip payload
	mux := http.NewServeMux()

	mux.HandleFunc("/login", func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet {
			w.Header().Set("Content-Type", "text/html")
			fmt.Fprint(w, `<html><body>
				<form method="POST" action="/login">
					<input type="hidden" name="_csrf" value="testtoken"/>
					<input name="username"/><input name="password"/>
					<button type="submit">Login</button>
				</form></body></html>`)
			return
		}
		http.Redirect(w, r, "/download", http.StatusFound)
	})

	mux.HandleFunc("/download", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		fmt.Fprint(w, `<html><body>
			<a href="/files/KboOpenData_2024_01_Full.zip">KboOpenData_2024_01_Full.zip</a>
		</body></html>`)
	})

	mux.HandleFunc("/files/", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/zip")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(zipBytes)
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	kgDB := openTestKGDB(t)
	graph := kg.NewSQLiteGraph(kgDB)

	k := be_kbo.NewWithOverrides(graph, "user", "pass",
		srv.URL+"/login",
		srv.URL+"/download",
	)
	result, err := k.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}

	// Two automotive enterprises; restaurant must not appear.
	if result.Discovered != 2 {
		t.Errorf("Discovered = %d, want 2", result.Discovered)
	}
	if result.Errors != 0 {
		t.Errorf("Errors = %d, want 0", result.Errors)
	}

	ctx := context.Background()
	id1, err := graph.FindDealerByIdentifier(ctx, kg.IdentifierKBO, "0123.456.789")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier 0123.456.789: %v", err)
	}
	if id1 == "" {
		t.Error("KBO 0123.456.789 not found in KG")
	}

	id2, err := graph.FindDealerByIdentifier(ctx, kg.IdentifierKBO, "0987.654.321")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier 0987.654.321: %v", err)
	}
	if id2 == "" {
		t.Error("KBO 0987.654.321 not found in KG")
	}

	id3, err := graph.FindDealerByIdentifier(ctx, kg.IdentifierKBO, "0111.222.333")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier 0111.222.333: %v", err)
	}
	if id3 != "" {
		t.Errorf("KBO 0111.222.333 (restaurant) should NOT be in KG; got dealerID %q", id3)
	}
}

func TestKBO_Run_MissingCredentials(t *testing.T) {
	kgDB := openTestKGDB(t)
	graph := kg.NewSQLiteGraph(kgDB)

	k := be_kbo.New(graph, "", "")
	_, err := k.Run(context.Background())
	if err == nil {
		t.Fatal("expected error for missing credentials, got nil")
	}
}
