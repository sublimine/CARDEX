package browser

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

// roundTripFunc lets us use a plain function as an http.RoundTripper.
type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

// newTestTransport returns a RetryTransport with a mock sleepFn so tests don't
// actually sleep, and predictable timing.
func newTestTransport(base http.RoundTripper) *RetryTransport {
	return &RetryTransport{
		Base:       base,
		MaxRetries: 3,
		BaseDelay:  10 * time.Millisecond,
		MaxDelay:   100 * time.Millisecond,
		sleepFn:    func(time.Duration) {}, // no-op: skip actual sleeping
	}
}

// statusResponse builds a minimal *http.Response with the given status code.
func statusResponse(code int) *http.Response {
	return &http.Response{
		StatusCode: code,
		Header:     make(http.Header),
		Body:       http.NoBody,
	}
}

// TestRetry_429_RetriesAndSucceeds verifies that a 429 triggers retries and
// the transport returns success once the server recovers.
func TestRetry_429_RetriesAndSucceeds(t *testing.T) {
	var calls atomic.Int32

	base := roundTripFunc(func(r *http.Request) (*http.Response, error) {
		n := calls.Add(1)
		if n < 3 {
			return statusResponse(http.StatusTooManyRequests), nil
		}
		return statusResponse(http.StatusOK), nil
	})

	rt := newTestTransport(base)
	req, _ := http.NewRequest(http.MethodGet, "http://example.com/", nil)
	resp, err := rt.RoundTrip(req)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.StatusCode != http.StatusOK {
		t.Errorf("want 200, got %d", resp.StatusCode)
	}
	if calls.Load() != 3 {
		t.Errorf("want 3 calls (2 retries), got %d", calls.Load())
	}
}

// TestRetry_503_Retries verifies that a 503 Service Unavailable triggers retries.
func TestRetry_503_Retries(t *testing.T) {
	var calls atomic.Int32

	base := roundTripFunc(func(r *http.Request) (*http.Response, error) {
		n := calls.Add(1)
		if n < 2 {
			return statusResponse(http.StatusServiceUnavailable), nil
		}
		return statusResponse(http.StatusOK), nil
	})

	rt := newTestTransport(base)
	req, _ := http.NewRequest(http.MethodGet, "http://example.com/", nil)
	resp, err := rt.RoundTrip(req)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.StatusCode != http.StatusOK {
		t.Errorf("want 200, got %d", resp.StatusCode)
	}
	if calls.Load() < 2 {
		t.Errorf("want at least 2 calls (1 retry), got %d", calls.Load())
	}
}

// TestRetry_404_DoesNotRetry verifies that a 404 is returned immediately without
// any retry attempt.
func TestRetry_404_DoesNotRetry(t *testing.T) {
	var calls atomic.Int32

	base := roundTripFunc(func(r *http.Request) (*http.Response, error) {
		calls.Add(1)
		return statusResponse(http.StatusNotFound), nil
	})

	rt := newTestTransport(base)
	req, _ := http.NewRequest(http.MethodGet, "http://example.com/missing", nil)
	resp, err := rt.RoundTrip(req)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.StatusCode != http.StatusNotFound {
		t.Errorf("want 404, got %d", resp.StatusCode)
	}
	if calls.Load() != 1 {
		t.Errorf("want exactly 1 call (no retries), got %d", calls.Load())
	}
}

// TestRetry_RetryAfterHeader verifies that the Retry-After delta-seconds header
// is passed to sleepFn when a 429 response includes it.
func TestRetry_RetryAfterHeader(t *testing.T) {
	var calls atomic.Int32
	var sleeptimes []time.Duration

	base := roundTripFunc(func(r *http.Request) (*http.Response, error) {
		n := calls.Add(1)
		if n == 1 {
			resp := statusResponse(http.StatusTooManyRequests)
			resp.Header.Set("Retry-After", "5") // 5 seconds
			return resp, nil
		}
		return statusResponse(http.StatusOK), nil
	})

	rt := &RetryTransport{
		Base:       base,
		MaxRetries: 3,
		BaseDelay:  10 * time.Millisecond,
		MaxDelay:   60 * time.Second, // high enough to not cap the 5s
		sleepFn: func(d time.Duration) {
			sleeptimes = append(sleeptimes, d)
		},
	}

	req, _ := http.NewRequest(http.MethodGet, "http://example.com/", nil)
	resp, err := rt.RoundTrip(req)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.StatusCode != http.StatusOK {
		t.Errorf("want 200, got %d", resp.StatusCode)
	}
	if len(sleeptimes) == 0 {
		t.Fatal("sleepFn was never called")
	}
	// The Retry-After of 5s should be honoured.
	if sleeptimes[0] < 4*time.Second || sleeptimes[0] > 6*time.Second {
		t.Errorf("expected ~5s sleep from Retry-After, got %v", sleeptimes[0])
	}
}

// TestRetry_MaxRetriesExhausted verifies that after MaxRetries the last error
// (or last non-retryable response) is returned.
func TestRetry_MaxRetriesExhausted(t *testing.T) {
	var calls atomic.Int32

	base := roundTripFunc(func(r *http.Request) (*http.Response, error) {
		calls.Add(1)
		return nil, fmt.Errorf("connection refused")
	})

	rt := newTestTransport(base)
	req, _ := http.NewRequest(http.MethodGet, "http://example.com/", nil)
	_, err := rt.RoundTrip(req)
	if err == nil {
		t.Fatal("want error after MaxRetries exhausted, got nil")
	}
	if !strings.Contains(err.Error(), "connection refused") {
		t.Errorf("want original error in message, got %v", err)
	}
	wantCalls := int32(rt.MaxRetries + 1)
	if calls.Load() != wantCalls {
		t.Errorf("want %d calls (initial + %d retries), got %d",
			wantCalls, rt.MaxRetries, calls.Load())
	}
}

// TestRetry_Integration is a light smoke-test against a real httptest.Server.
func TestRetry_Integration(t *testing.T) {
	var hits atomic.Int32
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := hits.Add(1)
		if n < 2 {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer ts.Close()

	rt := &RetryTransport{
		Base:       http.DefaultTransport,
		MaxRetries: 3,
		BaseDelay:  5 * time.Millisecond,
		MaxDelay:   50 * time.Millisecond,
	}
	client := &http.Client{Transport: rt}
	resp, err := client.Get(ts.URL)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Errorf("want 200, got %d", resp.StatusCode)
	}
}
