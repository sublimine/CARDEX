package alerts

import (
	"context"
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// ErrNotFound is returned when an alert id does not exist (or is not owned by
// the caller).
var ErrNotFound = errors.New("alert not found")

// Store persists alert definitions in PostgreSQL.
//
// Per ADR-0006 (MVCC discipline: INSERT-new + DELETE-stale, never UPDATE rows),
// alert definitions are immutable once created. Volatile notification state
// (last signature, last fired time) lives in Redis, not in mutable columns —
// see evaluator.go and the redisx alert helpers.
type Store struct {
	pool *pgxpool.Pool
}

// NewStore builds a Store over an existing pool.
func NewStore(pool *pgxpool.Pool) *Store { return &Store{pool: pool} }

// schema is the alerts table DDL. Applied idempotently at startup. There are no
// mutable runtime columns by design (ADR-0006).
const schema = `
CREATE TABLE IF NOT EXISTS arbitrage_alerts (
    id              TEXT PRIMARY KEY,
    owner           TEXT NOT NULL,
    make            TEXT NOT NULL,
    model           TEXT NOT NULL,
    year_min        INT NOT NULL DEFAULT 0,
    year_max        INT NOT NULL DEFAULT 0,
    fuel            TEXT NOT NULL DEFAULT '',
    mileage_min     INT NOT NULL DEFAULT 0,
    mileage_max     INT NOT NULL DEFAULT 0,
    buy_countries   TEXT[] NOT NULL DEFAULT '{}',
    sell_countries  TEXT[] NOT NULL DEFAULT '{}',
    min_margin_pct  DOUBLE PRECISION NOT NULL DEFAULT 5,
    webhook_url     TEXT NOT NULL DEFAULT '',
    email           TEXT NOT NULL DEFAULT '',
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_alerts_active ON arbitrage_alerts (active) WHERE active;
CREATE INDEX IF NOT EXISTS idx_alerts_owner ON arbitrage_alerts (owner);
`

// EnsureSchema creates the alerts table and indexes if absent.
func (s *Store) EnsureSchema(ctx context.Context) error {
	if _, err := s.pool.Exec(ctx, schema); err != nil {
		return fmt.Errorf("ensure alerts schema: %w", err)
	}
	return nil
}

// Create inserts an alert definition.
func (s *Store) Create(ctx context.Context, a Alert) error {
	_, err := s.pool.Exec(ctx, `
        INSERT INTO arbitrage_alerts
            (id, owner, make, model, year_min, year_max, fuel, mileage_min, mileage_max,
             buy_countries, sell_countries, min_margin_pct, webhook_url, email, active, created_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)`,
		a.ID, a.Owner, a.Make, a.Model, a.YearMin, a.YearMax, a.Fuel, a.MileageMin, a.MileageMax,
		a.BuyCountries, a.SellCountries, a.MinMarginPct, a.WebhookURL, a.Email, a.Active, a.CreatedAt)
	if err != nil {
		return fmt.Errorf("insert alert: %w", err)
	}
	return nil
}

const selectCols = `id, owner, make, model, year_min, year_max, fuel, mileage_min, mileage_max,
    buy_countries, sell_countries, min_margin_pct, webhook_url, email, active, created_at`

func scanAlert(row pgx.Row) (Alert, error) {
	var a Alert
	err := row.Scan(&a.ID, &a.Owner, &a.Make, &a.Model, &a.YearMin, &a.YearMax, &a.Fuel,
		&a.MileageMin, &a.MileageMax, &a.BuyCountries, &a.SellCountries, &a.MinMarginPct,
		&a.WebhookURL, &a.Email, &a.Active, &a.CreatedAt)
	return a, err
}

// List returns all alerts for an owner, newest first.
func (s *Store) List(ctx context.Context, owner string) ([]Alert, error) {
	rows, err := s.pool.Query(ctx, `SELECT `+selectCols+`
        FROM arbitrage_alerts WHERE owner = $1 ORDER BY created_at DESC`, owner)
	if err != nil {
		return nil, fmt.Errorf("list alerts: %w", err)
	}
	defer rows.Close()

	var out []Alert
	for rows.Next() {
		a, err := scanAlert(rows)
		if err != nil {
			return nil, fmt.Errorf("scan alert: %w", err)
		}
		out = append(out, a)
	}
	return out, rows.Err()
}

// Get returns one alert by id scoped to owner.
func (s *Store) Get(ctx context.Context, id, owner string) (Alert, error) {
	row := s.pool.QueryRow(ctx, `SELECT `+selectCols+`
        FROM arbitrage_alerts WHERE id = $1 AND owner = $2`, id, owner)
	a, err := scanAlert(row)
	if errors.Is(err, pgx.ErrNoRows) {
		return Alert{}, ErrNotFound
	}
	if err != nil {
		return Alert{}, fmt.Errorf("get alert: %w", err)
	}
	return a, nil
}

// Delete removes an alert scoped to owner. Returns ErrNotFound if absent.
func (s *Store) Delete(ctx context.Context, id, owner string) error {
	tag, err := s.pool.Exec(ctx, `DELETE FROM arbitrage_alerts WHERE id = $1 AND owner = $2`, id, owner)
	if err != nil {
		return fmt.Errorf("delete alert: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

// ListActive returns all active alert definitions (used by the evaluator).
func (s *Store) ListActive(ctx context.Context) ([]Alert, error) {
	rows, err := s.pool.Query(ctx, `SELECT `+selectCols+`
        FROM arbitrage_alerts WHERE active = TRUE`)
	if err != nil {
		return nil, fmt.Errorf("list active alerts: %w", err)
	}
	defer rows.Close()

	var out []Alert
	for rows.Next() {
		a, err := scanAlert(rows)
		if err != nil {
			return nil, fmt.Errorf("scan active alert: %w", err)
		}
		out = append(out, a)
	}
	return out, rows.Err()
}
