// Package v16_photo_phash implements validation strategy V16 — Photo Perceptual Hash Deduplication.
//
// # Strategy
//
// Duplicate or near-duplicate photos across different vehicle listings are a strong
// signal of fraudulent re-listing, VIN swapping, or copy-paste dealer entries.
//
// For each photo URL in the vehicle listing this validator:
//  1. Downloads the image via HTTP GET.
//  2. Computes a 64-bit perceptual hash (pHash) using DCT of a 32×32 greyscale downsample.
//  3. Queries the HashStore for any previously indexed photo with Hamming distance ≤ 4.
//  4. If a duplicate is found from a different vehicle → WARNING.
//  5. Stores the computed hash for future comparisons.
//
// Hamming distance ≤ 4 (out of 64 bits) is the duplicate threshold — identical or
// near-identical photos score ≤ 4 different bits after typical JPEG recompression.
//
// # Dependency injection
//
// HashStore abstracts the SQLite pHash index. Use New() / NewWithClient() for a no-op
// store (safe for unit tests); use NewWithStore() to inject the real SQLite backend.
package v16_photo_phash

import (
	"context"
	"fmt"
	"image"
	_ "image/gif"
	_ "image/jpeg"
	_ "image/png"
	"math/bits"
	"net/http"
	"strings"
	"time"

	"github.com/corona10/goimagehash"

	"cardex.eu/quality/internal/pipeline"
)

const (
	strategyID = "V16"
	strategyName = "Photo pHash Deduplication"

	maxDist        = 4 // Hamming distance threshold for near-duplicate detection
	defaultTimeout = 10 * time.Second
)

// HashStore abstracts lookup and storage of perceptual hashes.
type HashStore interface {
	// FindSimilar returns vehicle IDs that have a stored photo hash within maxDistance
	// Hamming bits of hash, excluding excludeVehicleID (the current vehicle).
	FindSimilar(ctx context.Context, hash uint64, maxDistance int, excludeVehicleID string) ([]string, error)
	// StoreHash persists a computed pHash for (vehicleID, photoURL).
	StoreHash(ctx context.Context, vehicleID, photoURL string, hash uint64) error
}

// noopHashStore never finds duplicates and silently discards stored hashes.
type noopHashStore struct{}

func (n *noopHashStore) FindSimilar(_ context.Context, _ uint64, _ int, _ string) ([]string, error) {
	return nil, nil
}
func (n *noopHashStore) StoreHash(_ context.Context, _, _ string, _ uint64) error { return nil }

// PhotoPHash implements pipeline.Validator for V16.
type PhotoPHash struct {
	client *http.Client
	store  HashStore
}

// New returns a PhotoPHash validator backed by a no-op store and a default HTTP client.
func New() *PhotoPHash {
	return NewWithStore(&http.Client{Timeout: defaultTimeout}, &noopHashStore{})
}

// NewWithClient returns a PhotoPHash validator using the given HTTP client and no-op store.
func NewWithClient(client *http.Client) *PhotoPHash {
	return NewWithStore(client, &noopHashStore{})
}

// NewWithStore returns a PhotoPHash validator with the given HTTP client and hash store.
func NewWithStore(client *http.Client, store HashStore) *PhotoPHash {
	return &PhotoPHash{client: client, store: store}
}

func (v *PhotoPHash) ID() string                  { return strategyID }
func (v *PhotoPHash) Name() string                { return strategyName }
func (v *PhotoPHash) Severity() pipeline.Severity { return pipeline.SeverityWarning }

// Validate checks for near-duplicate photos using perceptual hashing.
func (v *PhotoPHash) Validate(ctx context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error) {
	result := &pipeline.ValidationResult{
		ValidatorID: strategyID,
		VehicleID:   vehicle.InternalID,
		Severity:    pipeline.SeverityInfo,
		Suggested:   make(map[string]string),
		Evidence:    make(map[string]string),
	}

	if len(vehicle.PhotoURLs) == 0 {
		result.Pass = true
		result.Issue = "no photos to hash-check (V06 handles photo count)"
		result.Confidence = 1.0
		return result, nil
	}

	var duplicateMatches []string
	var processed int

	for i, photoURL := range vehicle.PhotoURLs {
		if photoURL == "" {
			continue
		}

		hash, err := v.computePHash(ctx, photoURL)
		if err != nil {
			// soft-fail per photo — network or decode error does not block the pipeline
			result.Evidence[fmt.Sprintf("fetch_error_%d", i)] = err.Error()
			continue
		}
		processed++

		// Store this hash (best-effort, ignore errors).
		_ = v.store.StoreHash(ctx, vehicle.InternalID, photoURL, hash)

		// Check for duplicates from other vehicles.
		matches, err := v.store.FindSimilar(ctx, hash, maxDist, vehicle.InternalID)
		if err != nil {
			result.Evidence["store_error"] = err.Error()
			continue
		}
		duplicateMatches = append(duplicateMatches, matches...)
	}

	result.Evidence["photos_checked"] = fmt.Sprintf("%d", processed)

	if len(duplicateMatches) == 0 {
		result.Pass = true
		result.Confidence = 0.95
		return result, nil
	}

	// Deduplicate matched vehicle IDs.
	seen := make(map[string]struct{})
	var unique []string
	for _, m := range duplicateMatches {
		if _, ok := seen[m]; !ok {
			seen[m] = struct{}{}
			unique = append(unique, m)
		}
	}

	result.Pass = false
	result.Severity = pipeline.SeverityWarning
	result.Issue = fmt.Sprintf("near-duplicate photos found in %d other vehicle(s): %s",
		len(unique), strings.Join(unique, ", "))
	result.Confidence = 0.9
	result.Evidence["duplicate_vehicle_ids"] = strings.Join(unique, " | ")
	result.Suggested["action"] = "verify this is not a fraudulent re-listing or VIN swap"
	return result, nil
}

// computePHash downloads the image at url and returns its 64-bit perceptual hash.
func (v *PhotoPHash) computePHash(ctx context.Context, url string) (uint64, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return 0, fmt.Errorf("build request: %w", err)
	}

	resp, err := v.client.Do(req)
	if err != nil {
		return 0, fmt.Errorf("fetch %s: %w", url, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return 0, fmt.Errorf("HTTP %d for %s", resp.StatusCode, url)
	}

	img, _, err := image.Decode(resp.Body)
	if err != nil {
		return 0, fmt.Errorf("decode image %s: %w", url, err)
	}

	h, err := goimagehash.PerceptionHash(img)
	if err != nil {
		return 0, fmt.Errorf("phash %s: %w", url, err)
	}
	return h.GetHash(), nil
}

// HammingDistance returns the number of differing bits between two 64-bit hashes.
func HammingDistance(a, b uint64) int {
	return bits.OnesCount64(a ^ b)
}
