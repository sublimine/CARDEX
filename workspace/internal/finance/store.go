package finance

import (
	"crypto/rand"
	"database/sql"
	"fmt"
	"time"
)

// Store handles all persistence for financial transactions and exchange rates.
type Store struct {
	db *sql.DB
}

// NewStore returns a Store backed by db.
func NewStore(db *sql.DB) *Store { return &Store{db: db} }

// Create inserts a new transaction and returns the persisted record.
func (s *Store) Create(tenantID, vehicleID string, req CreateTransactionRequest) (*Transaction, error) {
	if !req.Type.Valid() {
		return nil, fmt.Errorf("finance: invalid transaction type %q", req.Type)
	}
	if req.AmountCents <= 0 {
		return nil, fmt.Errorf("finance: amount_cents must be > 0")
	}
	if req.Currency == "" {
		req.Currency = "EUR"
	}
	if req.Date == "" {
		req.Date = time.Now().Format("2006-01-02")
	}

	id := newID()
	now := time.Now().UTC().Format(time.RFC3339)
	_, err := s.db.Exec(`
		INSERT INTO crm_transactions
		    (id, tenant_id, vehicle_id, type, amount_cents, currency,
		     vat_cents, vat_rate, counterparty, reference, date, notes, created_at, updated_at)
		VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
		id, tenantID, vehicleID, string(req.Type),
		req.AmountCents, req.Currency, req.VATCents, req.VATRate,
		req.Counterparty, req.Reference, req.Date, req.Notes,
		now, now,
	)
	if err != nil {
		return nil, fmt.Errorf("finance: create tx: %w", err)
	}
	return s.GetByID(tenantID, id)
}

// GetByID retrieves a transaction by its ID, scoped to tenant.
func (s *Store) GetByID(tenantID, id string) (*Transaction, error) {
	row := s.db.QueryRow(`
		SELECT id, tenant_id, vehicle_id, type, amount_cents, currency,
		       vat_cents, vat_rate, counterparty, reference, date, notes, created_at, updated_at
		FROM crm_transactions WHERE id = ? AND tenant_id = ?`,
		id, tenantID,
	)
	return scanTx(row)
}

// ListByVehicle returns all transactions for a vehicle ordered by date asc.
func (s *Store) ListByVehicle(tenantID, vehicleID string) ([]Transaction, error) {
	rows, err := s.db.Query(`
		SELECT id, tenant_id, vehicle_id, type, amount_cents, currency,
		       vat_cents, vat_rate, counterparty, reference, date, notes, created_at, updated_at
		FROM crm_transactions
		WHERE tenant_id = ? AND vehicle_id = ?
		ORDER BY date ASC, created_at ASC`,
		tenantID, vehicleID,
	)
	if err != nil {
		return nil, fmt.Errorf("finance: list by vehicle: %w", err)
	}
	defer rows.Close()
	return scanTxRows(rows)
}

// Update modifies an existing transaction. Returns not-found error if absent.
func (s *Store) Update(tenantID, id string, req CreateTransactionRequest) (*Transaction, error) {
	if !req.Type.Valid() {
		return nil, fmt.Errorf("finance: invalid transaction type %q", req.Type)
	}
	if req.AmountCents <= 0 {
		return nil, fmt.Errorf("finance: amount_cents must be > 0")
	}
	if req.Currency == "" {
		req.Currency = "EUR"
	}
	now := time.Now().UTC().Format(time.RFC3339)
	res, err := s.db.Exec(`
		UPDATE crm_transactions
		SET type=?, amount_cents=?, currency=?, vat_cents=?, vat_rate=?,
		    counterparty=?, reference=?, date=?, notes=?, updated_at=?
		WHERE id=? AND tenant_id=?`,
		string(req.Type), req.AmountCents, req.Currency, req.VATCents, req.VATRate,
		req.Counterparty, req.Reference, req.Date, req.Notes, now,
		id, tenantID,
	)
	if err != nil {
		return nil, fmt.Errorf("finance: update tx: %w", err)
	}
	n, _ := res.RowsAffected()
	if n == 0 {
		return nil, fmt.Errorf("finance: transaction %q not found", id)
	}
	return s.GetByID(tenantID, id)
}

// Delete removes a transaction by ID (tenant-scoped).
func (s *Store) Delete(tenantID, id string) error {
	res, err := s.db.Exec(`DELETE FROM crm_transactions WHERE id=? AND tenant_id=?`, id, tenantID)
	if err != nil {
		return fmt.Errorf("finance: delete tx: %w", err)
	}
	n, _ := res.RowsAffected()
	if n == 0 {
		return fmt.Errorf("finance: transaction %q not found", id)
	}
	return nil
}

// ListByDateRange returns all tenant transactions where date is in [from, to] (YYYY-MM-DD).
func (s *Store) ListByDateRange(tenantID, from, to string) ([]Transaction, error) {
	rows, err := s.db.Query(`
		SELECT id, tenant_id, vehicle_id, type, amount_cents, currency,
		       vat_cents, vat_rate, counterparty, reference, date, notes, created_at, updated_at
		FROM crm_transactions
		WHERE tenant_id = ? AND date >= ? AND date <= ?
		ORDER BY date ASC, vehicle_id ASC`,
		tenantID, from, to,
	)
	if err != nil {
		return nil, fmt.Errorf("finance: list by date range: %w", err)
	}
	defer rows.Close()
	return scanTxRows(rows)
}

// ListByMonth returns all tenant transactions in the calendar month (year, month 1-12).
func (s *Store) ListByMonth(tenantID string, year, month int) ([]Transaction, error) {
	from := fmt.Sprintf("%04d-%02d-01", year, month)
	ny, nm := year, month+1
	if nm > 12 {
		nm, ny = 1, year+1
	}
	nextMonthStart := fmt.Sprintf("%04d-%02d-01", ny, nm)
	rows, err := s.db.Query(`
		SELECT id, tenant_id, vehicle_id, type, amount_cents, currency,
		       vat_cents, vat_rate, counterparty, reference, date, notes, created_at, updated_at
		FROM crm_transactions
		WHERE tenant_id = ? AND date >= ? AND date < ?
		ORDER BY date ASC`,
		tenantID, from, nextMonthStart,
	)
	if err != nil {
		return nil, fmt.Errorf("finance: list by month: %w", err)
	}
	defer rows.Close()
	return scanTxRows(rows)
}

// GetExchangeRate returns the most recent rate from→"EUR" on or before date.
// Returns 1.0 if currencies match or no rate is configured (graceful fallback).
func (s *Store) GetExchangeRate(fromCurrency, toCurrency, date string) (float64, error) {
	if fromCurrency == toCurrency {
		return 1.0, nil
	}
	var rate float64
	err := s.db.QueryRow(`
		SELECT rate FROM crm_exchange_rates
		WHERE from_currency=? AND to_currency=? AND valid_from<=?
		ORDER BY valid_from DESC LIMIT 1`,
		fromCurrency, toCurrency, date,
	).Scan(&rate)
	if err == sql.ErrNoRows {
		return 1.0, nil
	}
	if err != nil {
		return 0, fmt.Errorf("finance: get exchange rate: %w", err)
	}
	return rate, nil
}

// UpsertExchangeRate inserts or updates an FX rate (idempotent on unique key).
func (s *Store) UpsertExchangeRate(r ExchangeRate) error {
	_, err := s.db.Exec(`
		INSERT INTO crm_exchange_rates (from_currency, to_currency, rate, valid_from)
		VALUES (?,?,?,?)
		ON CONFLICT(from_currency, to_currency, valid_from) DO UPDATE SET rate=excluded.rate`,
		r.FromCurrency, r.ToCurrency, r.Rate, r.ValidFrom,
	)
	if err != nil {
		return fmt.Errorf("finance: upsert rate: %w", err)
	}
	return nil
}

// ── scan helpers ──────────────────────────────────────────────────────────────

type scanner interface{ Scan(dest ...any) error }

func scanTx(row scanner) (*Transaction, error) {
	var tx Transaction
	var typeStr, createdAt, updatedAt string
	err := row.Scan(
		&tx.ID, &tx.TenantID, &tx.VehicleID, &typeStr,
		&tx.AmountCents, &tx.Currency, &tx.VATCents, &tx.VATRate,
		&tx.Counterparty, &tx.Reference, &tx.Date, &tx.Notes,
		&createdAt, &updatedAt,
	)
	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("finance: transaction not found")
	}
	if err != nil {
		return nil, fmt.Errorf("finance: scan tx: %w", err)
	}
	tx.Type = TransactionType(typeStr)
	tx.CreatedAt, _ = time.Parse(time.RFC3339, createdAt)
	tx.UpdatedAt, _ = time.Parse(time.RFC3339, updatedAt)
	return &tx, nil
}

func scanTxRows(rows *sql.Rows) ([]Transaction, error) {
	var out []Transaction
	for rows.Next() {
		var tx Transaction
		var typeStr, createdAt, updatedAt string
		if err := rows.Scan(
			&tx.ID, &tx.TenantID, &tx.VehicleID, &typeStr,
			&tx.AmountCents, &tx.Currency, &tx.VATCents, &tx.VATRate,
			&tx.Counterparty, &tx.Reference, &tx.Date, &tx.Notes,
			&createdAt, &updatedAt,
		); err != nil {
			return nil, fmt.Errorf("finance: scan rows: %w", err)
		}
		tx.Type = TransactionType(typeStr)
		tx.CreatedAt, _ = time.Parse(time.RFC3339, createdAt)
		tx.UpdatedAt, _ = time.Parse(time.RFC3339, updatedAt)
		out = append(out, tx)
	}
	return out, rows.Err()
}

// newID returns a random UUID-like string.
func newID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}
