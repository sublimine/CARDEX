package check

import (
	"sync"
	"time"
)

// RateLimiter implements a sliding-window in-memory rate limiter keyed by IP.
// Concurrent-safe; cleanup goroutine runs every 5 minutes.
type RateLimiter struct {
	mu      sync.Mutex
	windows map[string][]time.Time
	limit   int
	window  time.Duration
}

// NewRateLimiter creates a RateLimiter allowing at most limit requests per window.
func NewRateLimiter(limit int, window time.Duration) *RateLimiter {
	rl := &RateLimiter{
		windows: make(map[string][]time.Time),
		limit:   limit,
		window:  window,
	}
	go rl.cleanup()
	return rl
}

// Allow returns true if ip may make a request, recording the attempt.
// Returns false if the window already contains limit or more requests.
func (rl *RateLimiter) Allow(ip string) bool {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	now := time.Now()
	cutoff := now.Add(-rl.window)

	// Prune expired entries for this IP.
	times := rl.windows[ip]
	valid := times[:0]
	for _, t := range times {
		if t.After(cutoff) {
			valid = append(valid, t)
		}
	}

	if len(valid) >= rl.limit {
		rl.windows[ip] = valid
		return false
	}
	rl.windows[ip] = append(valid, now)
	return true
}

func (rl *RateLimiter) cleanup() {
	ticker := time.NewTicker(5 * time.Minute)
	for range ticker.C {
		rl.mu.Lock()
		now := time.Now()
		for ip, times := range rl.windows {
			cutoff := now.Add(-rl.window)
			valid := times[:0]
			for _, t := range times {
				if t.After(cutoff) {
					valid = append(valid, t)
				}
			}
			if len(valid) == 0 {
				delete(rl.windows, ip)
			} else {
				rl.windows[ip] = valid
			}
		}
		rl.mu.Unlock()
	}
}
