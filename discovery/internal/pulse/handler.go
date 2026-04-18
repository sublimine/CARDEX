package pulse

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// Handler returns an http.Handler for the three pulse REST endpoints:
//
//	GET /pulse/health/{dealer_id}
//	GET /pulse/watchlist
//	GET /pulse/trend/{dealer_id}
func Handler(db *sql.DB, weights WeightConfig) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/pulse/health/", func(w http.ResponseWriter, r *http.Request) {
		dealerID := strings.TrimPrefix(r.URL.Path, "/pulse/health/")
		if dealerID == "" {
			http.Error(w, "dealer_id required", http.StatusBadRequest)
			return
		}
		handleHealth(w, r, db, weights, dealerID)
	})
	mux.HandleFunc("/pulse/watchlist", func(w http.ResponseWriter, r *http.Request) {
		handleWatchlist(w, r, db)
	})
	mux.HandleFunc("/pulse/trend/", func(w http.ResponseWriter, r *http.Request) {
		dealerID := strings.TrimPrefix(r.URL.Path, "/pulse/trend/")
		if dealerID == "" {
			http.Error(w, "dealer_id required", http.StatusBadRequest)
			return
		}
		handleTrend(w, r, db, dealerID)
	})
	return mux
}

func handleHealth(w http.ResponseWriter, r *http.Request, db *sql.DB, weights WeightConfig, dealerID string) {
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()

	t0 := time.Now()
	score, err := ComputeSignals(ctx, db, dealerID, time.Now())
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) || strings.Contains(err.Error(), "no rows") {
			http.Error(w, fmt.Sprintf("dealer %q not found", dealerID), http.StatusNotFound)
			return
		}
		http.Error(w, "internal error: "+err.Error(), http.StatusInternalServerError)
		return
	}

	history, _ := LoadHistory(ctx, db, dealerID, 30)
	Score(score, weights, history)
	ScoreComputeDuration.Observe(time.Since(t0).Seconds())

	writeJSON(w, score)
}

func handleWatchlist(w http.ResponseWriter, r *http.Request, db *sql.DB) {
	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()

	maxScore := 70.0
	country := r.URL.Query().Get("country")

	if tier := r.URL.Query().Get("tier"); tier != "" {
		switch tier {
		case TierWatch:
			maxScore = 70
		case TierStress:
			maxScore = 50
		case TierCritical:
			maxScore = 30
		default:
			http.Error(w, "unknown tier; use watch|stress|critical", http.StatusBadRequest)
			return
		}
	}

	results, err := Watchlist(ctx, db, maxScore, country)
	if err != nil {
		http.Error(w, "internal error: "+err.Error(), http.StatusInternalServerError)
		return
	}
	writeJSON(w, map[string]any{"dealers": results, "total": len(results)})
}

func handleTrend(w http.ResponseWriter, r *http.Request, db *sql.DB, dealerID string) {
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()

	history, err := LoadHistory(ctx, db, dealerID, 30)
	if err != nil {
		http.Error(w, "internal error: "+err.Error(), http.StatusInternalServerError)
		return
	}
	writeJSON(w, map[string]any{
		"dealer_id": dealerID,
		"history":   history,
		"points":    len(history),
	})
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	if err := enc.Encode(v); err != nil {
		http.Error(w, "encode error: "+err.Error(), http.StatusInternalServerError)
	}
}
