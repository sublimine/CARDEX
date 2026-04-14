package de_offeneregister_test

import (
	"context"
	"database/sql"
	"path/filepath"
	"testing"

	_ "modernc.org/sqlite"

	"cardex.eu/discovery/internal/db"
	"cardex.eu/discovery/internal/families/familia_a/de_offeneregister"
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

// createOffeneRegisterDB builds a temporary SQLite file that mimics the
// OffeneRegister schema (FTS5 ObjectivesFts) with test data.
// Two automotive companies (C001, C002) and one non-automotive (C003).
func createOffeneRegisterDB(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "offeneregister_test.db")

	testDB, err := sql.Open("sqlite", dbPath)
	if err != nil {
		t.Fatalf("open offeneregister test db: %v", err)
	}
	defer testDB.Close()

	_, err = testDB.Exec(`
		CREATE TABLE IF NOT EXISTS companies (
			id                   TEXT PRIMARY KEY,
			native_company_number TEXT,
			company_number        TEXT,
			company_type          TEXT,
			current_status        TEXT,
			federal_state         TEXT,
			registered_office     TEXT
		);
		CREATE TABLE IF NOT EXISTS names (
			id         INTEGER PRIMARY KEY,
			company_id TEXT,
			name       TEXT
		);
		CREATE TABLE IF NOT EXISTS addresses (
			id             INTEGER PRIMARY KEY,
			company_id     TEXT,
			street_address TEXT,
			city           TEXT,
			zip_code       TEXT
		);
		CREATE TABLE IF NOT EXISTS objectives (
			id         INTEGER PRIMARY KEY,
			company_id TEXT,
			objective  TEXT
		);
		CREATE VIRTUAL TABLE IF NOT EXISTS ObjectivesFts USING fts5(
			objective,
			content=objectives,
			content_rowid=id
		);
	`)
	if err != nil {
		t.Fatalf("create offeneregister schema: %v", err)
	}

	_, err = testDB.Exec(`
		INSERT INTO companies VALUES
			('C001','HRB 12345','HRB 12345','GmbH','currently registered','Bayern','München'),
			('C002','HRB 67890','HRB 67890','AG',  'currently registered','NRW',   'Köln'),
			('C003','HRB 99999','HRB 99999','GmbH','currently registered','Berlin','Berlin');

		INSERT INTO names VALUES
			(1,'C001','Müller Autohaus GmbH'),
			(2,'C002','Rhine Automobil AG'),
			(3,'C003','Berlin Bäckerei GmbH');

		INSERT INTO addresses VALUES
			(1,'C001','Hauptstraße 1','München','80333'),
			(2,'C002','Kölner Ring 5','Köln',   '50667'),
			(3,'C003','Brotweg 3',    'Berlin', '10115');

		INSERT INTO objectives VALUES
			(1,'C001','Handel mit Kraftfahrzeugen, Autohaus und Kfz-Reparatur'),
			(2,'C002','Automobilhandel und Fahrzeugvermietung'),
			(3,'C003','Herstellung und Verkauf von Backwaren');

		INSERT INTO ObjectivesFts(rowid, objective) VALUES
			(1,'Handel mit Kraftfahrzeugen, Autohaus und Kfz-Reparatur'),
			(2,'Automobilhandel und Fahrzeugvermietung'),
			(3,'Herstellung und Verkauf von Backwaren');
	`)
	if err != nil {
		t.Fatalf("insert offeneregister test data: %v", err)
	}

	return dbPath
}

// TestOffeneRegister_Run_WithTestDB tests queryAndUpsert logic by pointing
// the executor at a freshly created test SQLite (ensureDatabase skips download
// when the local file is newer than maxDBAge = 30d).
func TestOffeneRegister_Run_WithTestDB(t *testing.T) {
	testDBPath := createOffeneRegisterDB(t)

	kgDB := openTestKGDB(t)
	graph := kg.NewSQLiteGraph(kgDB)

	o := de_offeneregister.New(graph, testDBPath)
	result, err := o.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}

	// Two automotive companies (C001 Kraftfahrzeuge/Autohaus, C002 Automobilhandel);
	// C003 Bäckerei must not match.
	if result.Discovered != 2 {
		t.Errorf("Discovered = %d, want 2", result.Discovered)
	}
	if result.Errors != 0 {
		t.Errorf("Errors = %d, want 0", result.Errors)
	}

	ctx := context.Background()

	id1, err := graph.FindDealerByIdentifier(ctx, kg.IdentifierHandelsregister, "HRB 12345")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier HRB 12345: %v", err)
	}
	if id1 == "" {
		t.Error("HRB 12345 not found in KG")
	}

	id2, err := graph.FindDealerByIdentifier(ctx, kg.IdentifierHandelsregister, "HRB 67890")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier HRB 67890: %v", err)
	}
	if id2 == "" {
		t.Error("HRB 67890 not found in KG")
	}

	id3, err := graph.FindDealerByIdentifier(ctx, kg.IdentifierHandelsregister, "HRB 99999")
	if err != nil {
		t.Fatalf("FindDealerByIdentifier HRB 99999: %v", err)
	}
	if id3 != "" {
		t.Errorf("HRB 99999 (Bäckerei) should NOT be in KG; got dealerID %q", id3)
	}
}
