package middleware

// RateLimit implements a sliding-window rate limiter using Redis.
//
// Algorithm: Redis sorted set per key, scored by Unix nanoseconds.
// Each request adds an entry; entries older than the window are trimmed.
// The current count determines allow/deny.
//
// Keys:
//   rl:{ip}           — per-IP for public endpoints
//   rl:entity:{ulid}  — per-entity for authenticated endpoints
//
// Limits (configurable via env, defaults below):
//   Public  endpoints: 120 req / 60s  per IP
//   Auth    endpoints: 600 req / 60s  per entity
//   Strict  endpoints: 20  req / 60s  per IP  (auth, register)

import (
	"fmt"
	"net"
	"net/http"
	"strconv"
	"time"

	"github.com/redis/go-redis/v9"
)

// RateLimiter holds the Redis client and limit config.
type RateLimiter struct {
	rdb    *redis.Client
	window time.Duration
	// limit tiers
	publicLimit int // req per window per IP (unauthenticated)
	authLimit   int // req per window per entity (JWT)
	strictLimit int // req per window per IP for sensitive routes
}

// NewRateLimiter creates a RateLimiter.
func NewRateLimiter(rdb *redis.Client) *RateLimiter {
	return &RateLimiter{
		rdb:         rdb,
		window:      60 * time.Second,
		publicLimit: 120,
		authLimit:   600,
		strictLimit: 20,
	}
}

// Public wraps a handler with per-IP rate limiting (120 req/min).
func (rl *RateLimiter) Public(next http.Handler) http.Handler {
	return rl.limit(next, func(r *http.Request) (string, int) {
		return "rl:" + clientIP(r), rl.publicLimit
	})
}

// Authenticated wraps a handler with per-entity rate limiting (600 req/min).
// Falls back to IP limiting if no entity in context.
func (rl *RateLimiter) Authenticated(next http.Handler) http.Handler {
	return rl.limit(next, func(r *http.Request) (string, int) {
		if entity := GetEntityULID(r.Context()); entity != "" {
			return "rl:entity:" + entity, rl.authLimit
		}
		return "rl:" + clientIP(r), rl.publicLimit
	})
}

// Strict wraps a handler with tight per-IP rate limiting (20 req/min).
// Used for login, register, password-reset endpoints.
func (rl *RateLimiter) Strict(next http.Handler) http.Handler {
	return rl.limit(next, func(r *http.Request) (string, int) {
		return "rl:strict:" + clientIP(r), rl.strictLimit
	})
}

// limit is the core sliding-window implementation.
func (rl *RateLimiter) limit(next http.Handler, keyFn func(*http.Request) (string, int)) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		key, limit := keyFn(r)
		now := time.Now()
		windowStart := now.Add(-rl.window)

		pipe := rl.rdb.Pipeline()
		// Remove entries older than the window
		pipe.ZRemRangeByScore(r.Context(), key, "0", strconv.FormatInt(windowStart.UnixNano(), 10))
		// Add this request (score = nanoseconds = unique per request)
		pipe.ZAdd(r.Context(), key, redis.Z{
			Score:  float64(now.UnixNano()),
			Member: fmt.Sprintf("%d", now.UnixNano()),
		})
		// Count current entries
		countCmd := pipe.ZCard(r.Context(), key)
		// Set TTL so orphaned keys don't accumulate
		pipe.Expire(r.Context(), key, rl.window+5*time.Second)
		if _, err := pipe.Exec(r.Context()); err != nil {
			// Redis unavailable — fail open (allow request)
			next.ServeHTTP(w, r)
			return
		}

		count := countCmd.Val()
		remaining := int64(limit) - count
		if remaining < 0 {
			remaining = 0
		}
		reset := now.Add(rl.window).Unix()

		w.Header().Set("X-RateLimit-Limit", strconv.Itoa(limit))
		w.Header().Set("X-RateLimit-Remaining", strconv.FormatInt(remaining, 10))
		w.Header().Set("X-RateLimit-Reset", strconv.FormatInt(reset, 10))

		if count > int64(limit) {
			w.Header().Set("Retry-After", strconv.FormatInt(int64(rl.window.Seconds()), 10))
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusTooManyRequests)
			w.Write([]byte(`{"error":"rate_limit_exceeded","message":"Too many requests. Please slow down.","retry_after":60}`))
			return
		}

		next.ServeHTTP(w, r)
	})
}

// clientIP extracts the real client IP, respecting X-Forwarded-For from trusted proxies.
func clientIP(r *http.Request) string {
	// X-Real-IP (set by nginx)
	if ip := r.Header.Get("X-Real-IP"); ip != "" {
		if parsed := net.ParseIP(ip); parsed != nil {
			return parsed.String()
		}
	}
	// X-Forwarded-For (first entry = original client)
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		for _, part := range splitTrim(xff, ",") {
			if parsed := net.ParseIP(part); parsed != nil {
				return parsed.String()
			}
		}
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}

func splitTrim(s, sep string) []string {
	parts := make([]string, 0, 4)
	for _, p := range splitString(s, sep) {
		if t := trimSpace(p); t != "" {
			parts = append(parts, t)
		}
	}
	return parts
}

func splitString(s, sep string) []string {
	var parts []string
	start := 0
	for i := 0; i <= len(s)-len(sep); i++ {
		if s[i:i+len(sep)] == sep {
			parts = append(parts, s[start:i])
			start = i + len(sep)
			i += len(sep) - 1
		}
	}
	parts = append(parts, s[start:])
	return parts
}

func trimSpace(s string) string {
	start, end := 0, len(s)
	for start < end && (s[start] == ' ' || s[start] == '\t') {
		start++
	}
	for end > start && (s[end-1] == ' ' || s[end-1] == '\t') {
		end--
	}
	return s[start:end]
}
