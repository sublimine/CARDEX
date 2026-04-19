// Package middleware provides reusable HTTP middleware for the workspace service.
package middleware

import (
	"net/http"
	"strings"
)

// CORS returns a middleware that adds CORS response headers.
//
// allowedOrigins is a list of exact origins to allow plus optional wildcard
// suffix patterns (e.g. ".trycloudflare.com", ".ngrok-free.app").  The empty
// string "" or "*" may be included to allow any origin.
//
// Preflight (OPTIONS) requests are answered immediately with 204 No Content so
// that browsers don't block the actual request.
func CORS(allowedOrigins []string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			origin := r.Header.Get("Origin")
			if origin == "" {
				// Same-origin or non-browser request — no CORS headers needed.
				next.ServeHTTP(w, r)
				return
			}

			if originAllowed(origin, allowedOrigins) {
				h := w.Header()
				h.Set("Access-Control-Allow-Origin", origin)
				h.Set("Access-Control-Allow-Credentials", "true")
				h.Set("Vary", "Origin")
			}

			if r.Method == http.MethodOptions {
				// Preflight — echo requested method/headers and finish.
				h := w.Header()
				if reqMethod := r.Header.Get("Access-Control-Request-Method"); reqMethod != "" {
					h.Set("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
				}
				if reqHeaders := r.Header.Get("Access-Control-Request-Headers"); reqHeaders != "" {
					h.Set("Access-Control-Allow-Headers", reqHeaders)
				}
				h.Set("Access-Control-Max-Age", "86400")
				w.WriteHeader(http.StatusNoContent)
				return
			}

			next.ServeHTTP(w, r)
		})
	}
}

func originAllowed(origin string, allowed []string) bool {
	for _, a := range allowed {
		switch {
		case a == "" || a == "*":
			return true
		case strings.HasPrefix(a, "."):
			// Wildcard suffix — e.g. ".trycloudflare.com" matches
			// "https://abc.trycloudflare.com".
			if strings.HasSuffix(origin, a) {
				return true
			}
		default:
			if origin == a {
				return true
			}
		}
	}
	return false
}
