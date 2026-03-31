// Package handlers contains all HTTP handler functions for the CARDEX API.
package handlers

import (
	"encoding/json"
	"net/http"

	clickhouse "github.com/ClickHouse/clickhouse-go/v2"
	meilisearch "github.com/meilisearch/meilisearch-go"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

// Deps holds shared dependencies injected into all handlers.
type Deps struct {
	DB    *pgxpool.Pool
	Redis *redis.Client
	CH    clickhouse.Conn
	Meili *meilisearch.Index
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
