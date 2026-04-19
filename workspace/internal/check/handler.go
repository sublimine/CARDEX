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
	engine        *Engine
	cache         *Cache
	anonLimit     *RateLimiter         // unauthenticated callers: 10 req/hour
	isValidToken  func(string) bool    // nil = always treat as anonymous
}

// NewHandler creates the HTTP handler with the default rate limit (10 req/hour for anon).
// All callers are treated as anonymous — no JWT bypass.
func NewHandler(engine *Engine, cache *Cache) *Handler {
	return &Handler{
		engine:    engine,
		cache:     cache,
		anonLimit: NewRateLimiter(10, time.Hour),
	}
}

// NewHandlerWithValidator creates the HTTP handler with a JWT validator so that
// authenticated callers are exempt from the anonymous rate limit.
func NewHandlerWithValidator(engine *Engine, cache *Cache, isValid func(string) bool) *Handler {
	return &Handler{
		engine:       engine,
		cache:        cache,
		anonLimit:    NewRateLimiter(10, time.Hour),
		isValidToken: isValid,
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

// NewHandlerWithLimitAndValidator creates an HTTP handler with a custom rate limiter
// and a token validator (for integration tests that verify auth bypass behaviour).
func NewHandlerWithLimitAndValidator(engine *Engine, cache *Cache, rl *RateLimiter, isValid func(string) bool) *Handler {
	return &Handler{
		engine:       engine,
		cache:        cache,
		anonLimit:    rl,
		isValidToken: isValid,
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
	authenticated := h.isAuthenticated(r)
	if !authenticated && !h.anonLimit.Allow(ip) {
		w.Header().Set("Retry-After", "3600")
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
	tenantID := r.Header.Get("X-Tenant-ID")
	authenticated := h.isAuthenticated(r)
	if !authenticated && !h.anonLimit.Allow(ip) {
		w.Header().Set("Retry-After", "3600")
		jsonCheckErr(w, http.StatusTooManyRequests, "rate limit exceeded")
		return
	}

	// Check cache before generating.
	if cached, ok := h.cache.GetReport(r.Context(), vin); ok {
		h.cache.RecordRequest(r.Context(), vin, ip, tenantID, true)
		w.Header().Set("X-Cache-Hit", "true")
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(summaryFromReport(cached))
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
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(summaryFromReport(report))
}

func summaryFromReport(report *VehicleReport) SummaryReport {
	return SummaryReport{
		VIN:                report.VIN,
		DecodedVIN:         report.DecodedVIN,
		GeneratedAt:        report.GeneratedAt,
		Alerts:             report.Alerts,
		MileageConsistency: report.MileageConsistency,
		DataSources:        report.DataSources,
	}
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

// isAuthenticated returns true only when the request carries a bearer token
// that the configured validator accepts. Presence of any non-empty header is
// not sufficient — the token must be cryptographically valid.
func (h *Handler) isAuthenticated(r *http.Request) bool {
	if h.isValidToken == nil {
		return false
	}
	bearer := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	if bearer == "" || bearer == r.Header.Get("Authorization") {
		return false
	}
	return h.isValidToken(bearer)
}

func clientIPCheck(r *http.Request) string {
	// X-Real-IP is set by the reverse proxy (nginx/traefik) and cannot be
	// forged by the client — use it when present.
	if xri := strings.TrimSpace(r.Header.Get("X-Real-IP")); xri != "" {
		return xri
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

