package server

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"fmt"
	"time"

	"github.com/oklog/ulid/v2"
)

const schemaEdge = `
CREATE TABLE IF NOT EXISTS edge_dealers (
    dealer_id    TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    country      TEXT NOT NULL,
    vat_number   TEXT NOT NULL,
    api_key_hash TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    revoked_at   TEXT,
    vies_verified INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS edge_inventory_staging (
    id            TEXT PRIMARY KEY,
    dealer_id     TEXT NOT NULL REFERENCES edge_dealers(dealer_id),
    vehicles_json TEXT NOT NULL,
    received_at   TEXT NOT NULL,
    consumed      INTEGER NOT NULL DEFAULT 0,
    consumed_at   TEXT
);
`

// DB wraps the SQLite database for edge dealer operations.
type DB struct {
	db *sql.DB
}

// NewDB opens the SQLite DB and ensures the edge schema exists.
func NewDB(dbPath string) (*DB, error) {
	db, err := sql.Open("sqlite", dbPath+"?_journal_mode=WAL&_busy_timeout=10000")
	if err != nil {
		return nil, fmt.Errorf("edge/server.NewDB: open %q: %w", dbPath, err)
	}
	db.SetMaxOpenConns(1)
	if _, err := db.Exec(schemaEdge); err != nil {
		db.Close()
		return nil, fmt.Errorf("edge/server.NewDB: schema: %w", err)
	}
	return &DB{db: db}, nil
}

// Close releases the database connection.
func (d *DB) Close() error { return d.db.Close() }

// ValidateAPIKey returns true if the api_key matches the stored hash for the
// dealer and the dealer account is not revoked.
func (d *DB) ValidateAPIKey(ctx context.Context, dealerID, apiKey string) (bool, error) {
	hash := hashAPIKey(apiKey)
	var stored string
	var revokedAt sql.NullString
	err := d.db.QueryRowContext(ctx,
		`SELECT api_key_hash, revoked_at FROM edge_dealers WHERE dealer_id = ?`,
		dealerID,
	).Scan(&stored, &revokedAt)
	if err == sql.ErrNoRows {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	if revokedAt.Valid {
		return false, nil // revoked
	}
	return stored == hash, nil
}

// DealerExists returns true if the dealer_id exists in edge_dealers.
func (d *DB) DealerExists(ctx context.Context, dealerID string) (bool, error) {
	var count int
	err := d.db.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM edge_dealers WHERE dealer_id = ? AND revoked_at IS NULL`,
		dealerID,
	).Scan(&count)
	return count > 0, err
}

// RegisterDealer inserts a new dealer and returns the generated dealer_id and
// plaintext api_key.  The api_key is hashed before storage.
func (d *DB) RegisterDealer(ctx context.Context, name, country, vatNumber string, viesVerified bool) (dealerID, apiKey string, err error) {
	dealerID = ulid.Make().String()

	rawKey := make([]byte, 32)
	if _, err = rand.Read(rawKey); err != nil {
		return "", "", fmt.Errorf("RegisterDealer: generate key: %w", err)
	}
	apiKey = hex.EncodeToString(rawKey)
	hash := hashAPIKey(apiKey)

	viesInt := 0
	if viesVerified {
		viesInt = 1
	}

	_, err = d.db.ExecContext(ctx,
		`INSERT INTO edge_dealers (dealer_id, name, country, vat_number, api_key_hash, created_at, vies_verified)
		 VALUES (?, ?, ?, ?, ?, ?, ?)`,
		dealerID, name, country, vatNumber, hash,
		time.Now().UTC().Format(time.RFC3339), viesInt,
	)
	if err != nil {
		return "", "", fmt.Errorf("RegisterDealer: insert: %w", err)
	}
	return dealerID, apiKey, nil
}

// ListDealers returns all dealers (active and revoked).
func (d *DB) ListDealers(ctx context.Context) ([]DealerRow, error) {
	rows, err := d.db.QueryContext(ctx,
		`SELECT dealer_id, name, country, vat_number, created_at, revoked_at, vies_verified
		 FROM edge_dealers ORDER BY created_at DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []DealerRow
	for rows.Next() {
		var r DealerRow
		var revokedAt sql.NullString
		if err := rows.Scan(&r.DealerID, &r.Name, &r.Country, &r.VATNumber,
			&r.CreatedAt, &revokedAt, &r.VIESVerified); err != nil {
			return nil, err
		}
		r.Active = !revokedAt.Valid
		out = append(out, r)
	}
	return out, rows.Err()
}

// RevokeDealer sets revoked_at for the given dealer_id.
// Returns an error if the dealer does not exist or is already revoked.
func (d *DB) RevokeDealer(ctx context.Context, dealerID string) error {
	res, err := d.db.ExecContext(ctx,
		`UPDATE edge_dealers SET revoked_at = ?
		 WHERE dealer_id = ? AND revoked_at IS NULL`,
		time.Now().UTC().Format(time.RFC3339), dealerID,
	)
	if err != nil {
		return err
	}
	n, _ := res.RowsAffected()
	if n == 0 {
		return fmt.Errorf("dealer %q not found or already revoked", dealerID)
	}
	return nil
}

// DealerRow is one row from the edge_dealers table (no api_key_hash).
type DealerRow struct {
	DealerID     string
	Name         string
	Country      string
	VATNumber    string
	CreatedAt    string
	Active       bool
	VIESVerified int
}

// hashAPIKey returns the hex-encoded SHA-256 of the plaintext key.
func hashAPIKey(key string) string {
	sum := sha256.Sum256([]byte(key))
	return hex.EncodeToString(sum[:])
}
