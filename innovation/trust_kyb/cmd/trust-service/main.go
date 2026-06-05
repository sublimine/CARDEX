// trust-service — CARDEX Dealer KYB Trust Profile Engine
//
// HTTP API:
//
//	GET  /health                        liveness probe
//	GET  /trust/profile/{dealer_id}     full trust profile JSON
//	GET  /trust/badge/{dealer_id}.svg   embeddable SVG badge
//	GET  /trust/verify/{profile_hash}   verify badge authenticity
//	POST /trust/refresh/{dealer_id}     force-recompute trust profile (auth)
//	GET  /trust/list                    ?tier=&country=&limit= list profiles
//
// Environment variables:
//
//	TRUST_DB_PATH              path to shared SQLite KG (default: ./data/discovery.db)
//	TRUST_PORT                 HTTP listen port          (default: 8505)
//	TRUST_BADGE_BASE           base URL for badge links  (default: http://localhost:8505)
//	TRUST_MIN_LISTINGS         min listings to profile   (default: 5)
//	CARDEX_TRUST_REFRESH_TOKEN bearer token for /refresh; empty disables it
//	CARDEX_TRUST_HASH_SECRET   HMAC secret for profile hashes (see model.ComputeHash)
package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"regexp"
	"strconv"
	"strings"
	"syscall"
	"time"

	_ "modernc.org/sqlite"

	"cardex.eu/trust/internal/badge"
	"cardex.eu/trust/internal/model"
	"cardex.eu/trust/internal/profiler"
	"cardex.eu/trust/internal/storage"
)

// dealerIDPattern restricts dealer IDs in URL paths. The KG uses ULIDs and
// short opaque slugs; anything outside this charset is a path-traversal probe.
var dealerIDPattern = regexp.MustCompile(`^[A-Za-z0-9_-]{1,128}$`)

// profileHashPattern restricts the /trust/verify/{hash} segment to 64 hex chars.
var profileHashPattern = regexp.MustCompile(`^[a-f0-9]{64}$`)

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
	refreshToken := os.Getenv("CARDEX_TRUST_REFRESH_TOKEN")
	if os.Getenv("CARDEX_TRUST_HASH_SECRET") == "" {
		log.Warn("CARDEX_TRUST_HASH_SECRET unset — profile hashes fall back to plain SHA-256 and are forgeable")
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

	srv := &server{
		store:        store,
		kg:           kg,
		badgeBase:    badgeBase,
		minListings:  minListings,
		log:          log,
		refreshToken: refreshToken,
	}

	rootCtx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()

	go func() {
		srv.refreshAll(rootCtx)
		ticker := time.NewTicker(7 * 24 * time.Hour)
		defer ticker.Stop()
		for {
			select {
			case <-rootCtx.Done():
				return
			case <-ticker.C:
				srv.refreshAll(rootCtx)
			}
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
	httpSrv := &http.Server{
		Addr:              addr,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       90 * time.Second,
		MaxHeaderBytes:    1 << 20,
	}

	log.Info("trust-service starting", "addr", addr, "db", dbPath)
	serveErr := make(chan error, 1)
	go func() {
		serveErr <- httpSrv.ListenAndServe()
	}()

	select {
	case <-rootCtx.Done():
		log.Info("shutdown signal received")
	case err := <-serveErr:
		if err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Error("server error", "err", err)
		}
	}

	shutCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := httpSrv.Shutdown(shutCtx); err != nil {
		log.Warn("server shutdown", "err", err)
	}
}

type server struct {
	store        *storage.Store
	kg           *sql.DB
	badgeBase    string
	minListings  int
	log          *slog.Logger
	refreshToken string
}

func (s *server) handleHealth(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(`{"status":"ok"}`))
}

func (s *server) handleProfile(w http.ResponseWriter, r *http.Request) {
	dealerID := strings.TrimPrefix(r.URL.Path, "/trust/profile/")
	if !dealerIDPattern.MatchString(dealerID) {
		s.jsonError(w, r, "invalid dealer_id", nil, http.StatusBadRequest)
		return
	}
	p, err := s.store.Get(r.Context(), dealerID)
	if err != nil {
		s.jsonError(w, r, "lookup failed", err, http.StatusInternalServerError)
		return
	}
	if p == nil {
		p, err = s.computeAndStore(r.Context(), dealerID)
		if err != nil {
			s.jsonError(w, r, "dealer not found", err, http.StatusNotFound)
			return
		}
	}
	s.jsonOK(w, p)
}

func (s *server) handleBadge(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimPrefix(r.URL.Path, "/trust/badge/")
	dealerID := strings.TrimSuffix(path, ".svg")
	if !dealerIDPattern.MatchString(dealerID) {
		http.Error(w, "invalid dealer_id", http.StatusBadRequest)
		return
	}
	tier := "unverified"
	if p, err := s.store.Get(r.Context(), dealerID); err == nil && p != nil {
		tier = p.TrustTier
	} else if err != nil {
		s.log.Warn("badge: store.Get", "dealer_id", dealerID, "err", err)
	}
	svg, err := badge.Generate(tier)
	if err != nil {
		http.Error(w, "badge generation failed", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", badge.ContentType())
	w.Header().Set("Cache-Control", "public, max-age=3600")
	_, _ = w.Write(svg)
}

func (s *server) handleVerify(w http.ResponseWriter, r *http.Request) {
	hash := strings.TrimPrefix(r.URL.Path, "/trust/verify/")
	if !profileHashPattern.MatchString(strings.ToLower(hash)) {
		s.jsonError(w, r, "invalid profile_hash", nil, http.StatusBadRequest)
		return
	}
	p, err := s.store.GetByHash(r.Context(), strings.ToLower(hash))
	if err != nil {
		s.jsonError(w, r, "lookup failed", err, http.StatusInternalServerError)
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
	if !s.authorizeRefresh(r) {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	dealerID := strings.TrimPrefix(r.URL.Path, "/trust/refresh/")
	if !dealerIDPattern.MatchString(dealerID) {
		s.jsonError(w, r, "invalid dealer_id", nil, http.StatusBadRequest)
		return
	}
	p, err := s.computeAndStore(r.Context(), dealerID)
	if err != nil {
		s.jsonError(w, r, "dealer not found", err, http.StatusNotFound)
		return
	}
	s.jsonOK(w, p)
}

// authorizeRefresh enforces a bearer-token check on /trust/refresh. When the
// CARDEX_TRUST_REFRESH_TOKEN env var is empty, the endpoint is refused
// outright (closed-by-default) rather than accidentally exposed.
func (s *server) authorizeRefresh(r *http.Request) bool {
	if s.refreshToken == "" {
		return false
	}
	auth := r.Header.Get("Authorization")
	prefix := "Bearer "
	if !strings.HasPrefix(auth, prefix) {
		return false
	}
	got := strings.TrimPrefix(auth, prefix)
	return subtleStringEq(got, s.refreshToken)
}

// subtleStringEq is a constant-time string comparison to avoid timing leaks.
func subtleStringEq(a, b string) bool {
	if len(a) != len(b) {
		return false
	}
	var v byte
	for i := 0; i < len(a); i++ {
		v |= a[i] ^ b[i]
	}
	return v == 0
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
		s.jsonError(w, r, "list failed", err, http.StatusInternalServerError)
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
	if err := json.NewEncoder(w).Encode(v); err != nil {
		s.log.Warn("encode response", "err", err)
	}
}

// jsonError logs the internal error (with caller context) and returns a
// short, non-disclosing message to the client. Stack traces / SQL details
// never leave the process.
func (s *server) jsonError(w http.ResponseWriter, r *http.Request, msg string, internal error, code int) {
	if internal != nil {
		s.log.Warn("http error",
			"path", r.URL.Path,
			"method", r.Method,
			"status", code,
			"err", internal)
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	if err := json.NewEncoder(w).Encode(map[string]string{"error": msg}); err != nil {
		s.log.Warn("encode error response", "err", err)
	}
}

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
