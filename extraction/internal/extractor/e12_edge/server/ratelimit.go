package server

import (
	"sync"
	"time"
)

// rateLimiter enforces a per-dealer listing rate limit.
// It uses a sliding window of 60 seconds with a configurable max count.
type rateLimiter struct {
	mu       sync.Mutex
	windows  map[string]*window
	maxCount int // max listings per windowSize
	windowSz time.Duration
}

type window struct {
	count     int
	resetAt   time.Time
}

// newRateLimiter constructs a limiter allowing maxPerMin listings per 60s window.
func newRateLimiter(maxPerMin int) *rateLimiter {
	return &rateLimiter{
		windows:  make(map[string]*window),
		maxCount: maxPerMin,
		windowSz: time.Minute,
	}
}

// Allow returns true if the dealer can send count more listings within the
// current rate-limit window, and false if they are over the limit.
// It advances the window if the current one has expired.
func (r *rateLimiter) Allow(dealerID string, count int) bool {
	r.mu.Lock()
	defer r.mu.Unlock()

	now := time.Now()
	w, ok := r.windows[dealerID]
	if !ok || now.After(w.resetAt) {
		r.windows[dealerID] = &window{count: count, resetAt: now.Add(r.windowSz)}
		return count <= r.maxCount
	}
	if w.count+count > r.maxCount {
		return false
	}
	w.count += count
	return true
}

// Reset clears the window for the given dealer (used in tests).
func (r *rateLimiter) Reset(dealerID string) {
	r.mu.Lock()
	delete(r.windows, dealerID)
	r.mu.Unlock()
}
