package matraba

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// Dataset identifies which of the three DGT monthly dumps to target.
// They share the same fixed-width layout; only the URL path differs.
type Dataset string

const (
	DatasetMatraba Dataset = "matraba" // matriculaciones (new registrations)
	DatasetTransfe Dataset = "transfe" // transferencias (ownership changes)
	DatasetBajas   Dataset = "bajas"   // bajas (deregistrations)
)

// BaseURL is the root of the DGT microdata distribution. Each dataset
// slots into a canonical pattern under it. No authentication required.
const BaseURL = "https://www.dgt.es/microdatos/salida"

// FileURL builds the public URL for a given dataset + (year, month).
// Example: FileURL(DatasetMatraba, 2024, 12) →
//
//	https://www.dgt.es/microdatos/salida/2024/12/vehiculos/matriculaciones/export_mensual_mat_202412.zip
//
// The inner folder and filename prefix differ per dataset:
//
//	matraba → .../matriculaciones/export_mensual_mat_YYYYMM.zip
//	transfe → .../transferencias/export_mensual_tra_YYYYMM.zip
//	bajas   → .../bajas/export_mensual_baj_YYYYMM.zip
func FileURL(ds Dataset, year, month int) string {
	var folder, prefix string
	switch ds {
	case DatasetMatraba:
		folder, prefix = "matriculaciones", "mat"
	case DatasetTransfe:
		folder, prefix = "transferencias", "tra"
	case DatasetBajas:
		folder, prefix = "bajas", "baj"
	default:
		folder, prefix = string(ds), string(ds)
	}
	return fmt.Sprintf("%s/%d/%d/vehiculos/%s/export_mensual_%s_%04d%02d.zip",
		BaseURL, year, month, folder, prefix, year, month)
}

// Downloader fetches DGT monthly ZIPs. It owns an *http.Client so the
// caller can wire custom timeouts, transports, or mocked round-trippers
// in tests.
type Downloader struct {
	Client    *http.Client
	UserAgent string
	// BaseOverride, if non-empty, replaces BaseURL. Used in tests so
	// FileURL() can be redirected at an httptest.Server.
	BaseOverride string
}

// NewDownloader returns a Downloader with a 5-minute HTTP timeout. The
// DGT origin is slow when streaming 300-500 MB ZIPs; 5 min is the
// compromise between "long enough for monthly dumps" and "short enough
// to surface a genuinely dead endpoint quickly".
func NewDownloader() *Downloader {
	return &Downloader{
		Client:    &http.Client{Timeout: 5 * time.Minute},
		UserAgent: "cardex-matraba-importer/1.0 (+https://cardex.eu)",
	}
}

// URLFor is FileURL(...) with the downloader's BaseOverride applied.
func (d *Downloader) URLFor(ds Dataset, year, month int) string {
	u := FileURL(ds, year, month)
	if d.BaseOverride != "" {
		u = strings.Replace(u, BaseURL, strings.TrimRight(d.BaseOverride, "/"), 1)
	}
	return u
}

// ErrNotYetPublished is returned when the origin answers 404. DGT
// publishes monthly dumps ~15-30 days after the month closes, so a 404
// in the first weeks of the following month is expected and NOT a fatal
// error — callers can retry later.
var ErrNotYetPublished = errors.New("matraba: dataset not yet published (HTTP 404)")

// Download streams the monthly ZIP for dataset/(year,month) into the
// given destination directory and returns the absolute path of the
// saved file. If the file already exists, it is returned as-is without
// re-downloading (idempotent for re-runs of the importer).
func (d *Downloader) Download(ctx context.Context, ds Dataset, year, month int, destDir string) (string, error) {
	if err := os.MkdirAll(destDir, 0o755); err != nil {
		return "", fmt.Errorf("matraba mkdir: %w", err)
	}

	u := d.URLFor(ds, year, month)
	fname := filepath.Base(u)
	out := filepath.Join(destDir, fname)

	if info, err := os.Stat(out); err == nil && info.Size() > 0 {
		return out, nil
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return "", fmt.Errorf("matraba build request: %w", err)
	}
	if d.UserAgent != "" {
		req.Header.Set("User-Agent", d.UserAgent)
	}
	req.Header.Set("Accept", "application/zip, */*")

	resp, err := d.Client.Do(req)
	if err != nil {
		return "", fmt.Errorf("matraba download %s: %w", u, err)
	}
	defer resp.Body.Close()

	switch {
	case resp.StatusCode == http.StatusNotFound:
		return "", fmt.Errorf("%w: %s", ErrNotYetPublished, u)
	case resp.StatusCode != http.StatusOK:
		return "", fmt.Errorf("matraba download %s: HTTP %d", u, resp.StatusCode)
	}

	// Stream to a temp file so interrupted downloads don't leave a half-
	// written ZIP that the next run would mistake for a complete file.
	tmp := out + ".part"
	f, err := os.Create(tmp)
	if err != nil {
		return "", fmt.Errorf("matraba create temp: %w", err)
	}
	_, copyErr := io.Copy(f, resp.Body)
	closeErr := f.Close()
	if copyErr != nil {
		_ = os.Remove(tmp)
		return "", fmt.Errorf("matraba copy body: %w", copyErr)
	}
	if closeErr != nil {
		_ = os.Remove(tmp)
		return "", fmt.Errorf("matraba close temp: %w", closeErr)
	}
	if err := os.Rename(tmp, out); err != nil {
		return "", fmt.Errorf("matraba rename temp: %w", err)
	}
	return out, nil
}
