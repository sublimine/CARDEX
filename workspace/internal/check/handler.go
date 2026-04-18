package check

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"
)

// Handler exposes the vehicle history check endpoints.
// Routes:
//
//	GET /api/v1/check/{vin}         — full report
//	GET /api/v1/check/{vin}/summary — VIN decode + alerts only
type Handler struct {
	engine    *Engine
	cache     *Cache
	anonLimit *RateLimiter // unauthenticated callers: 10 req/hour
}

// NewHandler creates the HTTP handler with the default rate limit (10 req/hour for anon).
func NewHandler(engine *Engine, cache *Cache) *Handler {
	return &Handler{
		engine:    engine,
		cache:     cache,
		anonLimit: NewRateLimiter(10, time.Hour),
	}
}

// NewHandlerWithLimit creates an HTTP handler with a custom rate limiter (for tests).
func NewHandlerWithLimit(engine *Engine, cache *Cache, rl *RateLimiter) *Handler {
	return &Handler{
		engine:    engine,
		cache:     cache,
		anonLimit: rl,
	}
}

// Register mounts the check routes on mux without auth middleware (public).
func (h *Handler) Register(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/v1/check/{vin}", h.fullReport)
	mux.HandleFunc("GET /api/v1/check/{vin}/summary", h.summary)
}

// ── Handlers ──────────────────────────────────────────────────────────────────

func (h *Handler) fullReport(w http.ResponseWriter, r *http.Request) {
	vin, ok := h.validateVINParam(w, r)
	if !ok {
		return
	}
	ip := clientIPCheck(r)
	authenticated := r.Header.Get("Authorization") != ""
	if !authenticated && !h.anonLimit.Allow(ip) {
		jsonCheckErr(w, http.StatusTooManyRequests, "rate limit exceeded — 10 requests per hour for unauthenticated users")
		return
	}

	tenantID := r.Header.Get("X-Tenant-ID")

	// Check cache before generating.
	if cached, ok := h.cache.GetReport(r.Context(), vin); ok {
		h.cache.RecordRequest(r.Context(), vin, ip, tenantID, true)
		metricRequestsTotal.WithLabelValues("true").Inc()
		w.Header().Set("X-Cache-Hit", "true")
		w.Header().Set("X-Data-Sources", sourceHeader(cached.DataSources))
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(cached)
		return
	}

	report, err := h.engine.GenerateReport(r.Context(), vin)
	if err != nil {
		if errors.Is(err, ErrInvalidVIN) {
			jsonCheckErr(w, http.StatusBadRequest, err.Error())
			return
		}
		jsonCheckErr(w, http.StatusInternalServerError, "report generation failed")
		return
	}

	h.cache.RecordRequest(r.Context(), vin, ip, tenantID, false)
	w.Header().Set("X-Cache-Hit", "false")
	w.Header().Set("X-Data-Sources", sourceHeader(report.DataSources))
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(report)
}

// SummaryReport is a lightweight version of VehicleReport for the /summary endpoint.
type SummaryReport struct {
	VIN                string             `json:"vin"`
	DecodedVIN         *VINInfo           `json:"decoded_vin,omitempty"`
	GeneratedAt        time.Time          `json:"generated_at"`
	Alerts             []Alert            `json:"alerts"`
	MileageConsistency *ConsistencyScore  `json:"mileage_consistency,omitempty"`
	DataSources        []DataSource       `json:"data_sources"`
}

func (h *Handler) summary(w http.ResponseWriter, r *http.Request) {
	vin, ok := h.validateVINParam(w, r)
	if !ok {
		return
	}
	ip := clientIPCheck(r)
	authenticated := r.Header.Get("Authorization") != ""
	if !authenticated && !h.anonLimit.Allow(ip) {
		jsonCheckErr(w, http.StatusTooManyRequests, "rate limit exceeded")
		return
	}

	report, err := h.engine.GenerateReport(r.Context(), vin)
	if err != nil {
		if errors.Is(err, ErrInvalidVIN) {
			jsonCheckErr(w, http.StatusBadRequest, err.Error())
			return
		}
		jsonCheckErr(w, http.StatusInternalServerError, "report generation failed")
		return
	}

	summary := SummaryReport{
		VIN:                report.VIN,
		DecodedVIN:         report.DecodedVIN,
		GeneratedAt:        report.GeneratedAt,
		Alerts:             report.Alerts,
		MileageConsistency: report.MileageConsistency,
		DataSources:        report.DataSources,
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(summary)
}

// ── helpers ───────────────────────────────────────────────────────────────────

func (h *Handler) validateVINParam(w http.ResponseWriter, r *http.Request) (string, bool) {
	vin := strings.ToUpper(strings.TrimSpace(r.PathValue("vin")))
	if vin == "" {
		jsonCheckErr(w, http.StatusBadRequest, "VIN required")
		return "", false
	}
	if err := ValidateVIN(vin); err != nil {
		jsonCheckErr(w, http.StatusBadRequest, err.Error())
		return "", false
	}
	return vin, true
}

func sourceHeader(sources []DataSource) string {
	var parts []string
	for _, s := range sources {
		parts = append(parts, s.Country+":"+string(s.Status))
	}
	return strings.Join(parts, ",")
}

func clientIPCheck(r *http.Request) string {
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		return strings.SplitN(xff, ",", 2)[0]
	}
	ip := r.RemoteAddr
	if idx := strings.LastIndex(ip, ":"); idx != -1 {
		return ip[:idx]
	}
	return ip
}

func jsonCheckErr(w http.ResponseWriter, status int, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": msg})
}

