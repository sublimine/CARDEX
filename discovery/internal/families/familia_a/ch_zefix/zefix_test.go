package ch_zefix_test

import (
	"context"
	"database/sql"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	_ "modernc.org/sqlite"

	"cardex.eu/discovery/internal/db"
	"cardex.eu/discovery/internal/families/familia_a/ch_zefix"
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

// CSV with a NOGA column — two NOGA 4511 entries and one non-matching.
const firmCSV = `uid,name,noga_code,kanton,ort,rechtsform
CHE-123456789,Garage Müller AG,45110,ZH,Zürich,AG
CHE-987654321,Autohaus Espace SA,45111,BE,Bern,SA
CHE-111222333,Bäckerei Schmid GmbH,10710,LU,Luzern,GmbH
`

func TestZefix_CKAN_WithNOGA(t *testing.T) {
	// Resource server (serves the CSV).
	resSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/csv")
		_, _ = w.Write([]byte(firmCSV))
	}))
	defer resSrv.Close()

	// CKAN search server — returns a package pointing to the CSV on resSrv.
	ckanSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body := fmt.Sprintf(`{
			"success": true,
			"result": {
				"count": 1,
				"results": [
					{
						"id": "test-pkg",
						"title": "Firmen Schweiz",
						"resources": [
							{"url": "%s/firmen.csv", "format": "CSV", "name": "firmen.csv"}
						]
					}
				]
			}
		}`, resSrv.URL)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(body))
	}))
	defer ckanSrv.Close()

	kgDB := openTestKGDB(t)
	graph := kg.NewSQLiteGraph(kgDB)

	z := ch_zefix.NewWithURLs(graph, ckanSrv.URL, resSrv.URL)
	result, err := z.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}

	// Two NOGA 4511 entries (45110, 45111 both start with "4511");
	// Bäckerei (10710) must be excluded.
	if result.Discovered != 2 {
		t.Errorf("Discovered = %d, want 2", result.Discovered)
	}
	if result.Errors != 0 {
		t.Errorf("Errors = %d, want 0", result.Errors)
	}

	ctx := context.Background()
	id1, err := graph.FindDealerByIdentifier(ctx, kg.IdentifierZefix, "CHE-123.456.789")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier CHE-123.456.789: %v", err)
	}
	if id1 == "" {
		t.Error("CHE-123.456.789 not found in KG")
	}

	id2, err := graph.FindDealerByIdentifier(ctx, kg.IdentifierZefix, "CHE-987.654.321")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier CHE-987.654.321: %v", err)
	}
	if id2 == "" {
		t.Error("CHE-987.654.321 not found in KG")
	}
}

func TestZefix_HTMLFallback_WhenCKANEmpty(t *testing.T) {
	// CKAN returns no packages → fallback to HTML keyword search.
	ckanSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"success":true,"result":{"count":0,"results":[]}}`))
	}))
	defer ckanSrv.Close()

	// Zefix HTML server — every request returns a table with one company.
	const zefixHTML = `<html><body>
		<table>
		  <tbody>
		    <tr>
		      <td><a href="/en/search/entity/list/uid/CHE-999888777">Autohaus Test AG</a></td>
		      <td>AG</td>
		      <td>ZH</td>
		    </tr>
		  </tbody>
		</table>
	</body></html>`

	zefixSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		_, _ = w.Write([]byte(zefixHTML))
	}))
	defer zefixSrv.Close()

	kgDB := openTestKGDB(t)
	graph := kg.NewSQLiteGraph(kgDB)

	z := ch_zefix.NewWithURLs(graph, ckanSrv.URL, zefixSrv.URL)
	result, err := z.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}

	// 7 keywords each returns 1 company (same UID). After the first upsert,
	// FindDealerByIdentifier returns the existing dealerID so subsequent upserts
	// are idempotent — Discovered is incremented on each call regardless of
	// whether it's a new or existing entity. So we expect ≥ 1.
	if result.Discovered == 0 {
		t.Error("expected Discovered > 0 from HTML fallback")
	}

	ctx := context.Background()
	id, err := graph.FindDealerByIdentifier(ctx, kg.IdentifierZefix, "CHE-999.888.777")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier: %v", err)
	}
	if id == "" {
		t.Error("CHE-999.888.777 not found in KG after HTML fallback")
	}
}
