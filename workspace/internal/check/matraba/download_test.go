package matraba

import (
	"archive/zip"
	"bytes"
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
)

func TestFileURLMatchesDGTPattern(t *testing.T) {
	cases := []struct {
		ds    Dataset
		y, m  int
		want  string
	}{
		{DatasetMatraba, 2024, 12,
			"https://www.dgt.es/microdatos/salida/2024/12/vehiculos/matriculaciones/export_mensual_mat_202412.zip"},
		{DatasetTransfe, 2024, 7,
			"https://www.dgt.es/microdatos/salida/2024/7/vehiculos/transferencias/export_mensual_tra_202407.zip"},
		{DatasetBajas, 2023, 1,
			"https://www.dgt.es/microdatos/salida/2023/1/vehiculos/bajas/export_mensual_baj_202301.zip"},
	}
	for _, c := range cases {
		got := FileURL(c.ds, c.y, c.m)
		if got != c.want {
			t.Errorf("FileURL(%s, %d, %d) = %q, want %q", c.ds, c.y, c.m, got, c.want)
		}
	}
}

func TestDownloadFetchesAndCaches(t *testing.T) {
	// Build a real ZIP payload so the downloader sees a complete body.
	row, _ := fullSampleRow(t)
	var zipBuf bytes.Buffer
	zw := zip.NewWriter(&zipBuf)
	mw, _ := zw.Create("export_mensual_mat_202412.txt")
	mw.Write([]byte(row))
	mw.Write([]byte{'\n'})
	zw.Close()

	var hits int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits++
		if !strings.Contains(r.URL.Path, "export_mensual_mat_202412.zip") {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/zip")
		w.Write(zipBuf.Bytes())
	}))
	defer srv.Close()

	dl := NewDownloader()
	dl.BaseOverride = srv.URL + "/microdatos/salida"

	dir := t.TempDir()
	path, err := dl.Download(context.Background(), DatasetMatraba, 2024, 12, dir)
	if err != nil {
		t.Fatalf("download: %v", err)
	}
	if filepath.Base(path) != "export_mensual_mat_202412.zip" {
		t.Errorf("saved file = %s, want export_mensual_mat_202412.zip", path)
	}

	// Second call returns cached file without re-fetching.
	path2, err := dl.Download(context.Background(), DatasetMatraba, 2024, 12, dir)
	if err != nil {
		t.Fatalf("second download: %v", err)
	}
	if path2 != path {
		t.Errorf("cached path differs: %q vs %q", path2, path)
	}
	if hits != 1 {
		t.Errorf("origin hit %d times, want 1 (second call should cache)", hits)
	}
}

func TestDownload404IsSurfacedAsNotYetPublished(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.NotFound(w, r)
	}))
	defer srv.Close()

	dl := NewDownloader()
	dl.BaseOverride = srv.URL + "/microdatos/salida"

	_, err := dl.Download(context.Background(), DatasetMatraba, 2099, 12, t.TempDir())
	if !errors.Is(err, ErrNotYetPublished) {
		t.Errorf("expected ErrNotYetPublished, got %v", err)
	}
}

func TestDownloadServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	dl := NewDownloader()
	dl.BaseOverride = srv.URL + "/microdatos/salida"

	_, err := dl.Download(context.Background(), DatasetMatraba, 2024, 12, t.TempDir())
	if err == nil || errors.Is(err, ErrNotYetPublished) {
		t.Errorf("expected non-404 error, got %v", err)
	}
}

func TestDownloadEndToEndParsesArchive(t *testing.T) {
	// Exercise the full download → ParseZIP pipeline against a mock origin.
	row, _ := fullSampleRow(t)
	var zipBuf bytes.Buffer
	zw := zip.NewWriter(&zipBuf)
	mw, _ := zw.Create("export_mensual_mat_202412.txt")
	for i := 0; i < 5; i++ {
		mw.Write([]byte(row))
		mw.Write([]byte{'\n'})
	}
	zw.Close()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write(zipBuf.Bytes())
	}))
	defer srv.Close()

	dl := NewDownloader()
	dl.BaseOverride = srv.URL + "/microdatos/salida"

	path, err := dl.Download(context.Background(), DatasetMatraba, 2024, 12, t.TempDir())
	if err != nil {
		t.Fatalf("download: %v", err)
	}

	var seen int
	if _, err := ParseZIP(context.Background(), path, func(r Record) error {
		seen++
		return nil
	}); err != nil {
		t.Fatalf("parse: %v", err)
	}
	if seen != 5 {
		t.Errorf("parsed %d rows, want 5", seen)
	}
}
