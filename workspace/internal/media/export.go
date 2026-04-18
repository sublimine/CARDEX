package media

import (
	"context"
	"fmt"
)

// ExportForPlatform returns the photos for a vehicle ready for syndication on
// the given platform. It applies the platform's max-count and max-size limits.
// Photos are sourced from the web variant (largest available ≤ size limit).
func ExportForPlatform(
	ctx context.Context,
	storage MediaStorage,
	tenantID, vehicleID string,
	platform ExportPlatform,
) ([]ExportedPhoto, error) {
	photos, err := storage.ListPhotos(ctx, tenantID, vehicleID)
	if err != nil {
		return nil, fmt.Errorf("export %s list photos: %w", platform.Name, err)
	}

	// Trim to the platform's maximum.
	if len(photos) > platform.MaxCount {
		photos = photos[:platform.MaxCount]
	}

	out := make([]ExportedPhoto, 0, len(photos))
	for _, p := range photos {
		variants, err := storage.ListVariants(ctx, p.ID)
		if err != nil {
			return nil, fmt.Errorf("export %s list variants for %s: %w", platform.Name, p.ID, err)
		}

		chosen := pickVariant(variants, platform)
		if chosen == nil {
			continue
		}
		out = append(out, ExportedPhoto{
			PhotoID:  p.ID,
			FilePath: chosen.FilePath,
			URL:      chosen.URL,
			Width:    chosen.Width,
			Height:   chosen.Height,
			SizeKB:   int(chosen.SizeBytes / 1024),
		})
	}
	return out, nil
}

// pickVariant selects the best variant for the given platform constraints.
// Preference: web variant if within size limit, else original, else thumbnail.
func pickVariant(variants []*PhotoVariant, platform ExportPlatform) *PhotoVariant {
	var byKind = map[VariantKind]*PhotoVariant{}
	for _, v := range variants {
		byKind[v.Kind] = v
	}

	maxBytes := int64(platform.MaxSizeKB) * 1024
	for _, kind := range []VariantKind{VariantWeb, VariantOriginal, VariantThumbnail} {
		v, ok := byKind[kind]
		if !ok {
			continue
		}
		if maxBytes > 0 && v.SizeBytes > maxBytes {
			continue
		}
		return v
	}
	return nil
}

// ExportMobileDe is a convenience wrapper for mobile.de (max 30, 5 MB JPEG).
func ExportMobileDe(ctx context.Context, s MediaStorage, tenantID, vehicleID string) ([]ExportedPhoto, error) {
	return ExportForPlatform(ctx, s, tenantID, vehicleID, PlatformMobileDe)
}

// ExportAutoScout24 is a convenience wrapper for AutoScout24 (max 50, 10 MB JPEG).
func ExportAutoScout24(ctx context.Context, s MediaStorage, tenantID, vehicleID string) ([]ExportedPhoto, error) {
	return ExportForPlatform(ctx, s, tenantID, vehicleID, PlatformAutoScout24)
}

// ExportLeboncoin is a convenience wrapper for leboncoin (max 10, 5 MB JPEG).
func ExportLeboncoin(ctx context.Context, s MediaStorage, tenantID, vehicleID string) ([]ExportedPhoto, error) {
	return ExportForPlatform(ctx, s, tenantID, vehicleID, PlatformLeboncoin)
}
