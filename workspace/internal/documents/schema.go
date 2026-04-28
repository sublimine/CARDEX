package documents

import (
	"context"
	"database/sql"
	"fmt"
	"time"
)

const documentsSchema = `
CREATE TABLE IF NOT EXISTS crm_documents (
    id          TEXT    PRIMARY KEY,
    tenant_id   TEXT    NOT NULL,
    type        TEXT    NOT NULL,
    vehicle_id  TEXT,
    deal_id     TEXT,
    file_path   TEXT    NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_crm_doc_tenant  ON crm_documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_crm_doc_vehicle ON crm_documents(vehicle_id) WHERE vehicle_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_crm_doc_deal    ON crm_documents(deal_id) WHERE deal_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS crm_invoice_seq (
    tenant_id  TEXT    NOT NULL,
    year       INTEGER NOT NULL,
    last_seq   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, year)
);
`

// EnsureSchema creates the documents tables if they do not exist.
func EnsureSchema(ctx context.Context, db *sql.DB) error {
	if _, err := db.ExecContext(ctx, documentsSchema); err != nil {
		return fmt.Errorf("documents: ensure schema: %w", err)
	}
	return nil
}

// saveDocument persists a Document record to crm_documents.
func saveDocument(ctx context.Context, db *sql.DB, doc *Document) error {
	_, err := db.ExecContext(ctx, `
		INSERT INTO crm_documents (id, tenant_id, type, vehicle_id, deal_id, file_path, created_at)
		VALUES (?, ?, ?, ?, ?, ?, ?)`,
		doc.ID, doc.TenantID, string(doc.Type),
		nullStr(doc.VehicleID), nullStr(doc.DealID),
		doc.FilePath,
		doc.CreatedAt.UTC().Format(time.RFC3339),
	)
	if err != nil {
		return fmt.Errorf("documents: save: %w", err)
	}
	return nil
}

// GetDocument retrieves a document record by ID.
func GetDocument(ctx context.Context, db *sql.DB, id string) (*Document, error) {
	row := db.QueryRowContext(ctx, `
		SELECT id, tenant_id, type, COALESCE(vehicle_id,''), COALESCE(deal_id,''), file_path, created_at
		FROM crm_documents WHERE id = ?`, id)

	var doc Document
	var docType, createdAt string
	if err := row.Scan(&doc.ID, &doc.TenantID, &docType,
		&doc.VehicleID, &doc.DealID, &doc.FilePath, &createdAt); err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("document %q not found", id)
		}
		return nil, fmt.Errorf("documents: get: %w", err)
	}
	doc.Type = DocType(docType)
	doc.CreatedAt, _ = time.Parse(time.RFC3339, createdAt)
	return &doc, nil
}

// NextInvoiceNumber increments and returns the next invoice number for a tenant+year.
// Format: {tenantPrefix}-{year}-{seq:05d}
func NextInvoiceNumber(ctx context.Context, db *sql.DB, tenantID, tenantPrefix string) (string, error) {
	year := time.Now().Year()

	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return "", fmt.Errorf("documents: invoice seq tx: %w", err)
	}
	defer tx.Rollback()

	// Upsert increment.
	if _, err := tx.ExecContext(ctx, `
		INSERT INTO crm_invoice_seq (tenant_id, year, last_seq) VALUES (?, ?, 1)
		ON CONFLICT(tenant_id, year) DO UPDATE SET last_seq = last_seq + 1`,
		tenantID, year,
	); err != nil {
		return "", fmt.Errorf("documents: invoice seq upsert: %w", err)
	}

	var seq int
	if err := tx.QueryRowContext(ctx,
		`SELECT last_seq FROM crm_invoice_seq WHERE tenant_id = ? AND year = ?`,
		tenantID, year,
	).Scan(&seq); err != nil {
		return "", fmt.Errorf("documents: invoice seq read: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return "", fmt.Errorf("documents: invoice seq commit: %w", err)
	}

	return fmt.Sprintf("%s-%d-%05d", tenantPrefix, year, seq), nil
}

func nullStr(s string) any {
	if s == "" {
		return nil
	}
	return s
}
