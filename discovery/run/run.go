// Package run exposes a minimal public API over the discovery module's
// internal packages, intended exclusively for e2e integration tests.
//
// Production code must use the discovery service binary directly; this
// package exists only to initialise the shared SQLite schema inside a test
// process.
package run

import (
	"database/sql"

	_ "modernc.org/sqlite"

	"cardex.eu/discovery/internal/db"
)

// InitDB opens (or creates) the SQLite knowledge-graph at path and applies
// all schema migrations (dealer_entity, vehicle_record, etc.).
// The caller owns the returned *sql.DB and must Close it when done.
func InitDB(path string) (*sql.DB, error) {
	return db.Open(path)
}
