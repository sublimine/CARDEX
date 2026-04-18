// trust-service — CARDEX Dealer KYB Trust Profile Engine
//
// HTTP API:
//
//	GET  /health                        liveness probe
//	GET  /trust/profile/{dealer_id}     full trust profile JSON
//	GET  /trust/badge/{dealer_id}.svg   embeddable SVG badge
//	GET  /trust/verify/{profile_hash}   verify badge authenticity
//	POST /trust/refresh/{dealer_id}     force-recompute trust profile
//	GET  /trust/list                    ?tier=&country=&limit= list profiles
//
// Environment variables:
//
//	TRUST_DB_PATH       path to shared SQLite KG (default: ./data/discovery.db)
//	TRUST_PORT          HTTP listen port          (default: 8505)
//	TRUST_BADGE_BASE    base URL for badge links  (default: http://localhost:8505)
//	TRUST_MIN_LISTINGS  min listings to profile   (default: 5)
package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	_ "modernc.org/sqlite"

	"cardex.eu/trust/internal/badge"
	"cardex.eu/trust/internal/model"
	"cardex.eu/trust/internal/profiler"
	"cardex.eu/trust/internal/storage"
)

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(log)

	dbPath := env("TRUST_DB_PATH", "./data/discovery.db")
	port := env("TRUST_PORT", "8505")
	badgeBase := env("TRUST_BADGE_BASE", "http://localhost:8505")
	minListings, _ := strconv.Atoi(env("TRUST_MIN_LISTINGS", "5"))
	if minListings <= 0 {
		minListings = 5
	}

	store, err := storage.New(dbPath)
	if err != nil {
		log.Error("storage init failed", "err", err)
		os.Exit(1)
	}
	defer store.Close()

	kg, err := sql.Open("sqlite", dbPath+"?_journal_mode=WAL&_busy_timeout=5000")
	if err != nil {
		log.Error("kg db open failed", "err", err)
		os.Exit(1)
	}
	defer kg.Close()

	srv := &server{store: store, kg: kg, badgeBase: badgeBase, minListings: minListings, log: log}

	go func() {
		ctx := context.Background()
		srv.refreshAll(ctx)
		ticker := time.NewTicker(7 * 24 * time.Hour)
		defer ticker.Stop()
		for range ticker.C {
			srv.refreshAll(ctx)
		}
	}()

	mux := http.NewServeMux()
	mux.HandleFunc("/health", srv.handleHealth)
	mux.HandleFunc("/trust/list", srv.handleList)
	mux.HandleFunc("/trust/profile/", srv.handleProfile)
	mux.HandleFunc("/trust/badge/", srv.handleBadge)
	mux.HandleFunc("/trust/verify/", srv.handleVerify)
	mux.HandleFunc("/trust/refresh/", srv.handleRefresh)

	addr := ":" + port
	log.Info("trust-service starting", "addr", addr, "db", dbPath)
	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Error("server error", "err", err)
		os.Exit(1)
	}
}

type server struct {
	store       *storage.Store
	kg          *sql.DB
	badgeBase   string
	minListings int
	log         *slog.Logger
}

func (s *server) handleHealth(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Write([]byte(`{"status":"ok"}`))
}

func (s *server) handleProfile(w http.ResponseWriter, r *http.Request) {
	dealerID := strings.TrimPrefix(r.URL.Path, "/trust/profile/")
	if dealerID == "" {
		s.jsonError(w, "missing dealer_id", http.StatusBadRequest)
		return
	}
	p, err := s.store.Get(r.Context(), dealerID)
	if err != nil {
		s.jsonError(w, err.Error(), http.StatusInternalServerError)
		return
	}
	if p == nil {
		p, err = s.computeAndStore(r.Context(), dealerID)
		if err != nil {
			s.jsonError(w, "dealer not found: "+err.Error(), http.StatusNotFound)
			return
		}
	}
	s.jsonOK(w, p)
}

func (s *server) handleBadge(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimPrefix(r.URL.Path, "/trust/badge/")
	dealerID := strings.TrimSuffix(path, ".svg")
	if dealerID == "" {
		http.Error(w, "missing dealer_id", http.StatusBadRequest)
		return
	}
	tier := "unverified"
	if p, err := s.store.Get(r.Context(), dealerID); err == nil && p != nil {
		tier = p.TrustTier
	}
	svg, err := badge.Generate(tier)
	if err != nil {
		http.Error(w, "badge generation failed", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", badge.ContentType())
	w.Header().Set("Cache-Control", "public, max-age=3600")
	w.Write(svg)
}

func (s *server) handleVerify(w http.ResponseWriter, r *http.Request) {
	hash := strings.TrimPrefix(r.URL.Path, "/trust/verify/")
	if hash == "" {
		s.jsonError(w, "missing profile_hash", http.StatusBadRequest)
		return
	}
	p, err := s.store.GetByHash(r.Context(), hash)
	if err != nil {
		s.jsonError(w, err.Error(), http.StatusInternalServerError)
		return
	}
	if p == nil {
		s.jsonOK(w, map[string]any{"valid": false})
		return
	}
	expired := p.IsExpired(time.Now().UTC())
	s.jsonOK(w, map[string]any{
		"valid":       !expired,
		"dealer_id":   p.DealerID,
		"trust_tier":  p.TrustTier,
		"trust_score": p.TrustScore,
		"expires_at":  p.ExpiresAt,
		"expired":     expired,
	})
}

func (s *server) handleRefresh(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	dealerID := strings.TrimPrefix(r.URL.Path, "/trust/refresh/")
	if dealerID == "" {
		s.jsonError(w, "missing dealer_id", http.StatusBadRequest)
		return
	}
	p, err := s.computeAndStore(r.Context(), dealerID)
	if err != nil {
		s.jsonError(w, err.Error(), http.StatusNotFound)
		return
	}
	s.jsonOK(w, p)
}

func (s *server) handleList(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	limit, _ := strconv.Atoi(q.Get("limit"))
	profiles, err := s.store.List(r.Context(), storage.ListFilter{
		Tier:    q.Get("tier"),
		Country: q.Get("country"),
		Limit:   limit,
	})
	if err != nil {
		s.jsonError(w, err.Error(), http.StatusInternalServerError)
		return
	}
	s.jsonOK(w, map[string]any{"count": len(profiles), "profiles": profiles})
}

func (s *server) computeAndStore(ctx context.Context, dealerID string) (*model.DealerTrustProfile, error) {
	sig, err := storage.FetchSignals(ctx, s.kg, dealerID)
	if err != nil {
		return nil, err
	}
	in := storage.SignalsToInput(sig, s.badgeBase, time.Now().UTC())
	p := profiler.Compute(in)
	if err := s.store.Upsert(ctx, p); err != nil {
		s.log.Warn("upsert failed", "dealer_id", dealerID, "err", err)
	}
	return p, nil
}

func (s *server) refreshAll(ctx context.Context) {
	ids, err := storage.ListEligibleDealers(ctx, s.kg, s.minListings)
	if err != nil {
		s.log.Warn("refreshAll: list dealers", "err", err)
		return
	}
	s.log.Info("refreshAll: starting", "dealers", len(ids))
	for _, id := range ids {
		if ctx.Err() != nil {
			return
		}
		if _, err := s.computeAndStore(ctx, id); err != nil {
			s.log.Warn("refreshAll: compute failed", "dealer_id", id, "err", err)
		}
	}
	s.log.Info("refreshAll: complete", "dealers", len(ids))
}

func (s *server) jsonOK(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(v)
}

func (s *server) jsonError(w http.ResponseWriter, msg string, code int) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(map[string]string{"error": msg})
}

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
