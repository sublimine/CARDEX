package alerts

import (
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"net/url"
	"strings"
	"time"

	"cardex.eu/api/internal/httpx"
	"cardex.eu/api/internal/redisx"
	"cardex.eu/api/internal/restparams"
)

// Handler serves the alert CRUD endpoints.
type Handler struct {
	store *Store
	redis *redisx.Client
	log   *slog.Logger
	now   func() time.Time
}

// NewHandler builds an alerts Handler.
func NewHandler(s *Store, r *redisx.Client, log *slog.Logger) *Handler {
	return &Handler{store: s, redis: r, log: log, now: time.Now}
}

// owner extracts the authenticated key owner from the request context.
func owner(r *http.Request) string { return httpx.KeyNameFromContext(r.Context()) }

// Create handles POST /api/v1/alerts.
func (h *Handler) Create(w http.ResponseWriter, r *http.Request) {
	var req CreateRequest
	dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16<<10))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&req); err != nil {
		httpx.WriteError(w, http.StatusBadRequest, "invalid_body", "request body must be valid JSON: "+err.Error())
		return
	}

	a, err := h.validate(req, r)
	if err != nil {
		httpx.WriteError(w, http.StatusBadRequest, "invalid_alert", err.Error())
		return
	}

	if err := h.store.Create(r.Context(), a); err != nil {
		h.log.Error("create alert failed", "err", err, "request_id", httpx.RequestID(r.Context()))
		httpx.WriteError(w, http.StatusInternalServerError, "create_failed", "failed to create alert")
		return
	}
	httpx.WriteJSON(w, http.StatusCreated, a)
}

// List handles GET /api/v1/alerts.
func (h *Handler) List(w http.ResponseWriter, r *http.Request) {
	list, err := h.store.List(r.Context(), owner(r))
	if err != nil {
		h.log.Error("list alerts failed", "err", err)
		httpx.WriteError(w, http.StatusInternalServerError, "list_failed", "failed to list alerts")
		return
	}
	for i := range list {
		h.enrichLastFired(r, &list[i])
	}
	if list == nil {
		list = []Alert{}
	}
	httpx.WriteJSON(w, http.StatusOK, map[string]any{"alerts": list, "total": len(list)})
}

// GetOne handles GET /api/v1/alerts/{id}.
func (h *Handler) GetOne(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	a, err := h.store.Get(r.Context(), id, owner(r))
	if errors.Is(err, ErrNotFound) {
		httpx.WriteError(w, http.StatusNotFound, "not_found", "alert not found")
		return
	}
	if err != nil {
		h.log.Error("get alert failed", "err", err)
		httpx.WriteError(w, http.StatusInternalServerError, "get_failed", "failed to fetch alert")
		return
	}
	h.enrichLastFired(r, &a)
	httpx.WriteJSON(w, http.StatusOK, a)
}

// Delete handles DELETE /api/v1/alerts/{id}.
func (h *Handler) Delete(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	err := h.store.Delete(r.Context(), id, owner(r))
	if errors.Is(err, ErrNotFound) {
		httpx.WriteError(w, http.StatusNotFound, "not_found", "alert not found")
		return
	}
	if err != nil {
		h.log.Error("delete alert failed", "err", err)
		httpx.WriteError(w, http.StatusInternalServerError, "delete_failed", "failed to delete alert")
		return
	}
	if h.redis != nil {
		_ = h.redis.DeleteAlertState(r.Context(), id)
	}
	w.WriteHeader(http.StatusNoContent)
}

// enrichLastFired populates a.LastFiredAt from Redis (best effort).
func (h *Handler) enrichLastFired(r *http.Request, a *Alert) {
	if h.redis == nil {
		return
	}
	if t, err := h.redis.AlertLastFired(r.Context(), a.ID); err == nil && !t.IsZero() {
		ft := t
		a.LastFiredAt = &ft
	}
}

// validate converts a CreateRequest into a stored Alert, enforcing invariants.
func (h *Handler) validate(req CreateRequest, r *http.Request) (Alert, error) {
	vehMake := strings.TrimSpace(req.Make)
	vehModel := strings.TrimSpace(req.Model)
	if vehMake == "" || vehModel == "" {
		return Alert{}, errors.New("'make' and 'model' are required")
	}
	if len(vehMake) > maxFieldLen || len(vehModel) > maxFieldLen {
		return Alert{}, errors.New("'make' and 'model' must be at most 64 characters")
	}
	if hasCRLF(vehMake) || hasCRLF(vehModel) || hasCRLF(req.Fuel) {
		return Alert{}, errors.New("'make', 'model' and 'fuel' must not contain line breaks")
	}
	if req.WebhookURL == "" && req.Email == "" {
		return Alert{}, errors.New("at least one delivery channel is required: 'webhook_url' or 'email'")
	}
	if req.WebhookURL != "" {
		u, err := url.ParseRequestURI(req.WebhookURL)
		if err != nil || (u.Scheme != "http" && u.Scheme != "https") {
			return Alert{}, errors.New("'webhook_url' must be a valid http(s) URL")
		}
	}
	if req.Email != "" && (!strings.Contains(req.Email, "@") || hasCRLF(req.Email) || len(req.Email) > 254) {
		return Alert{}, errors.New("'email' must be a valid email address")
	}
	if req.YearMin != 0 && req.YearMax != 0 && req.YearMin > req.YearMax {
		return Alert{}, errors.New("year_min cannot exceed year_max")
	}
	if req.MileageMin != 0 && req.MileageMax != 0 && req.MileageMin > req.MileageMax {
		return Alert{}, errors.New("mileage_min cannot exceed mileage_max")
	}
	buy, err := validateCountries(req.BuyCountries)
	if err != nil {
		return Alert{}, err
	}
	sell, err := validateCountries(req.SellCountries)
	if err != nil {
		return Alert{}, err
	}
	margin := req.MinMarginPct
	if margin < 0 {
		return Alert{}, errors.New("min_margin_pct must be non-negative")
	}
	if margin == 0 {
		margin = 5
	}

	return Alert{
		ID:            newID(),
		Owner:         owner(r),
		Make:          vehMake,
		Model:         vehModel,
		YearMin:       req.YearMin,
		YearMax:       req.YearMax,
		Fuel:          strings.TrimSpace(req.Fuel),
		MileageMin:    req.MileageMin,
		MileageMax:    req.MileageMax,
		BuyCountries:  buy,
		SellCountries: sell,
		MinMarginPct:  margin,
		WebhookURL:    req.WebhookURL,
		Email:         req.Email,
		Active:        true,
		CreatedAt:     h.now().UTC(),
	}, nil
}

// maxFieldLen bounds free-text make/model to keep ILIKE scans cheap.
const maxFieldLen = 64

// hasCRLF reports whether s contains a carriage return or line feed.
func hasCRLF(s string) bool { return strings.ContainsAny(s, "\r\n") }

// validateCountries upper-cases and checks country codes against the supported set.
func validateCountries(in []string) ([]string, error) {
	if len(in) == 0 {
		return []string{}, nil
	}
	out := make([]string, 0, len(in))
	for _, c := range in {
		code := strings.ToUpper(strings.TrimSpace(c))
		if code == "" {
			continue
		}
		if !restparams.SupportedCountries[code] {
			return nil, errors.New("unsupported country " + code + "; supported: DE, FR, ES, NL, BE, CH")
		}
		out = append(out, code)
	}
	return out, nil
}
