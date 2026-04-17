package routes

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"
)

// Server is the HTTP API for the Routes disposition engine.
//
// Endpoints:
//   - GET  /health              → {"status":"ok", "db": "open"}
//   - GET  /routes/spread       → MarketSpread
//   - POST /routes/optimize     → DispositionPlan
//   - POST /routes/batch        → BatchPlan
type Server struct {
	optimizer     *Optimizer
	batchOpt      *BatchOptimizer
	spreadCalc    *SpreadCalculator
	db            *sql.DB
	log           *slog.Logger
}

// NewServer constructs a routes Server backed by the given SQLite database.
func NewServer(db *sql.DB, log *slog.Logger) *Server {
	if log == nil {
		log = slog.Default()
	}
	transport := DefaultTransportMatrix()
	tax := NewDefaultTaxEngine()
	opt := NewOptimizer(db, tax, transport)
	return &Server{
		optimizer:  opt,
		batchOpt:   NewBatchOptimizer(opt, defaultMaxFraction),
		spreadCalc: NewSpreadCalculator(db),
		db:         db,
		log:        log,
	}
}

// Handler returns an http.Handler for the routes API.
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", s.handleHealth)
	mux.HandleFunc("/routes/spread", s.handleSpread)
	mux.HandleFunc("/routes/optimize", s.handleOptimize)
	mux.HandleFunc("/routes/batch", s.handleBatch)
	return mux
}

// ListenAndServe starts the HTTP server on addr and blocks until it exits.
func (s *Server) ListenAndServe(addr string) error {
	s.log.Info("routes server listening", "addr", addr)
	srv := &http.Server{
		Addr:         addr,
		Handler:      s.Handler(),
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 60 * time.Second,
		IdleTimeout:  120 * time.Second,
	}
	return srv.ListenAndServe()
}

// ── Handlers ──────────────────────────────────────────────────────────────────

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	dbStatus := "open"
	if err := s.db.Ping(); err != nil {
		dbStatus = "error: " + err.Error()
	}
	writeJSON(w, http.StatusOK, map[string]string{
		"status": "ok",
		"db":     dbStatus,
		"time":   time.Now().Format(time.RFC3339),
	})
}

// GET /routes/spread?make=BMW&model=3er&year=2021[&km=45000&fuel=diesel]
func (s *Server) handleSpread(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	q := r.URL.Query()
	make_ := q.Get("make")
	model := q.Get("model")
	yearStr := q.Get("year")
	if make_ == "" || model == "" || yearStr == "" {
		writeError(w, http.StatusBadRequest, "make, model and year query parameters are required")
		return
	}
	year, err := strconv.Atoi(yearStr)
	if err != nil || year < 1900 || year > 2100 {
		writeError(w, http.StatusBadRequest, "year must be a valid integer")
		return
	}
	km := 0
	if kmStr := q.Get("km"); kmStr != "" {
		km, _ = strconv.Atoi(kmStr)
	}
	fuel := q.Get("fuel")

	spread, err := s.spreadCalc.Calculate(make_, model, year, km, fuel)
	if err != nil {
		s.log.Error("spread calculation failed", "err", err)
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, spread)
}

// POST /routes/optimize — body: OptimizeRequest → DispositionPlan
func (s *Server) handleOptimize(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var req OptimizeRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	req.Make = strings.TrimSpace(req.Make)
	req.Model = strings.TrimSpace(req.Model)
	req.CurrentCountry = strings.ToUpper(strings.TrimSpace(req.CurrentCountry))

	plan, err := s.optimizer.Optimize(req)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if len(plan.Routes) == 0 {
		writeError(w, http.StatusNotFound, fmt.Sprintf(
			"no market data found for %s %s %d in any country", req.Make, req.Model, req.Year))
		return
	}
	writeJSON(w, http.StatusOK, plan)
}

// POST /routes/batch — body: []VehicleInput → BatchPlan
func (s *Server) handleBatch(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var vehicles []VehicleInput
	if err := json.NewDecoder(r.Body).Decode(&vehicles); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	if err := validateBatchRequest(vehicles); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	plan, err := s.batchOpt.Optimize(vehicles)
	if err != nil {
		s.log.Error("batch optimization failed", "err", err)
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, plan)
}

// ── Helpers ───────────────────────────────────────────────────────────────────

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(v); err != nil {
		slog.Error("writeJSON encode failed", "err", err)
	}
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}
