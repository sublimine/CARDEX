package media

import "time"

// VariantKind identifies the three output variants produced per photo.
type VariantKind string

const (
	VariantOriginal  VariantKind = "original"  // resized to max 2048px, full quality
	VariantWeb       VariantKind = "web"        // max 1024px, JPEG q85, max 800 KB
	VariantThumbnail VariantKind = "thumbnail"  // 400×300 px, JPEG q75
)

// AllVariants is the ordered list of variants generated for every upload.
var AllVariants = []VariantKind{VariantOriginal, VariantWeb, VariantThumbnail}

// ProcessedVariant is the in-memory result of encoding a single variant.
type ProcessedVariant struct {
	Kind    VariantKind
	Data    []byte
	Width   int
	Height  int
	SizeKB  int
}

// Photo is the canonical photo record persisted in the database.
type Photo struct {
	ID          string    `json:"id"`
	TenantID    string    `json:"tenant_id"`
	VehicleID   string    `json:"vehicle_id"`
	SortOrder   int       `json:"sort_order"`
	IsPrimary   bool      `json:"is_primary"`
	FileName    string    `json:"file_name"`
	MimeType    string    `json:"mime_type"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

// PhotoVariant is a stored output variant linked to a Photo.
type PhotoVariant struct {
	ID        string      `json:"id"`
	PhotoID   string      `json:"photo_id"`
	Kind      VariantKind `json:"kind"`
	FilePath  string      `json:"file_path"`
	URL       string      `json:"url,omitempty"`
	Width     int         `json:"width"`
	Height    int         `json:"height"`
	SizeBytes int64       `json:"size_bytes"`
	CreatedAt time.Time   `json:"created_at"`
}

// ExportedPhoto represents a single photo prepared for a syndication platform.
type ExportedPhoto struct {
	PhotoID  string
	FilePath string
	URL      string
	Width    int
	Height   int
	SizeKB   int
}

// ExportPlatform configures per-platform export constraints.
type ExportPlatform struct {
	Name     string
	MaxCount int
	MaxSizeKB int
	Format   string // "jpeg" | "webp"
}

var (
	PlatformMobileDe    = ExportPlatform{Name: "mobile.de",    MaxCount: 30, MaxSizeKB: 5120,  Format: "jpeg"}
	PlatformAutoScout24 = ExportPlatform{Name: "autoscout24",  MaxCount: 50, MaxSizeKB: 10240, Format: "jpeg"}
	PlatformLeboncoin   = ExportPlatform{Name: "leboncoin",    MaxCount: 10, MaxSizeKB: 5120,  Format: "jpeg"}
)

// BulkInput holds one raw file submission in a batch upload.
type BulkInput struct {
	FileName string
	Data     []byte
	MimeType string
}

// BulkResult summarises the outcome of processing one photo in a bulk upload.
type BulkResult struct {
	FileName  string
	PhotoID   string
	IsPrimary bool
	Err       error
}
