package matraba

import (
	"context"
	"database/sql"
	"path/filepath"
	"testing"

	_ "modernc.org/sqlite"
)

func openTestDB(t *testing.T) *sql.DB {
	t.Helper()
	path := filepath.Join(t.TempDir(), "matraba_test.db")
	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	if err := EnsureSchema(db); err != nil {
		t.Fatalf("ensure schema: %v", err)
	}
	return db
}

func TestEnsureSchemaIdempotent(t *testing.T) {
	db := openTestDB(t)
	// Second call must be a no-op.
	if err := EnsureSchema(db); err != nil {
		t.Fatalf("second EnsureSchema: %v", err)
	}
	// Tables should exist.
	for _, tbl := range []string{"matraba_vehicles", "matraba_imports"} {
		var name string
		err := db.QueryRow(
			`SELECT name FROM sqlite_master WHERE type='table' AND name=?`, tbl,
		).Scan(&name)
		if err != nil {
			t.Errorf("expected table %s to exist: %v", tbl, err)
		}
	}
}

func TestStoreImportAndLookupExactVIN(t *testing.T) {
	db := openTestDB(t)
	store := NewStore(db)

	row, _ := fullSampleRow(t)
	rec, err := Parse(row)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}

	feed := make(chan Record, 1)
	feed <- rec
	close(feed)
	stats, err := store.ImportTx(context.Background(), feed)
	if err != nil {
		t.Fatalf("ImportTx: %v", err)
	}
	if stats.RowsWritten != 1 {
		t.Errorf("RowsWritten = %d, want 1", stats.RowsWritten)
	}
	if stats.RowsMasked != 0 {
		t.Errorf("RowsMasked = %d, want 0 (clean VIN)", stats.RowsMasked)
	}

	got, ok, err := store.LookupByVIN(context.Background(), "WVGZZZ5NZAW021819")
	if err != nil {
		t.Fatalf("lookup: %v", err)
	}
	if !ok {
		t.Fatal("VIN not found after import")
	}
	if got.MarcaITV != "VOLKSWAGEN" || got.ModeloITV != "TIGUAN" {
		t.Errorf("round-trip lost fields: %+v", got)
	}
}

func TestStoreUpsertsOnConflict(t *testing.T) {
	db := openTestDB(t)
	store := NewStore(db)

	row1, _ := fullSampleRow(t)
	rec1, _ := Parse(row1)

	// Second import of the same VIN with a different municipality — emulates
	// a TRANSFE row overwriting an older MATRABA row for the same vehicle.
	row2 := buildRow(t, map[int]string{
		7:  "WVGZZZ5NZAW021819",
		31: "BARCELONA",
		20: "08",
	})
	rec2, _ := Parse(row2)

	feed := make(chan Record, 2)
	feed <- rec1
	feed <- rec2
	close(feed)
	if _, err := store.ImportTx(context.Background(), feed); err != nil {
		t.Fatalf("ImportTx: %v", err)
	}

	got, _, _ := store.LookupByVIN(context.Background(), "WVGZZZ5NZAW021819")
	if got.Municipio != "BARCELONA" || got.CodProvinciaVeh != "08" {
		t.Errorf("conflict did not overwrite: %+v", got)
	}
	n, _ := store.Count(context.Background())
	if n != 1 {
		t.Errorf("Count = %d after upsert, want 1", n)
	}
}

func TestStoreLookupByPrefix(t *testing.T) {
	db := openTestDB(t)
	store := NewStore(db)

	// Three VINs sharing the same WMI+VDS3 prefix — simulates post-2025
	// masked data where only the prefix is indexable.
	prefixes := []string{
		"WVGZZZ5NZAW021819",
		"WVGZZZ5NZAW099999",
		"WVGZZZ5NZAW123456",
	}
	feed := make(chan Record, len(prefixes))
	for _, v := range prefixes {
		row := buildRow(t, map[int]string{7: v, 4: "VOLKSWAGEN"})
		rec, _ := Parse(row)
		feed <- rec
	}
	close(feed)
	if _, err := store.ImportTx(context.Background(), feed); err != nil {
		t.Fatalf("ImportTx: %v", err)
	}

	hits, err := store.LookupByPrefix(context.Background(), "WVGZZZ5NZAW", 10)
	if err != nil {
		t.Fatalf("prefix lookup: %v", err)
	}
	if len(hits) != 3 {
		t.Errorf("prefix hits = %d, want 3", len(hits))
	}
}

func TestStoreSkipsEmptyVIN(t *testing.T) {
	db := openTestDB(t)
	store := NewStore(db)

	// Row without a VIN (all spaces in field 7) — common for very old,
	// incomplete historical data; must not be inserted since "" would
	// collide on the primary key.
	row := buildRow(t, map[int]string{4: "SEAT"})
	rec, _ := Parse(row)
	if rec.Bastidor != "" {
		t.Fatalf("expected empty VIN for unset field 7, got %q", rec.Bastidor)
	}

	feed := make(chan Record, 1)
	feed <- rec
	close(feed)
	stats, err := store.ImportTx(context.Background(), feed)
	if err != nil {
		t.Fatalf("ImportTx: %v", err)
	}
	if stats.RowsWritten != 0 {
		t.Errorf("empty-VIN row wrote %d rows, want 0", stats.RowsWritten)
	}
}

func TestStoreRecordImport(t *testing.T) {
	db := openTestDB(t)
	store := NewStore(db)
	err := store.RecordImport(context.Background(),
		"https://www.dgt.es/.../export_mensual_mat_202412.zip",
		"/tmp/export_mensual_mat_202412.zip",
		"matraba", "2024-12",
		1000, 998, 0, nil)
	if err != nil {
		t.Fatalf("RecordImport: %v", err)
	}
	var n int
	db.QueryRow(`SELECT COUNT(*) FROM matraba_imports`).Scan(&n)
	if n != 1 {
		t.Errorf("audit table rows = %d, want 1", n)
	}
}
