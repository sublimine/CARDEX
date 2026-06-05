// Package httpx provides JSON response helpers and HTTP middleware shared by all
// API handlers. The response envelope is intentionally minimal: success payloads
// are serialized directly; errors use a small {error:{code,message}} object so
// clients can branch on a stable machine-readable code.
package httpx

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"log/slog"
	"net/http"
)

// CacheKey builds a bounded Redis cache key from a route and a raw query string.
// The query is hashed so an attacker cannot exhaust Redis memory with long
// values, and the key length stays constant.
func CacheKey(route, rawQuery string) string {
	sum := sha256.Sum256([]byte(rawQuery))
	return route + ":" + hex.EncodeToString(sum[:])
}

// ErrorBody is the JSON error envelope.
type ErrorBody struct {
	Error ErrorDetail `json:"error"`
}

// ErrorDetail carries a stable code and a human message.
type ErrorDetail struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

// WriteJSON serializes v as JSON with the given status code.
func WriteJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	if v == nil {
		return
	}
	if err := json.NewEncoder(w).Encode(v); err != nil {
		// Status/body already partially written; just log.
		slog.Error("writeJSON encode failed", "err", err)
	}
}

// WriteError emits a structured JSON error with the given status and code.
func WriteError(w http.ResponseWriter, status int, code, message string) {
	WriteJSON(w, status, ErrorBody{Error: ErrorDetail{Code: code, Message: message}})
}
