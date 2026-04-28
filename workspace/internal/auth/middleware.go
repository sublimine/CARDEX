package auth

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"sync"
	"time"
)

// RequireAuth returns middleware that validates the Bearer JWT in the
// Authorization header. On success it injects userID and tenantID into the
// request context via TenantIDFromCtx / UserIDFromCtx. On failure: 401 JSON.
func RequireAuth(jwtSvc *JWTService) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			token := extractBearer(r)
			if token == "" {
				jsonAuthErr(w, http.StatusUnauthorized, "authorization header required")
				return
			}
			claims, err := jwtSvc.ValidateToken(token)
			if err != nil {
				msg := "invalid token"
				if err == ErrTokenExpired {
					msg = "token expired"
				}
				jsonAuthErr(w, http.StatusUnauthorized, msg)
				return
			}
			ctx := context.WithValue(r.Context(), ctxKeyUserID, claims.UserID)
			ctx = context.WithValue(ctx, ctxKeyTenantID, claims.TenantID)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// ── Rate limiter ─────────────────────────────────────────────────────────────

const (
	rateLimitWindow   = 15 * time.Minute
	rateLimitMaxTries = 5
)

type attempt struct {
	count     int
	windowEnd time.Time
}

// loginRateLimiter tracks failed login attempts per IP address.
type loginRateLimiter struct {
	mu   sync.Mutex
	data map[string]*attempt
}

func newLoginRateLimiter() *loginRateLimiter {
	rl := &loginRateLimiter{data: make(map[string]*attempt)}
	go rl.cleanup()
	return rl
}

// Allow returns true if the IP may attempt a login, false if rate-limited.
// It increments the counter on each call.
func (rl *loginRateLimiter) Allow(ip string) bool {
	rl.mu.Lock()
	defer rl.mu.Unlock()
	now := time.Now()
	a, ok := rl.data[ip]
	if !ok || now.After(a.windowEnd) {
		rl.data[ip] = &attempt{count: 1, windowEnd: now.Add(rateLimitWindow)}
		return true
	}
	a.count++
	return a.count <= rateLimitMaxTries
}

// Reset clears the counter for an IP (called on successful login).
func (rl *loginRateLimiter) Reset(ip string) {
	rl.mu.Lock()
	delete(rl.data, ip)
	rl.mu.Unlock()
}

func (rl *loginRateLimiter) cleanup() {
	t := time.NewTicker(5 * time.Minute)
	for range t.C {
		rl.mu.Lock()
		now := time.Now()
		for ip, a := range rl.data {
			if now.After(a.windowEnd) {
				delete(rl.data, ip)
			}
		}
		rl.mu.Unlock()
	}
}

// ── helpers ───────────────────────────────────────────────────────────────────

func extractBearer(r *http.Request) string {
	h := r.Header.Get("Authorization")
	if !strings.HasPrefix(h, "Bearer ") {
		return ""
	}
	return strings.TrimPrefix(h, "Bearer ")
}

func jsonAuthErr(w http.ResponseWriter, status int, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": msg})
}
