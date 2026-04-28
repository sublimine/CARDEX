# CARDEX Photo Pipeline — Sprint 42

## Overview

The Photo Pipeline provides server-side image processing for vehicle listings:
HEIC/JPEG/PNG/WebP uploads are decoded, EXIF-stripped, resized, and stored in
three variants (original, web, thumbnail). Watermarking and bulk upload
with controlled concurrency are included. Platform-specific export adapters
serve the variants to mobile.de, AutoScout24, and leboncoin.

**Package:** `cardex.eu/workspace/internal/media`
**Service port:** consumed by workspace-service (no dedicated port)
**Branch:** `sprint/42-photo-pipeline`

---

## Components

| File | Responsibility |
|---|---|
| `types.go` | Domain types: VariantKind, Photo, PhotoVariant, ExportPlatform, BulkInput/Result |
| `errors.go` | Sentinel errors: ErrFileTooLarge, ErrUnsupportedFormat |
| `metrics.go` | Prometheus: uploads_total, processing_duration_seconds, storage_bytes_total |
| `processor.go` | Decode → resize → encode → 3 variants |
| `storage.go` | MediaStorage interface + FSStorage (SQLite + filesystem) |
| `watermark.go` | Dealer logo overlay (web variant only, 40% opacity default) |
| `bulk.go` | BulkUploader: up to 30 photos, semaphore(4) goroutines |
| `reorder.go` | Atomic sort_order update + HTTP handler |
| `export.go` | Platform-specific photo export (mobile.de / AutoScout24 / leboncoin) |

---

## Variant Specifications

| Variant | Max dimensions | Quality | Max size | Format |
|---|---|---|---|---|
| `original` | 2048×2048 px | JPEG q92 | unlimited | JPEG |
| `web` | 1024×1024 px | JPEG q85 → auto-reduce | 800 KB | JPEG |
| `thumbnail` | 400×300 px (cropped) | JPEG q75 | — | JPEG |

> WebP output is a TODO pending a pure-Go WebP encoder (`golang.org/x/image`
> provides only a WebP decoder; CGo-based `chai2010/webp` is excluded to keep
> the pure-Go dependency policy).

---

## EXIF Stripping

`imaging.Decode(r, imaging.AutoOrientation(true))` applies any EXIF rotation
tag before stripping. Re-encoding via `jpeg.Encode` produces a clean JPEG
without APP1/EXIF markers, satisfying GPS and device-info privacy requirements.

---

## Storage Layout

```
{baseDir}/
  {tenantID}/
    {vehicleID}/
      {photoID}_original.jpg
      {photoID}_web.jpg
      {photoID}_thumbnail.jpg
```

SQLite tables (workspace shared DB, `crm_` prefix):

```sql
crm_media_photos   -- one row per upload
crm_media_variants -- one row per variant (3 per photo)
```

---

## Watermark

- Dealer logo loaded from a file path at startup.
- Scaled to ≤25% of image width, placed in the bottom-right corner with 16 px padding.
- Applied only to the `web` variant during bulk upload.
- If no logo file is configured, watermarking is silently skipped.

---

## Bulk Upload Concurrency

```
sem := make(chan struct{}, 4)   // max 4 goroutines
```

The first successfully processed photo is atomically marked as `is_primary`.
Sort order is assigned by the caller (reorder endpoint) after upload.

---

## Platform Export Limits

| Platform | Max photos | Max file size |
|---|---|---|
| mobile.de | 30 | 5 MB |
| AutoScout24 | 50 | 10 MB |
| leboncoin | 10 | 5 MB |

`ExportForPlatform` automatically selects the best-fitting variant for each
platform constraint (web → original → thumbnail, first within size limit).

---

## Reorder Endpoint

`PUT /api/v1/vehicles/{vehicleID}/media/reorder`

Body: `{"photo_ids": ["id1", "id2", ...]}`

Sets `sort_order = 0, 1, 2, …` atomically in a single SQLite transaction.
Requires `X-Tenant-ID` header.

---

## Prometheus Metrics

| Metric | Labels | Type |
|---|---|---|
| `workspace_media_uploads_total` | `tenant_id`, `status` | Counter |
| `workspace_media_processing_duration_seconds` | `variant` | Histogram |
| `workspace_media_storage_bytes_total` | `variant` | Counter |

---

## Dependencies Added

| Package | Version | Purpose |
|---|---|---|
| `github.com/disintegration/imaging` | v1.6.2 | Resize, decode, EXIF auto-orient |
| `github.com/jdeng/goheif` | latest | Pure-Go HEIC decode |
| `golang.org/x/image` | v0.38.0 | Upgraded from v0.12.0 (CVE fix) |

---

## Test Coverage

| Test | What it verifies |
|---|---|
| TestDetectedFormatJPEG/PNG/WebP/Unknown | Magic byte detection |
| TestProcessJPEGProducesThreeVariants | All 3 variants produced |
| TestProcessPNGProducesThreeVariants | PNG input supported |
| TestProcessOriginalDimensionsCapped | max 2048 px enforced |
| TestProcessWebDimensionsCapped | max 1024 px enforced |
| TestProcessThumbnailDimensions | 400×300 px exact |
| TestProcessSmallImageNotUpscaled | no enlargement for small inputs |
| TestProcessOutputIsJPEG | JPEG magic bytes on all variants |
| TestProcessEXIFStripped | APP1 marker absent in output |
| TestProcessEmptyDataError | error on nil input |
| TestSaveAndGetPhoto | SQLite round-trip |
| TestListPhotosOrderedBySortOrder | ORDER BY sort_order |
| TestUpdateSortOrders | atomic reorder transaction |
| TestWriteFile | filesystem path structure |
| TestWatermarkNilPassthrough | nil watermarker is safe |
| TestWatermarkApplyChangesImage | logo compositing produces same-size result |
| TestReorderHandlerMissingTenantID | 400 on missing header |
| TestReorderHandlerWrongMethod | 405 on GET |
| TestVehicleIDFromPath | URL path extraction |
| TestPickVariantRespectsMaxSize | size constraint honoured |
| TestPickVariantPrefersWeb | web variant preferred |
| TestExportPlatformMaxCount | platform limits correct |

Total: **24 tests**, all pass under `-race`.
govulncheck: **No vulnerabilities found.**

---

## Constraints

- Do NOT touch `model/`, `storage/`, `handler/` (Sprint 40).
- Do NOT touch `syndication/` (Sprint 41).
- Pure-Go only — no CGo, no libwebp.
