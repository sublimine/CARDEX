package db

import (
	"database/sql"
	"fmt"
)

// Migrate applies the embedded schema.sql if the schema_version table is absent
// (i.e., a brand-new database). Idempotent: CREATE TABLE IF NOT EXISTS guards
// prevent double-application on subsequent starts.
func Migrate(db *sql.DB) error {
	var count int
	row := db.QueryRow(
		`SELECT COUNT(*) FROM sqlite_master
		  WHERE type='table' AND name='schema_version'`,
	)
	if err := row.Scan(&count); err != nil {
		return fmt.Errorf("migrate: checking schema_version: %w", err)
	}

	if count > 0 {
		// Schema already applied at least once; nothing to do.
		return nil
	}

	if _, err := db.Exec(schemaSQL); err != nil {
		return fmt.Errorf("migrate: applying schema: %w", err)
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
