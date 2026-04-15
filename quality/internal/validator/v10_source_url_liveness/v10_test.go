package v10_source_url_liveness_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/validator/v10_source_url_liveness"
)

func vehicle(sourceURL string) *pipeline.Vehicle {
	return &pipeline.Vehicle{InternalID: "T1", SourceURL: sourceURL}
}

// TestV10_200OK verifies that a live 200 response passes.
func TestV10_200OK(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	val := v10_source_url_liveness.NewWithClient(srv.Client(), time.Hour)
	res, err := val.Validate(context.Background(), vehicle(srv.URL+"/listing/123"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for 200 OK, issue: %s", res.Issue)
	}
}

// TestV10_404_Critical verifies that a 404 response produces a CRITICAL failure.
func TestV10_404_Critical(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	val := v10_source_url_liveness.NewWithClient(srv.Client(), time.Hour)
	res, err := val.Validate(context.Background(), vehicle(srv.URL+"/listing/gone"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for 404, got true")
	}
	if res.Severity != pipeline.SeverityCritical {
		t.Errorf("want CRITICAL for 404, got %s", res.Severity)
	}
}

// TestV10_301_Redirect_Info verifies that a 301 redirect passes as INFO.
func TestV10_301_Redirect_Info(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "/new-location", http.StatusMovedPermanently)
	}))
	defer srv.Close()

	// Use a no-follow client (mirrors production behaviour).
	noFollow := &http.Client{
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	val := v10_source_url_liveness.NewWithClient(noFollow, time.Hour)
	res, err := val.Validate(context.Background(), vehicle(srv.URL+"/old-listing"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Errorf("want pass=true for 301 redirect, issue: %s", res.Issue)
	}
	if res.Severity != pipeline.SeverityInfo {
		t.Errorf("want INFO for redirect, got %s", res.Severity)
	}
}

// TestV10_500_Warning verifies that a 500 server error produces a WARNING.
func TestV10_500_Warning(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	val := v10_source_url_liveness.NewWithClient(srv.Client(), time.Hour)
	res, err := val.Validate(context.Background(), vehicle(srv.URL+"/listing/broken"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for 500, got true")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want WARNING for 500, got %s", res.Severity)
	}
}

// TestV10_NetworkError_Warning verifies that a connection refusal produces a WARNING.
func TestV10_NetworkError_Warning(t *testing.T) {
	val := v10_source_url_liveness.NewWithClient(
		&http.Client{Timeout: time.Second},
		time.Hour,
	)
	// Port 1 always refuses connections.
	res, err := val.Validate(context.Background(), vehicle("http://127.0.0.1:1/listing"))
	if err != nil {
		t.Fatalf("unexpected top-level error: %v", err)
	}
	if res.Pass {
		t.Error("want pass=false for network error, got true")
	}
	if res.Severity != pipeline.SeverityWarning {
		t.Errorf("want WARNING for network error, got %s", res.Severity)
	}
}

// TestV10_NoSourceURL_Skip verifies that an empty source URL is an INFO skip.
func TestV10_NoSourceURL_Skip(t *testing.T) {
	val := v10_source_url_liveness.New()
	res, err := val.Validate(context.Background(), vehicle(""))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !res.Pass {
		t.Error("want pass=true (skip) for empty source URL")
	}
	if res.Severity != pipeline.SeverityInfo {
		t.Errorf("want INFO for skip, got %s", res.Severity)
	}
}
