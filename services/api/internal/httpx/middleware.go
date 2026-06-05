package httpx

import (
	"context"
	"crypto/rand"
	"crypto/subtle"
	"encoding/hex"
	"errors"
	"log/slog"
	"net/http"
	"strconv"
	"time"

	"cardex.eu/api/internal/apikeys"
	"cardex.eu/api/internal/metrics"
	"cardex.eu/api/internal/redisx"
)

// ctxKey is a private context key type to avoid collisions.
type ctxKey int

const (
	ctxKeyRequestID ctxKey = iota
	ctxKeyTier
	ctxKeyKeyName
)

// Middleware is the standard wrapper signature.
type Middleware func(http.Handler) http.Handler

// Chain applies middlewares in order so the first listed runs outermost.
func Chain(h http.Handler, mws ...Middleware) http.Handler {
	for i := len(mws) - 1; i >= 0; i-- {
		h = mws[i](h)
	}
	return h
}

// statusRecorder captures the response status code for logging/metrics.
type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (s *statusRecorder) WriteHeader(code int) {
	s.status = code
	s.ResponseWriter.WriteHeader(code)
}

func (s *statusRecorder) Write(b []byte) (int, error) {
	if s.status == 0 {
		s.status = http.StatusOK
	}
	return s.ResponseWriter.Write(b)
}

// statusClass maps a status code to "2xx"/"4xx"/"5xx" for low-cardinality labels.
func statusClass(code int) string {
	switch {
	case code >= 500:
		return "5xx"
	case code >= 400:
		return "4xx"
	case code >= 300:
		return "3xx"
	default:
		return "2xx"
	}
}

// routeLabel returns the matched ServeMux pattern, or "unmatched".
func routeLabel(r *http.Request) string {
	if r.Pattern != "" {
		return r.Pattern
	}
	return "unmatched"
}

// Recover converts a panic into a 500 so one bad handler cannot crash the server.
func Recover(log *slog.Logger) Middleware {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			defer func() {
				if rec := recover(); rec != nil {
					log.Error("panic recovered", "err", rec, "path", r.URL.Path,
						"request_id", RequestID(r.Context()))
					WriteError(w, http.StatusInternalServerError, "internal_error", "internal server error")
				}
			}()
			next.ServeHTTP(w, r)
		})
	}
}

// Observe assigns a request ID, logs the request, and records Prometheus metrics.
func Observe(log *slog.Logger) Middleware {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			reqID := newRequestID()
			ctx := context.WithValue(r.Context(), ctxKeyRequestID, reqID)
			r = r.WithContext(ctx)
			w.Header().Set("X-Request-ID", reqID)

			rec := &statusRecorder{ResponseWriter: w}
			next.ServeHTTP(rec, r)

			route := routeLabel(r)
			dur := time.Since(start)
			metrics.RequestsTotal.WithLabelValues(route, r.Method, statusClass(rec.status)).Inc()
			metrics.RequestDuration.WithLabelValues(route).Observe(dur.Seconds())
			log.Info("request",
				"method", r.Method,
				"path", r.URL.Path,
				"route", route,
				"status", rec.status,
				"duration_ms", dur.Milliseconds(),
				"request_id", reqID,
			)
		})
	}
}

// CORS applies a strict origin allow-list. A request from an allowed origin gets
// the reflective ACAO header; preflight OPTIONS short-circuits with 204.
func CORS(origins []string) Middleware {
	allow := make(map[string]bool, len(origins))
	for _, o := range origins {
		allow[o] = true
	}
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			origin := r.Header.Get("Origin")
			if origin != "" && allow[origin] {
				w.Header().Set("Access-Control-Allow-Origin", origin)
				w.Header().Set("Vary", "Origin")
				w.Header().Set("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
				w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-API-Key")
				w.Header().Set("Access-Control-Allow-Credentials", "false")
				w.Header().Set("Access-Control-Max-Age", "600")
			}
			if r.Method == http.MethodOptions {
				w.WriteHeader(http.StatusNoContent)
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

// Authenticator validates API keys and enforces per-tier rate limits.
type Authenticator struct {
	redis        *redisx.Client
	log          *slog.Logger
	bootstrapKey string
	limitFree    int
	limitPaid    int
	limitEnt     int
}

// NewAuthenticator builds an Authenticator.
func NewAuthenticator(r *redisx.Client, log *slog.Logger, bootstrapKey string, limitFree, limitPaid, limitEnt int) *Authenticator {
	return &Authenticator{
		redis:        r,
		log:          log,
		bootstrapKey: bootstrapKey,
		limitFree:    limitFree,
		limitPaid:    limitPaid,
		limitEnt:     limitEnt,
	}
}

// limitFor returns the per-minute request ceiling for a tier.
func (a *Authenticator) limitFor(t apikeys.Tier) int {
	switch t {
	case apikeys.TierEnterprise:
		return a.limitEnt
	case apikeys.TierPaid:
		return a.limitPaid
	default:
		return a.limitFree
	}
}

// Middleware authenticates via the X-API-Key header then applies the rate limit.
func (a *Authenticator) Middleware() Middleware {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			key := r.Header.Get("X-API-Key")
			if key == "" {
				metrics.AuthFailures.Inc()
				WriteError(w, http.StatusUnauthorized, "missing_api_key", "X-API-Key header is required")
				return
			}

			tier, name, ok := a.resolve(r.Context(), key)
			if !ok {
				metrics.AuthFailures.Inc()
				WriteError(w, http.StatusUnauthorized, "invalid_api_key", "the provided API key is invalid or inactive")
				return
			}

			limit := a.limitFor(tier)
			res, err := a.redis.Allow(r.Context(), key, limit)
			if err != nil {
				metrics.RateLimiterDegraded.Inc()
				a.log.Warn("rate limiter degraded (failing open)", "err", err)
			}
			if limit > 0 {
				w.Header().Set("X-RateLimit-Limit", strconv.Itoa(res.Limit))
				w.Header().Set("X-RateLimit-Remaining", strconv.Itoa(res.Remaining))
				w.Header().Set("X-RateLimit-Reset", strconv.Itoa(res.ResetSeconds))
			}
			if !res.Allowed {
				metrics.RateLimited.WithLabelValues(string(tier)).Inc()
				w.Header().Set("Retry-After", strconv.Itoa(res.ResetSeconds))
				WriteError(w, http.StatusTooManyRequests, "rate_limited",
					"rate limit exceeded for your tier; retry after the window resets")
				return
			}

			ctx := context.WithValue(r.Context(), ctxKeyTier, tier)
			ctx = context.WithValue(ctx, ctxKeyKeyName, name)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// resolve validates a key against the bootstrap key first (constant-time), then
// Redis. It returns the tier, owner name and whether the key is valid+active.
func (a *Authenticator) resolve(ctx context.Context, key string) (apikeys.Tier, string, bool) {
	if a.bootstrapKey != "" && subtle.ConstantTimeCompare([]byte(key), []byte(a.bootstrapKey)) == 1 {
		return apikeys.TierEnterprise, "bootstrap", true
	}
	ak, err := a.redis.LookupAPIKey(ctx, key)
	if err != nil {
		if !errors.Is(err, redisx.ErrKeyNotFound) {
			a.log.Warn("apikey lookup error", "err", err)
		}
		return "", "", false
	}
	if !ak.Active || !ak.Tier.Valid() {
		return "", "", false
	}
	return ak.Tier, ak.Name, true
}

// newRequestID returns a random 16-hex-char request id.
func newRequestID() string {
	var b [8]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "0000000000000000"
	}
	return hex.EncodeToString(b[:])
}

// RequestID extracts the request id from context (empty if absent).
func RequestID(ctx context.Context) string {
	if v, ok := ctx.Value(ctxKeyRequestID).(string); ok {
		return v
	}
	return ""
}

// TierFromContext returns the authenticated tier (empty if unauthenticated).
func TierFromContext(ctx context.Context) apikeys.Tier {
	if v, ok := ctx.Value(ctxKeyTier).(apikeys.Tier); ok {
		return v
	}
	return ""
}

// KeyNameFromContext returns the authenticated API-key owner name (empty if
// unauthenticated). Used to scope per-owner resources such as alerts.
func KeyNameFromContext(ctx context.Context) string {
	if v, ok := ctx.Value(ctxKeyKeyName).(string); ok {
		return v
	}
	return ""
}
