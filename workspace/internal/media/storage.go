package media

import (
	"context"
	"crypto/rand"
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"time"

	_ "modernc.org/sqlite"
)

// ── Interface ─────────────────────────────────────────────────────────────────

// MediaStorage persists photos and their variants.
type MediaStorage interface {
	// SavePhoto persists a Photo record. ID must be pre-set by caller.
	SavePhoto(ctx context.Context, p *Photo) error
	// SaveVariant persists a PhotoVariant record.
	SaveVariant(ctx context.Context, v *PhotoVariant) error
	// WriteFile writes variant bytes to the underlying filesystem/object store.
	// Returns the stored file path.
	WriteFile(tenantID, vehicleID, photoID string, kind VariantKind, data []byte) (string, error)
	// GetPhoto returns a photo by ID scoped to a tenant.
	GetPhoto(ctx context.Context, tenantID, photoID string) (*Photo, error)
	// ListPhotos returns all photos for a vehicle, ordered by sort_order.
	ListPhotos(ctx context.Context, tenantID, vehicleID string) ([]*Photo, error)
	// ListVariants returns all variants for a photo.
	ListVariants(ctx context.Context, photoID string) ([]*PhotoVariant, error)
	// UpdateSortOrders atomically updates sort_order for a slice of photo IDs.
	UpdateSortOrders(ctx context.Context, tenantID string, ordered []string) error
	// DeletePhoto removes the photo record and all its variants.
	DeletePhoto(ctx context.Context, tenantID, photoID string) error
}

// ── Filesystem + SQLite implementation ───────────────────────────────────────

const schema = `
CREATE TABLE IF NOT EXISTS crm_media_photos (
  id          TEXT PRIMARY KEY,
  tenant_id   TEXT NOT NULL,
  vehicle_id  TEXT NOT NULL,
  sort_order  INTEGER NOT NULL DEFAULT 0,
  is_primary  INTEGER NOT NULL DEFAULT 0,
  file_name   TEXT NOT NULL,
  mime_type   TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_media_photos_vehicle ON crm_media_photos(tenant_id, vehicle_id, sort_order);

CREATE TABLE IF NOT EXISTS crm_media_variants (
  id          TEXT PRIMARY KEY,
  photo_id    TEXT NOT NULL REFERENCES crm_media_photos(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL,
  file_path   TEXT NOT NULL,
  width       INTEGER NOT NULL DEFAULT 0,
  height      INTEGER NOT NULL DEFAULT 0,
  size_bytes  INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_media_variants_photo ON crm_media_variants(photo_id);
`

// FSStorage implements MediaStorage using the local filesystem and an SQLite DB.
type FSStorage struct {
	db      *sql.DB
	baseDir string // root directory for stored files
}

// NewFSStorage opens (or creates) the SQLite database at dbPath and uses
// baseDir as the root for media files.
func NewFSStorage(dbPath, baseDir string) (*FSStorage, error) {
	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return nil, fmt.Errorf("media storage open db: %w", err)
	}
	if _, err := db.Exec(schema); err != nil {
		return nil, fmt.Errorf("media storage create schema: %w", err)
	}
	if err := os.MkdirAll(baseDir, 0o755); err != nil {
		return nil, fmt.Errorf("media storage mkdir: %w", err)
	}
	return &FSStorage{db: db, baseDir: baseDir}, nil
}

// Close releases the underlying database connection.
func (s *FSStorage) Close() error { return s.db.Close() }

func (s *FSStorage) SavePhoto(ctx context.Context, p *Photo) error {
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO crm_media_photos
		  (id, tenant_id, vehicle_id, sort_order, is_primary, file_name, mime_type, created_at, updated_at)
		VALUES (?,?,?,?,?,?,?,?,?)
		ON CONFLICT(id) DO UPDATE SET
		  sort_order=excluded.sort_order,
		  is_primary=excluded.is_primary,
		  updated_at=excluded.updated_at`,
		p.ID, p.TenantID, p.VehicleID, p.SortOrder, boolInt(p.IsPrimary),
		p.FileName, p.MimeType, p.CreatedAt.UTC().Format(time.RFC3339), p.UpdatedAt.UTC().Format(time.RFC3339),
	)
	return err
}

func (s *FSStorage) SaveVariant(ctx context.Context, v *PhotoVariant) error {
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO crm_media_variants
		  (id, photo_id, kind, file_path, width, height, size_bytes, created_at)
		VALUES (?,?,?,?,?,?,?,?)
		ON CONFLICT(id) DO NOTHING`,
		v.ID, v.PhotoID, string(v.Kind), v.FilePath,
		v.Width, v.Height, v.SizeBytes, v.CreatedAt.UTC().Format(time.RFC3339),
	)
	return err
}

// WriteFile stores variant bytes at {baseDir}/{tenantID}/{vehicleID}/{photoID}_{kind}.jpg
// and returns the relative path.
func (s *FSStorage) WriteFile(tenantID, vehicleID, photoID string, kind VariantKind, data []byte) (string, error) {
	dir := filepath.Join(s.baseDir, tenantID, vehicleID)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return "", fmt.Errorf("media mkdir: %w", err)
	}
	rel := filepath.Join(tenantID, vehicleID, fmt.Sprintf("%s_%s.jpg", photoID, kind))
	full := filepath.Join(s.baseDir, rel)
	if err := os.WriteFile(full, data, 0o644); err != nil {
		return "", fmt.Errorf("media write file: %w", err)
	}
	return rel, nil
}

func (s *FSStorage) GetPhoto(ctx context.Context, tenantID, photoID string) (*Photo, error) {
	row := s.db.QueryRowContext(ctx, `
		SELECT id, tenant_id, vehicle_id, sort_order, is_primary, file_name, mime_type, created_at, updated_at
		FROM crm_media_photos WHERE id=? AND tenant_id=?`, photoID, tenantID)
	return scanPhoto(row)
}

func (s *FSStorage) ListPhotos(ctx context.Context, tenantID, vehicleID string) ([]*Photo, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT id, tenant_id, vehicle_id, sort_order, is_primary, file_name, mime_type, created_at, updated_at
		FROM crm_media_photos
		WHERE tenant_id=? AND vehicle_id=?
		ORDER BY sort_order ASC, created_at ASC`, tenantID, vehicleID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []*Photo
	for rows.Next() {
		p, err := scanPhoto(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, p)
	}
	return out, rows.Err()
}

func (s *FSStorage) ListVariants(ctx context.Context, photoID string) ([]*PhotoVariant, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT id, photo_id, kind, file_path, width, height, size_bytes, created_at
		FROM crm_media_variants WHERE photo_id=? ORDER BY kind`, photoID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []*PhotoVariant
	for rows.Next() {
		v := &PhotoVariant{}
		var createdAt string
		var kind string
		if err := rows.Scan(&v.ID, &v.PhotoID, &kind, &v.FilePath,
			&v.Width, &v.Height, &v.SizeBytes, &createdAt); err != nil {
			return nil, err
		}
		v.Kind = VariantKind(kind)
		v.CreatedAt, _ = time.Parse(time.RFC3339, createdAt)
		out = append(out, v)
	}
	return out, rows.Err()
}

// UpdateSortOrders sets sort_order=0,1,2,... in the order of the provided
// photo IDs, atomically within a single transaction.
func (s *FSStorage) UpdateSortOrders(ctx context.Context, tenantID string, ordered []string) error {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback() //nolint:errcheck
	stmt, err := tx.PrepareContext(ctx, `UPDATE crm_media_photos SET sort_order=?, updated_at=? WHERE id=? AND tenant_id=?`)
	if err != nil {
		return err
	}
	defer stmt.Close()
	now := time.Now().UTC().Format(time.RFC3339)
	for i, id := range ordered {
		if _, err := stmt.ExecContext(ctx, i, now, id, tenantID); err != nil {
			return err
		}
	}
	return tx.Commit()
}

func (s *FSStorage) DeletePhoto(ctx context.Context, tenantID, photoID string) error {
	_, err := s.db.ExecContext(ctx,
		`DELETE FROM crm_media_photos WHERE id=? AND tenant_id=?`, photoID, tenantID)
	return err
}

// ── helpers ───────────────────────────────────────────────────────────────────

type scanner interface {
	Scan(dest ...any) error
}

func scanPhoto(s scanner) (*Photo, error) {
	p := &Photo{}
	var createdAt, updatedAt string
	var isPrimary int
	if err := s.Scan(&p.ID, &p.TenantID, &p.VehicleID, &p.SortOrder, &isPrimary,
		&p.FileName, &p.MimeType, &createdAt, &updatedAt); err != nil {
		if err == sql.ErrNoRows {
			return nil, ErrPhotoNotFound
		}
		return nil, err
	}
	p.IsPrimary = isPrimary == 1
	p.CreatedAt, _ = time.Parse(time.RFC3339, createdAt)
	p.UpdatedAt, _ = time.Parse(time.RFC3339, updatedAt)
	return p, nil
}

func boolInt(b bool) int {
	if b {
		return 1
	}
	return 0
}

func newMediaID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}
