package syndication

import (
	"context"
	"fmt"
	"time"
)

// Platform is the interface every syndication adapter must implement.
type Platform interface {
	Name() string
	SupportedCountries() []string
	Publish(ctx context.Context, listing PlatformListing) (externalID string, externalURL string, err error)
	Update(ctx context.Context, externalID string, listing PlatformListing) error
	Withdraw(ctx context.Context, externalID string) error
	Status(ctx context.Context, externalID string) (PlatformStatus, error)
	ValidateListing(listing PlatformListing) []ValidationError
}

// PlatformListing is the normalised listing sent to any platform adapter.
type PlatformListing struct {
	VehicleID    string
	VIN          string
	Make         string
	Model        string
	Variant      string
	Year         int
	MileageKM    int
	FuelType     string
	Transmission string
	PowerKW      int
	Color        string
	BodyType     string
	Price        int64    // cents
	Currency     string
	Description  string   // in the platform's language
	Features     []string
	PhotoURLs    []string // max per-platform limits apply
	DealerName   string
	DealerCountry string
	DealerVATID  string
	ContactEmail string
	ContactPhone string
}

// PlatformStatus represents the last-known publication state on a platform.
type PlatformStatus struct {
	ExternalID  string
	ExternalURL string
	State       string    // "active", "withdrawn", "pending", "error"
	UpdatedAt   time.Time
	Raw         string    // platform-specific status payload (JSON/XML)
}

// ValidationError is a pre-publish validation failure.
type ValidationError struct {
	Field   string
	Message string
}

func (e ValidationError) Error() string {
	return fmt.Sprintf("field %q: %s", e.Field, e.Message)
}

// SyndicationResult records the outcome of a single publish/withdraw operation.
type SyndicationResult struct {
	Platform    string
	ExternalID  string
	ExternalURL string
	Status      string // "published", "withdrawn", "error", "skipped"
	Error       error
}

// ── Platform registry ─────────────────────────────────────────────────────────

var registeredPlatforms = map[string]Platform{}

// Register adds a platform to the global registry. Called from init() in each adapter.
func Register(p Platform) {
	registeredPlatforms[p.Name()] = p
}

// Registered returns all registered platforms.
func Registered() map[string]Platform {
	out := make(map[string]Platform, len(registeredPlatforms))
	for k, v := range registeredPlatforms {
		out[k] = v
	}
	return out
}

// Get returns a platform by name or nil.
func Get(name string) Platform {
	return registeredPlatforms[name]
}
