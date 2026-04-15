package db

import (
	"database/sql"
	"fmt"
)

// incrementalMigrations are applied in version order after the base schema (v1).
// Each migration is applied at most once — the schema_version table records which
// versions have already been applied.
// sqls may contain multiple SQL statements; each is executed individually so that
// SQLite single-statement constraints (e.g. ALTER TABLE) are respected.
var incrementalMigrations = []struct {
	version     int
	description string
	sqls        []string
}{
	{
		version:     2,
		description: "dealer_web_presence.metadata_json -- Sprint 4 Familia C web cartography",
		sqls:        []string{`ALTER TABLE dealer_web_presence ADD COLUMN metadata_json TEXT`},
	},
	{
		version:     3,
		description: "dealer_location.phone -- Sprint 5 Familia F phone number storage",
		sqls:        []string{`ALTER TABLE dealer_location ADD COLUMN phone TEXT`},
	},
	{
		version:     4,
		description: "dealer_entity VAT validation fields -- Sprint 11 Familia M",
		sqls: []string{
			`ALTER TABLE dealer_entity ADD COLUMN vat_validated_at TEXT`,
			`ALTER TABLE dealer_entity ADD COLUMN vat_valid_status TEXT`,
		},
	},
	{
		version:     5,
		description: "processing_state key-value store -- Sprint 11 Familia K SearXNG checkpoint",
		sqls: []string{`CREATE TABLE IF NOT EXISTS processing_state (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at TEXT NOT NULL
)`},
	},
	{
		version:     6,
		description: "dealer_web_presence CMS fingerprint + extraction hints -- Sprint 12 Familia D",
		sqls: []string{
			`ALTER TABLE dealer_web_presence ADD COLUMN cms_fingerprint_json TEXT`,
			`ALTER TABLE dealer_web_presence ADD COLUMN cms_scanned_at TEXT`,
			`ALTER TABLE dealer_web_presence ADD COLUMN extraction_hints_json TEXT`,
		},
	},
	{
		version:     7,
		description: "dealer_press_signal table -- Sprint 14 Familia O press archives",
		sqls: []string{`CREATE TABLE IF NOT EXISTS dealer_press_signal (
  signal_id     TEXT PRIMARY KEY,
  dealer_id     TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  event_type    TEXT NOT NULL,
  article_url   TEXT,
  article_title TEXT,
  source_family TEXT NOT NULL,
  detected_at   TEXT NOT NULL
)`},
	},
}

// Migrate applies the embedded base schema (v1) on a brand-new database, then
// runs any incremental migrations that have not yet been applied.
// The function is idempotent: re-running on an already-migrated database is safe.
func Migrate(db *sql.DB) error {
	// -- Step 1: Apply base schema if the database is brand-new ----------------
	var count int
	row := db.QueryRow(
		`SELECT COUNT(*) FROM sqlite_master
		  WHERE type='table' AND name='schema_version'`,
	)
	if err := row.Scan(&count); err != nil {
		return fmt.Errorf("migrate: checking schema_version: %w", err)
	}

	if count == 0 {
		// First-ever open: apply full base schema (creates all tables + inserts v1).
		if _, err := db.Exec(schemaSQL); err != nil {
			return fmt.Errorf("migrate: applying base schema: %w", err)
		}
	}

	// -- Step 2: Apply incremental migrations not yet recorded -----------------
	for _, m := range incrementalMigrations {
		var applied int
		if err := db.QueryRow(
			`SELECT COUNT(*) FROM schema_version WHERE version = ?`, m.version,
		).Scan(&applied); err != nil {
			return fmt.Errorf("migrate v%d: check: %w", m.version, err)
		}
		if applied > 0 {
			continue // already applied
		}
		for i, stmt := range m.sqls {
			if _, err := db.Exec(stmt); err != nil {
				return fmt.Errorf("migrate v%d %q stmt[%d]: %w", m.version, m.description, i, err)
			}
		}
		if _, err := db.Exec(
			`INSERT INTO schema_version(version, description) VALUES (?,?)`,
			m.version, m.description,
		); err != nil {
			return fmt.Errorf("migrate v%d: record: %w", m.version, err)
		}
	}
	return nil
}

// Open opens (or creates) the SQLite database at path with WAL mode and
// foreign keys enabled, then runs Migrate.
func Open(path string) (*sql.DB, error) {
	// The DSN uses modernc.org/sqlite query parameters.
	dsn := path + "?_pragma=foreign_keys(ON)&_pragma=journal_mode(WAL)"
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("db.Open %q: %w", path, err)
	}
	db.SetMaxOpenConns(1) // SQLite WAL: single writer is safe and avoids SQLITE_BUSY
	if err := Migrate(db); err != nil {
		_ = db.Close()
		return nil, err
	}
	return db, nil
}
