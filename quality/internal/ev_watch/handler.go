package ev_watch

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"log/slog"
	"math"
	"net/http"
	"strconv"
	"strings"
	"time"
)

// Handler serves the EV watch HTTP API.
type Handler struct {
	db  *sql.DB
	log *slog.Logger
}

// NewHandler returns an HTTP handler backed by db.
func NewHandler(db *sql.DB, log *slog.Logger) *Handler {
	return &Handler{db: db, log: log}
}

// Register mounts the EV watch routes on mux.
func (h *Handler) Register(mux *http.ServeMux) {
	mux.HandleFunc("/ev-watch/anomalies", h.serveAnomalies)
	mux.HandleFunc("/ev-watch/cohort", h.serveCohort)
	mux.HandleFunc("/ev-watch/run", h.serveRun)
}

// ── GET /ev-watch/anomalies ───────────────────────────────────────────────────
//
// Query params: country, make, model, year, min_z, max_z, min_confidence, limit

type anomalyResponse struct {
	Count    int              `json:"count"`
	Anomalies []anomalyJSON  `json:"anomalies"`
}

type anomalyJSON struct {
	ListingID       string  `json:"listing_id"`
	VIN             string  `json:"vin,omitempty"`
	Make            string  `json:"make"`
	Model           string  `json:"model"`
	Year            int     `json:"year"`
	Country         string  `json:"country"`
	PriceEUR        float64 `json:"price_eur"`
	MileageKM       int     `json:"mileage_km"`
	CohortSize      int     `json:"cohort_size"`
	ZScore          float64 `json:"z_score"`
	AnomalyFlag     bool    `json:"anomaly_flag"`
	Confidence      float64 `json:"confidence"`
	EstimatedSoH    string  `json:"estimated_soh"`
	DetectedAt      string  `json:"detected_at"`
}

func (h *Handler) serveAnomalies(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	q := r.URL.Query()
	country := strings.ToUpper(q.Get("country"))
	make_  := strings.ToUpper(q.Get("make"))
	model  := strings.ToUpper(q.Get("model"))
	year   := parseInt(q.Get("year"), 0)
	minConf := parseFloat(q.Get("min_confidence"), 0)
	minZ    := parseFloat(q.Get("min_z"), math.NaN())
	maxZ    := parseFloat(q.Get("max_z"), math.NaN())
	limit  := parseInt(q.Get("limit"), 100)
	anomalyOnly := q.Get("anomaly_only") != "false" // default true

	var conds []string
	var args []any

	if anomalyOnly {
		conds = append(conds, "anomaly_flag = 1")
	}
	if country != "" {
		conds = append(conds, "country = ?")
		args = append(args, country)
	}
	if make_ != "" {
		conds = append(conds, "make = ?")
		args = append(args, make_)
	}
	if model != "" {
		conds = append(conds, "model LIKE ?")
		args = append(args, "%"+model+"%")
	}
	if year > 0 {
		conds = append(conds, "year = ?")
		args = append(args, year)
	}
	if minConf > 0 {
		conds = append(conds, "confidence >= ?")
		args = append(args, minConf)
	}
	if !math.IsNaN(minZ) {
		conds = append(conds, "z_score >= ?")
		args = append(args, minZ)
	}
	if !math.IsNaN(maxZ) {
		conds = append(conds, "z_score <= ?")
		args = append(args, maxZ)
	}

	where := ""
	if len(conds) > 0 {
		where = "WHERE " + strings.Join(conds, " AND ")
	}
	args = append(args, limit)

	query := fmt.Sprintf(`
		SELECT vehicle_id, COALESCE(vin,''), make, model, year, country,
		       price_cents, mileage_km, cohort_size,
		       z_score, anomaly_flag, confidence, estimated_soh, detected_at
		FROM ev_anomaly_scores
		%s ORDER BY z_score ASC LIMIT ?`, where)

	rows, err := h.db.QueryContext(r.Context(), query, args...)
	if err != nil {
		h.log.Error("ev-watch anomalies query", "err", err)
		http.Error(w, "database error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var results []anomalyJSON
	for rows.Next() {
		var a anomalyJSON
		var priceCents int64
		var flagInt int
		var detectedAt string
		if err := rows.Scan(
			&a.ListingID, &a.VIN, &a.Make, &a.Model, &a.Year, &a.Country,
			&priceCents, &a.MileageKM, &a.CohortSize,
			&a.ZScore, &flagInt, &a.Confidence, &a.EstimatedSoH, &detectedAt,
		); err != nil {
			h.log.Error("ev-watch scan", "err", err)
			continue
		}
		a.PriceEUR = float64(priceCents) / 100.0
		a.AnomalyFlag = flagInt == 1
		a.DetectedAt = detectedAt
		results = append(results, a)
	}
	if err := rows.Err(); err != nil {
		http.Error(w, "database error", http.StatusInternalServerError)
		return
	}
	if results == nil {
		results = []anomalyJSON{}
	}

	writeJSON(w, anomalyResponse{Count: len(results), Anomalies: results})
}

// ── GET /ev-watch/cohort ──────────────────────────────────────────────────────
//
// Query params: make (required), model (required), year, country

type cohortResponse struct {
	Make          string    `json:"make"`
	Model         string    `json:"model"`
	Year          int       `json:"year,omitempty"`
	Country       string    `json:"country,omitempty"`
	Count         int       `json:"count"`
	MeanPriceEUR  float64   `json:"mean_price_eur"`
	StdDevEUR     float64   `json:"std_dev_eur"`
	MinPriceEUR   float64   `json:"min_price_eur"`
	MaxPriceEUR   float64   `json:"max_price_eur"`
	AnomalyCount  int       `json:"anomaly_count"`
	SevereCount   int       `json:"severe_count"`
	ComputedAt    string    `json:"computed_at"`
}

func (h *Handler) serveCohort(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	q := r.URL.Query()
	make_   := strings.ToUpper(q.Get("make"))
	model   := strings.ToUpper(q.Get("model"))
	year    := parseInt(q.Get("year"), 0)
	country := strings.ToUpper(q.Get("country"))

	if make_ == "" || model == "" {
		http.Error(w, "make and model are required", http.StatusBadRequest)
		return
	}

	var conds = []string{"make = ?", "model = ?"}
	var args = []any{make_, model}
	if year > 0 {
		conds = append(conds, "year = ?")
		args = append(args, year)
	}
	if country != "" {
		conds = append(conds, "country = ?")
		args = append(args, country)
	}
	where := "WHERE " + strings.Join(conds, " AND ")

	row := h.db.QueryRowContext(r.Context(), fmt.Sprintf(`
		SELECT
			COUNT(*),
			AVG(price_cents) / 100.0,
			AVG(cohort_std_dev),
			MIN(price_cents) / 100.0,
			MAX(price_cents) / 100.0,
			SUM(CASE WHEN anomaly_flag = 1 THEN 1 ELSE 0 END),
			SUM(CASE WHEN z_score < -2.0 THEN 1 ELSE 0 END),
			MAX(detected_at)
		FROM ev_anomaly_scores %s`, where), args...)

	var resp cohortResponse
	resp.Make = make_
	resp.Model = model
	resp.Year = year
	resp.Country = country

	var computedAt sql.NullString
	if err := row.Scan(
		&resp.Count, &resp.MeanPriceEUR, &resp.StdDevEUR,
		&resp.MinPriceEUR, &resp.MaxPriceEUR,
		&resp.AnomalyCount, &resp.SevereCount, &computedAt,
	); err != nil {
		if err == sql.ErrNoRows {
			http.Error(w, "cohort not found — run analysis first", http.StatusNotFound)
			return
		}
		h.log.Error("ev-watch cohort query", "err", err)
		http.Error(w, "database error", http.StatusInternalServerError)
		return
	}
	resp.ComputedAt = computedAt.String
	writeJSON(w, resp)
}

// ── POST /ev-watch/run ────────────────────────────────────────────────────────

func (h *Handler) serveRun(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	start := time.Now()
	a := NewAnalyzer(h.db)
	scores, err := a.RunAnalysis(r.Context())
	dur := time.Since(start)
	metricAnalysisDuration.Observe(dur.Seconds())

	if err != nil {
		h.log.Error("ev-watch run analysis", "err", err)
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	anomalies := 0
	for _, s := range scores {
		if s.AnomalyFlag {
			anomalies++
		}
	}
	writeJSON(w, map[string]any{
		"scored":     len(scores),
		"anomalies":  anomalies,
		"duration_ms": dur.Milliseconds(),
	})
}

// ── Helpers ───────────────────────────────────────────────────────────────────

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(v); err != nil {
		http.Error(w, "encode error", http.StatusInternalServerError)
	}
}

func parseInt(s string, def int) int {
	if s == "" {
		return def
	}
	n, err := strconv.Atoi(s)
	if err != nil {
		return def
	}
	return n
}

func parseFloat(s string, def float64) float64 {
	if s == "" {
		return def
	}
	f, err := strconv.ParseFloat(s, 64)
	if err != nil {
		return def
	}
	return f
}

// RunAnalysisWithContext is called from the quality service cron loop.
func RunAnalysisWithContext(ctx context.Context, db *sql.DB, log *slog.Logger) error {
	start := time.Now()
	a := NewAnalyzer(db)
	scores, err := a.RunAnalysis(ctx)
	dur := time.Since(start)
	metricAnalysisDuration.Observe(dur.Seconds())

	if err != nil {
		return fmt.Errorf("ev_watch analysis: %w", err)
	}

	anomalies := 0
	severe := 0
	for _, s := range scores {
		if s.AnomalyFlag {
			anomalies++
		}
		if s.ZScore < SevereAnomalyZThreshold && s.CohortSize >= SevereAnomalyCohortMin {
			severe++
			log.Warn("EV severe anomaly detected",
				"listing_id", s.ListingID,
				"vin", s.VIN,
				"make", s.Make,
				"model", s.Model,
				"year", s.Year,
				"country", s.Country,
				"z_score", fmt.Sprintf("%.2f", s.ZScore),
				"price_eur", fmt.Sprintf("%.0f", float64(s.PriceCents)/100),
				"cohort_size", s.CohortSize,
			)
		}
	}

	log.Info("ev_watch analysis complete",
		"scored", len(scores),
		"anomalies", anomalies,
		"severe", severe,
		"duration_ms", dur.Milliseconds(),
	)
	return nil
}
