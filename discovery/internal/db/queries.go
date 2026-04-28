package db

import (
	"context"
	"database/sql"
	"fmt"
)

// ExecCtx executes a statement within a context, returning an error on failure.
// A thin helper used by kg layer so callers don't repeat error-wrapping boilerplate.
func ExecCtx(ctx context.Context, db *sql.DB, query string, args ...any) error {
	if _, err := db.ExecContext(ctx, query, args...); err != nil {
		return fmt.Errorf("db.ExecCtx: %w", err)
	}
	return nil
}

// QueryRowCtx runs a single-row query and scans dest columns.
// Returns sql.ErrNoRows when nothing matches — callers should check for it explicitly.
func QueryRowCtx(ctx context.Context, db *sql.DB, dest []any, query string, args ...any) error {
	row := db.QueryRowContext(ctx, query, args...)
	return row.Scan(dest...)
}

// InTx executes fn inside a serialised transaction, rolling back on any error.
func InTx(ctx context.Context, db *sql.DB, fn func(tx *sql.Tx) error) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("db.InTx begin: %w", err)
	}
	if err := fn(tx); err != nil {
		_ = tx.Rollback()
		return err
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("db.InTx commit: %w", err)
	}
	return nil
}
