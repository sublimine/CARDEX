// Package handlers contains all HTTP handler functions for the CARDEX API.
package handlers

import (
	"encoding/json"
	"net/http"
	"os"

	clickhouse "github.com/ClickHouse/clickhouse-go/v2"
	"github.com/cardex/alpha/pkg/nlc"
	meilisearch "github.com/meilisearch/meilisearch-go"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

// Deps holds shared dependencies injected into all handlers.
type Deps struct {
	DB       *pgxpool.Pool
	Redis    *redis.Client
	CH       clickhouse.Conn
	Meili    meilisearch.IndexManager
	NLCCalc  *nlc.Calculator
}

// envOrDefault returns the value of the environment variable key,
// or fallback if the variable is unset or empty.
func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

// writeJSON encodes v as JSON and writes it with the given status code.
func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

// writeError writes a JSON error response.
func writeError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, map[string]string{"error": code, "message": message})
}

// requireCH returns true if ClickHouse is available, otherwise writes 503 and returns false.
func (d *Deps) requireCH(w http.ResponseWriter) bool {
	if d.CH == nil {
		writeError(w, http.StatusServiceUnavailable, "analytics_unavailable", "Analytics engine not connected in this environment")
		return false
	}
	return true
}

// requireMeili returns true if MeiliSearch is available, otherwise writes 503 and returns false.
func (d *Deps) requireMeili(w http.ResponseWriter) bool {
	if d.Meili == nil {
		writeError(w, http.StatusServiceUnavailable, "search_unavailable", "Search engine not connected in this environment")
		return false
	}
	return true
}
