package kanban

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
)

// Server mounts all kanban and calendar HTTP routes.
type Server struct {
	store *Store
	log   *slog.Logger
}

// NewServer returns a Server.
func NewServer(store *Store, log *slog.Logger) *Server {
	return &Server{store: store, log: log}
}

// Register mounts routes on mux without any middleware.
func (srv *Server) Register(mux *http.ServeMux) {
	mux.HandleFunc("/api/v1/kanban/columns", srv.handleColumns)
	mux.HandleFunc("/api/v1/kanban/columns/", srv.handleColumnByID)
	mux.HandleFunc("/api/v1/kanban/cards/", srv.handleCards)
	mux.HandleFunc("/api/v1/calendar/events", srv.handleEvents)
	mux.HandleFunc("/api/v1/calendar/events/upcoming", srv.handleUpcoming)
	mux.HandleFunc("/api/v1/calendar/events/", srv.handleEventByID)
}

// RegisterWithMiddleware mounts routes on mux, wrapping each handler with mw.
func (srv *Server) RegisterWithMiddleware(mux *http.ServeMux, mw func(http.Handler) http.Handler) {
	wrap := func(h http.HandlerFunc) http.Handler { return mw(h) }
	mux.Handle("/api/v1/kanban/columns", wrap(srv.handleColumns))
	mux.Handle("/api/v1/kanban/columns/", wrap(srv.handleColumnByID))
	mux.Handle("/api/v1/kanban/cards/", wrap(srv.handleCards))
	mux.Handle("/api/v1/calendar/events", wrap(srv.handleEvents))
	mux.Handle("/api/v1/calendar/events/upcoming", wrap(srv.handleUpcoming))
	mux.Handle("/api/v1/calendar/events/", wrap(srv.handleEventByID))
}

// ── Kanban handlers ───────────────────────────────────────────────────────────

// GET /api/v1/kanban/columns       → list columns with cards
// POST /api/v1/kanban/columns      → create custom column
func (srv *Server) handleColumns(w http.ResponseWriter, r *http.Request) {
	tenant := r.Header.Get("X-Tenant-ID")
	if tenant == "" {
		http.Error(w, "X-Tenant-ID required", http.StatusBadRequest)
		return
	}
	switch r.Method {
	case http.MethodGet:
		if err := srv.store.InitTenant(r.Context(), tenant); err != nil {
			srv.internalError(w, "init tenant", err)
			return
		}
		cols, err := srv.store.ListColumns(r.Context(), tenant)
		if err != nil {
			srv.internalError(w, "list columns", err)
			return
		}
		writeJSON(w, http.StatusOK, cols)
	case http.MethodPost:
		var body struct {
			Name         string `json:"name"`
			Color        string `json:"color"`
			VehicleLimit int    `json:"vehicle_limit"`
			Position     int    `json:"position"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			http.Error(w, "invalid JSON", http.StatusBadRequest)
			return
		}
		col, err := srv.store.CreateColumn(r.Context(), tenant, body.Name, body.Color, body.VehicleLimit, body.Position)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		writeJSON(w, http.StatusCreated, col)
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

// PUT /api/v1/kanban/columns/{id} → edit column
func (srv *Server) handleColumnByID(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPut {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	tenant := r.Header.Get("X-Tenant-ID")
	if tenant == "" {
		http.Error(w, "X-Tenant-ID required", http.StatusBadRequest)
		return
	}
	colID := strings.TrimPrefix(r.URL.Path, "/api/v1/kanban/columns/")
	if colID == "" {
		http.Error(w, "column id required", http.StatusBadRequest)
		return
	}
	var patch ColumnPatch
	if err := json.NewDecoder(r.Body).Decode(&patch); err != nil {
		http.Error(w, "invalid JSON", http.StatusBadRequest)
		return
	}
	col, err := srv.store.PatchColumn(r.Context(), tenant, colID, patch)
	if err != nil {
		if strings.Contains(err.Error(), "not found") {
			http.Error(w, err.Error(), http.StatusNotFound)
			return
		}
		srv.internalError(w, "patch column", err)
		return
	}
	writeJSON(w, http.StatusOK, col)
}

// PUT /api/v1/kanban/cards/{vehicleId}/move  → move card
// PUT /api/v1/kanban/cards/{vehicleId}       → patch card metadata
func (srv *Server) handleCards(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPut {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	tenant := r.Header.Get("X-Tenant-ID")
	if tenant == "" {
		http.Error(w, "X-Tenant-ID required", http.StatusBadRequest)
		return
	}
	// strip /api/v1/kanban/cards/
	rest := strings.TrimPrefix(r.URL.Path, "/api/v1/kanban/cards/")
	if strings.HasSuffix(rest, "/move") {
		vehicleID := strings.TrimSuffix(rest, "/move")
		var req MoveRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "invalid JSON", http.StatusBadRequest)
			return
		}
		card, err := srv.store.MoveCard(r.Context(), tenant, vehicleID, req)
		if err != nil {
			if strings.Contains(err.Error(), "not found") {
				http.Error(w, err.Error(), http.StatusNotFound)
				return
			}
			http.Error(w, err.Error(), http.StatusUnprocessableEntity)
			return
		}
		writeJSON(w, http.StatusOK, card)
	} else {
		vehicleID := rest
		var patch CardPatch
		if err := json.NewDecoder(r.Body).Decode(&patch); err != nil {
			http.Error(w, "invalid JSON", http.StatusBadRequest)
			return
		}
		card, err := srv.store.PatchCard(r.Context(), tenant, vehicleID, patch)
		if err != nil {
			if strings.Contains(err.Error(), "not found") {
				http.Error(w, err.Error(), http.StatusNotFound)
				return
			}
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		writeJSON(w, http.StatusOK, card)
	}
}

// ── Calendar handlers ─────────────────────────────────────────────────────────

// GET  /api/v1/calendar/events?from=&to= → list events in range
// POST /api/v1/calendar/events           → create event
func (srv *Server) handleEvents(w http.ResponseWriter, r *http.Request) {
	// Route upcoming before general events handler.
	if strings.HasSuffix(r.URL.Path, "/upcoming") {
		srv.handleUpcoming(w, r)
		return
	}
	tenant := r.Header.Get("X-Tenant-ID")
	if tenant == "" {
		http.Error(w, "X-Tenant-ID required", http.StatusBadRequest)
		return
	}
	switch r.Method {
	case http.MethodGet:
		from := r.URL.Query().Get("from")
		to := r.URL.Query().Get("to")
		events, err := srv.store.ListEvents(r.Context(), tenant, from, to)
		if err != nil {
			srv.internalError(w, "list events", err)
			return
		}
		if events == nil {
			events = []Event{}
		}
		writeJSON(w, http.StatusOK, events)
	case http.MethodPost:
		var e Event
		if err := json.NewDecoder(r.Body).Decode(&e); err != nil {
			http.Error(w, "invalid JSON", http.StatusBadRequest)
			return
		}
		e.TenantID = tenant
		created, err := srv.store.CreateEvent(r.Context(), e)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		writeJSON(w, http.StatusCreated, created)
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

// GET /api/v1/calendar/events/upcoming?days=7
func (srv *Server) handleUpcoming(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	tenant := r.Header.Get("X-Tenant-ID")
	if tenant == "" {
		http.Error(w, "X-Tenant-ID required", http.StatusBadRequest)
		return
	}
	days, _ := strconv.Atoi(r.URL.Query().Get("days"))
	events, err := srv.store.UpcomingEvents(r.Context(), tenant, days)
	if err != nil {
		srv.internalError(w, "upcoming events", err)
		return
	}
	if events == nil {
		events = []Event{}
	}
	writeJSON(w, http.StatusOK, events)
}

// PUT    /api/v1/calendar/events/{id} → edit
// DELETE /api/v1/calendar/events/{id} → cancel
func (srv *Server) handleEventByID(w http.ResponseWriter, r *http.Request) {
	tenant := r.Header.Get("X-Tenant-ID")
	if tenant == "" {
		http.Error(w, "X-Tenant-ID required", http.StatusBadRequest)
		return
	}
	// strip prefix; handle /upcoming path redirected here
	eventID := strings.TrimPrefix(r.URL.Path, "/api/v1/calendar/events/")
	if eventID == "" || eventID == "upcoming" {
		http.Error(w, "event id required", http.StatusBadRequest)
		return
	}
	switch r.Method {
	case http.MethodPut:
		var patch EventPatch
		if err := json.NewDecoder(r.Body).Decode(&patch); err != nil {
			http.Error(w, "invalid JSON", http.StatusBadRequest)
			return
		}
		event, err := srv.store.PatchEvent(r.Context(), tenant, eventID, patch)
		if err != nil {
			if strings.Contains(err.Error(), "not found") {
				http.Error(w, err.Error(), http.StatusNotFound)
				return
			}
			srv.internalError(w, "patch event", err)
			return
		}
		writeJSON(w, http.StatusOK, event)
	case http.MethodDelete:
		if err := srv.store.CancelEvent(r.Context(), tenant, eventID); err != nil {
			if strings.Contains(err.Error(), "not found") {
				http.Error(w, err.Error(), http.StatusNotFound)
				return
			}
			srv.internalError(w, "cancel event", err)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

// ── Helpers ───────────────────────────────────────────────────────────────────

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func (srv *Server) internalError(w http.ResponseWriter, op string, err error) {
	srv.log.Error("kanban server error", "op", op, "err", err)
	http.Error(w, "internal server error", http.StatusInternalServerError)
}
