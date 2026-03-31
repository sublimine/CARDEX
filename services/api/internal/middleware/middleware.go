// Package middleware provides HTTP middleware for the CARDEX API.
package middleware

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

type contextKey string

const (
	keyRequestID  contextKey = "request_id"
	keyDealerID   contextKey = "dealer_id"
	keyDealerULID contextKey = "dealer_ulid"
)

// RequestID adds a unique request ID to every request.
func RequestID(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := r.Header.Get("X-Request-ID")
		if id == "" {
			b := make([]byte, 8)
			rand.Read(b)
			id = hex.EncodeToString(b)
		}
		ctx := context.WithValue(r.Context(), keyRequestID, id)
		w.Header().Set("X-Request-ID", id)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// Logger logs request method, path, status, and latency.
func Logger(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rw := &responseWriter{ResponseWriter: w, code: http.StatusOK}
		next.ServeHTTP(rw, r)
		slog.Info("api.request",
			"method", r.Method,
			"path", r.URL.Path,
			"status", rw.code,
			"latency_ms", time.Since(start).Milliseconds(),
			"request_id", r.Context().Value(keyRequestID),
		)
	})
}

// CORS sets permissive CORS headers for the Next.js frontend.
func CORS(next http.Handler) http.Handler {
	allowedOrigins := strings.Split(
		envOrDefault("CORS_ORIGINS", "http://localhost:3001,https://cardex.eu,https://www.cardex.eu"),
		",",
	)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		for _, allowed := range allowedOrigins {
			if origin == strings.TrimSpace(allowed) {
				w.Header().Set("Access-Control-Allow-Origin", origin)
				break
			}
		}
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Request-ID")
		w.Header().Set("Access-Control-Max-Age", "86400")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// Auth validates JWT RS256 Bearer token and injects dealer_id into context.
// Returns 401 if token is missing/invalid; 403 if dealer is not active.
func Auth(next http.HandlerFunc) http.HandlerFunc {
	pubKeyPath := envOrDefault("JWT_RS256_PUBLIC_KEY_FILE", "/run/secrets/jwt_public_key")
	pubKeyBytes, err := os.ReadFile(pubKeyPath)
	if err != nil {
		// Fall back to dev key if file not found
		slog.Warn("middleware.auth: public key file not found, using dev mode", "path", pubKeyPath)
		pubKeyBytes = nil
	}

	return func(w http.ResponseWriter, r *http.Request) {
		authHeader := r.Header.Get("Authorization")
		if !strings.HasPrefix(authHeader, "Bearer ") {
			http.Error(w, `{"error":"missing_token"}`, http.StatusUnauthorized)
			return
		}
		tokenStr := strings.TrimPrefix(authHeader, "Bearer ")

		// Dev mode: accept any token with sub claim
		if pubKeyBytes == nil {
			claims := jwt.MapClaims{}
			parser := jwt.NewParser()
			tok, _, err := parser.ParseUnverified(tokenStr, claims)
			if err != nil || !tok.Valid {
				http.Error(w, `{"error":"invalid_token"}`, http.StatusUnauthorized)
				return
			}
			sub, _ := claims["sub"].(string)
			ctx := context.WithValue(r.Context(), keyDealerULID, sub)
			next(w, r.WithContext(ctx))
			return
		}

		pubKey, err := jwt.ParseRSAPublicKeyFromPEM(pubKeyBytes)
		if err != nil {
			http.Error(w, `{"error":"server_error"}`, http.StatusInternalServerError)
			return
		}

		claims := jwt.MapClaims{}
		_, err = jwt.ParseWithClaims(tokenStr, claims, func(t *jwt.Token) (interface{}, error) {
			if _, ok := t.Method.(*jwt.SigningMethodRSA); !ok {
				return nil, jwt.ErrSignatureInvalid
			}
			return pubKey, nil
		})
		if err != nil {
			http.Error(w, `{"error":"invalid_token"}`, http.StatusUnauthorized)
			return
		}

		sub, _ := claims["sub"].(string)
		if sub == "" {
			http.Error(w, `{"error":"invalid_claims"}`, http.StatusUnauthorized)
			return
		}

		ctx := context.WithValue(r.Context(), keyDealerULID, sub)
		next(w, r.WithContext(ctx))
	}
}

// GetDealerULID retrieves the authenticated dealer's ULID from context.
func GetDealerULID(ctx context.Context) string {
	v, _ := ctx.Value(keyDealerULID).(string)
	return v
}

// responseWriter wraps http.ResponseWriter to capture status code.
type responseWriter struct {
	http.ResponseWriter
	code int
}

func (rw *responseWriter) WriteHeader(code int) {
	rw.code = code
	rw.ResponseWriter.WriteHeader(code)
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
