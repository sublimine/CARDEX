package media

import (
	"context"
	"sync"
	"time"
)

const maxConcurrency = 4

// BulkUploader processes up to 30 photos concurrently (max 4 goroutines) and
// persists each one via the provided MediaStorage.
type BulkUploader struct {
	storage    MediaStorage
	watermark  *Watermarker // may be nil
}

// NewBulkUploader creates a BulkUploader.
func NewBulkUploader(storage MediaStorage, watermark *Watermarker) *BulkUploader {
	return &BulkUploader{storage: storage, watermark: watermark}
}

// Upload processes inputs and stores them under tenantID/vehicleID.
// The first successfully processed photo is marked as primary.
// At most 30 inputs are accepted; extras are silently dropped.
func (u *BulkUploader) Upload(ctx context.Context, tenantID, vehicleID string, inputs []BulkInput) []BulkResult {
	if len(inputs) > 30 {
		inputs = inputs[:30]
	}
	if len(inputs) == 0 {
		return nil
	}

	results := make([]BulkResult, len(inputs))
	sem := make(chan struct{}, maxConcurrency)
	var mu sync.Mutex
	primarySet := false
	var wg sync.WaitGroup

	for i, inp := range inputs {
		i, inp := i, inp
		wg.Add(1)
		sem <- struct{}{}
		go func() {
			defer wg.Done()
			defer func() { <-sem }()

			photoID, isPrimary, err := u.processOne(ctx, tenantID, vehicleID, inp, &mu, &primarySet)
			results[i] = BulkResult{
				FileName:  inp.FileName,
				PhotoID:   photoID,
				IsPrimary: isPrimary,
				Err:       err,
			}
			if err == nil {
				uploadsTotal.WithLabelValues(tenantID, "success").Inc()
			} else {
				uploadsTotal.WithLabelValues(tenantID, "error").Inc()
			}
		}()
	}
	wg.Wait()
	return results
}

func (u *BulkUploader) processOne(
	ctx context.Context,
	tenantID, vehicleID string,
	inp BulkInput,
	mu *sync.Mutex,
	primarySet *bool,
) (string, bool, error) {
	variants, err := Process(inp.Data)
	if err != nil {
		return "", false, err
	}

	// Apply watermark to web variant.
	if u.watermark != nil {
		for _, v := range variants {
			if v.Kind == VariantWeb {
				applyWatermarkToVariant(v, u.watermark)
			}
		}
	}

	photoID := newMediaID()
	now := time.Now().UTC()

	mu.Lock()
	isPrimary := !*primarySet
	if isPrimary {
		*primarySet = true
	}
	mu.Unlock()

	photo := &Photo{
		ID:        photoID,
		TenantID:  tenantID,
		VehicleID: vehicleID,
		SortOrder: 0,
		IsPrimary: isPrimary,
		FileName:  inp.FileName,
		MimeType:  inp.MimeType,
		CreatedAt: now,
		UpdatedAt: now,
	}
	if err := u.storage.SavePhoto(ctx, photo); err != nil {
		return "", false, err
	}

	for _, v := range variants {
		path, err := u.storage.WriteFile(tenantID, vehicleID, photoID, v.Kind, v.Data)
		if err != nil {
			return "", false, err
		}
		pv := &PhotoVariant{
			ID:        newMediaID(),
			PhotoID:   photoID,
			Kind:      v.Kind,
			FilePath:  path,
			Width:     v.Width,
			Height:    v.Height,
			SizeBytes: int64(len(v.Data)),
			CreatedAt: now,
		}
		if err := u.storage.SaveVariant(ctx, pv); err != nil {
			return "", false, err
		}
	}
	return photoID, isPrimary, nil
}

// applyWatermarkToVariant re-encodes the variant data with the watermark applied.
func applyWatermarkToVariant(v *ProcessedVariant, wm *Watermarker) {
	if wm == nil {
		return
	}
	img, err := decodeImage(v.Data, "jpeg")
	if err != nil {
		return
	}
	watermarked := wm.Apply(img)
	encoded, err := encodeJPEG(watermarked, webQuality)
	if err != nil {
		return
	}
	v.Data = encoded
	v.SizeKB = len(encoded) / 1024
}
