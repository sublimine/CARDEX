package documents

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// Service orchestrates document generation, storage, and retrieval.
type Service struct {
	db      *sql.DB
	baseDir string // base directory for PDF storage (e.g. "media")
}

// NewService creates a Service and ensures the DB schema exists.
func NewService(ctx context.Context, db *sql.DB, baseDir string) (*Service, error) {
	if err := EnsureSchema(ctx, db); err != nil {
		return nil, err
	}
	return &Service{db: db, baseDir: baseDir}, nil
}

// GenerateContract generates a contract PDF and saves it.
func (s *Service) GenerateContract(ctx context.Context, req ContractRequest) (*GenerateResult, error) {
	data, err := GenerateContract(req)
	if err != nil {
		return nil, err
	}
	return s.persist(ctx, req.TenantID, DocTypeContract, req.VehicleID, "", data)
}

// GenerateInvoice generates an EU invoice PDF and saves it.
func (s *Service) GenerateInvoice(ctx context.Context, req InvoiceRequest) (*GenerateResult, error) {
	data, err := GenerateInvoice(req)
	if err != nil {
		return nil, err
	}
	return s.persist(ctx, req.TenantID, DocTypeInvoice, "", req.DealID, data)
}

// GenerateVehicleSheet generates a vehicle technical sheet PDF and saves it.
func (s *Service) GenerateVehicleSheet(ctx context.Context, req VehicleSheetRequest) (*GenerateResult, error) {
	data, err := GenerateVehicleSheet(req)
	if err != nil {
		return nil, err
	}
	return s.persist(ctx, req.TenantID, DocTypeVehicleSheet, req.VehicleID, "", data)
}

// GenerateTransportDoc generates a transport accompaniment document and saves it.
func (s *Service) GenerateTransportDoc(ctx context.Context, req TransportRequest) (*GenerateResult, error) {
	data, err := GenerateTransportDoc(req)
	if err != nil {
		return nil, err
	}
	return s.persist(ctx, req.TenantID, DocTypeTransportDoc, req.VehicleID, "", data)
}

// GetDocumentFile returns the file path and metadata for a document by ID.
func (s *Service) GetDocumentFile(ctx context.Context, id string) (*Document, error) {
	return GetDocument(ctx, s.db, id)
}

// persist writes PDF bytes to disk and records the document in the DB.
func (s *Service) persist(ctx context.Context, tenantID string, docType DocType, vehicleID, dealID string, data []byte) (*GenerateResult, error) {
	if strings.ContainsAny(tenantID, `/\.`) || tenantID == "" {
		return nil, fmt.Errorf("documents: invalid tenant_id %q", tenantID)
	}
	id := generateID()
	dir := filepath.Join(s.baseDir, tenantID, "documents")
	// Guard: resolved path must still be under baseDir.
	if !strings.HasPrefix(filepath.Clean(dir)+string(filepath.Separator), filepath.Clean(s.baseDir)+string(filepath.Separator)) {
		return nil, fmt.Errorf("documents: path traversal detected")
	}
	if err := os.MkdirAll(dir, 0755); err != nil {
		return nil, fmt.Errorf("documents: mkdir %s: %w", dir, err)
	}

	fileName := fmt.Sprintf("%s_%s.pdf", string(docType), id)
	filePath := filepath.Join(dir, fileName)

	if err := os.WriteFile(filePath, data, 0644); err != nil {
		return nil, fmt.Errorf("documents: write pdf: %w", err)
	}

	doc := &Document{
		ID:        id,
		TenantID:  tenantID,
		Type:      docType,
		VehicleID: vehicleID,
		DealID:    dealID,
		FilePath:  filePath,
		CreatedAt: time.Now().UTC(),
	}
	if err := saveDocument(ctx, s.db, doc); err != nil {
		_ = os.Remove(filePath)
		return nil, err
	}

	return &GenerateResult{
		DocumentID:  id,
		FilePath:    filePath,
		DownloadURL: fmt.Sprintf("/api/v1/documents/%s/download", id),
	}, nil
}

// generateID returns a time-sortable pseudo-unique document ID.
func generateID() string {
	return fmt.Sprintf("%d", time.Now().UnixNano())
}
