package inbox

import (
	"database/sql"
	"encoding/json"
	"log/slog"
	"net/http"
	"strings"
	"time"
)

// Server exposes the inbox HTTP API.
type Server struct {
	convs     *ConversationStore
	templates *TemplateStore
	reply     *ReplyEngine
	proc      *Processor
	web       *WebhookSource
	manual    *ManualSource
	log       *slog.Logger
}

// NewServer wires up all inbox components and returns a ready server.
func NewServer(db *sql.DB, smtpCfg SMTPConfig, log *slog.Logger) *Server {
	convs := NewConversationStore(db)
	templates := NewTemplateStore(db)
	reply := NewReplyEngine(db, convs, templates, smtpCfg)
	proc := NewProcessor(db)
	return &Server{
		convs:     convs,
		templates: templates,
		reply:     reply,
		proc:      proc,
		web:       NewWebhookSource(),
		manual:    NewManualSource(),
		log:       log,
	}
}

// Handler returns the mux with all routes registered.
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /health", s.handleHealth)

	// Inbox (conversations)
	mux.HandleFunc("GET /api/v1/inbox", s.handleListInbox)
	mux.HandleFunc("GET /api/v1/inbox/{id}", s.handleGetConversation)
	mux.HandleFunc("POST /api/v1/inbox/{id}/reply", s.handleReply)
	mux.HandleFunc("PATCH /api/v1/inbox/{id}", s.handlePatchConversation)

	// Templates
	mux.HandleFunc("GET /api/v1/templates", s.handleListTemplates)
	mux.HandleFunc("POST /api/v1/templates", s.handleCreateTemplate)
	mux.HandleFunc("PUT /api/v1/templates/{id}", s.handleUpdateTemplate)

	// Ingestion endpoints
	mux.HandleFunc("POST /api/v1/ingest/web", s.web.IngestHandler())
	mux.HandleFunc("POST /api/v1/ingest/manual", s.handleManualIngest)

	return mux
}

// ListenAndServe starts the HTTP server.
func (s *Server) ListenAndServe(addr string) error {
	s.log.Info("inbox server listening", "addr", addr)
	srv := &http.Server{
		Addr:         addr,
		Handler:      s.Handler(),
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
	}
	return srv.ListenAndServe()
}

// ── handlers ──────────────────────────────────────────────────────────────────

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok", "time": time.Now().UTC().Format(time.RFC3339)})
}

func (s *Server) handleListInbox(w http.ResponseWriter, r *http.Request) {
	tenantID := tenantFromRequest(r)
	q := ListInboxQuery{
		Status:   r.URL.Query().Get("status"),
		Platform: r.URL.Query().Get("platform"),
	}
	if vid := r.URL.Query().Get("vehicle_id"); vid != "" {
		q.VehicleID = vid
	}
	if u := r.URL.Query().Get("unread"); u == "true" {
		t := true
		q.Unread = &t
	} else if u == "false" {
		f := false
		q.Unread = &f
	}
	convs, err := s.convs.List(tenantID, q)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, convs)
}

func (s *Server) handleGetConversation(w http.ResponseWriter, r *http.Request) {
	tenantID := tenantFromRequest(r)
	id := r.PathValue("id")
	conv, msgs, err := s.convs.Get(tenantID, id)
	if err != nil {
		writeErr(w, http.StatusNotFound, err)
		return
	}
	writeJSON(w, http.StatusOK, ConversationWithMessages{Conversation: conv, Messages: msgs})
}

func (s *Server) handleReply(w http.ResponseWriter, r *http.Request) {
	tenantID := tenantFromRequest(r)
	id := r.PathValue("id")

	var req ReplyRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeErr(w, http.StatusBadRequest, err)
		return
	}
	if req.Body == "" && req.TemplateID == "" {
		writeErr(w, http.StatusBadRequest, errMsg("body or template_id required"))
		return
	}
	if req.SendVia == "" {
		req.SendVia = "manual"
	}

	msg, err := s.reply.Reply(r.Context(), tenantID, id, req)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusCreated, msg)
}

func (s *Server) handlePatchConversation(w http.ResponseWriter, r *http.Request) {
	tenantID := tenantFromRequest(r)
	id := r.PathValue("id")

	var req PatchConversationRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeErr(w, http.StatusBadRequest, err)
		return
	}
	if err := s.convs.Patch(tenantID, id, req); err != nil {
		writeErr(w, http.StatusInternalServerError, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) handleListTemplates(w http.ResponseWriter, r *http.Request) {
	tenantID := tenantFromRequest(r)
	lang := r.URL.Query().Get("lang")
	templates, err := s.templates.List(tenantID, lang)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, templates)
}

func (s *Server) handleCreateTemplate(w http.ResponseWriter, r *http.Request) {
	tenantID := tenantFromRequest(r)
	var t Template
	if err := json.NewDecoder(r.Body).Decode(&t); err != nil {
		writeErr(w, http.StatusBadRequest, err)
		return
	}
	t.TenantID = tenantID
	t.IsSystem = false
	if err := s.templates.Create(&t); err != nil {
		writeErr(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusCreated, t)
}

func (s *Server) handleUpdateTemplate(w http.ResponseWriter, r *http.Request) {
	tenantID := tenantFromRequest(r)
	id := r.PathValue("id")
	var req struct {
		Subject string `json:"subject"`
		Body    string `json:"body"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeErr(w, http.StatusBadRequest, err)
		return
	}
	if err := s.templates.Update(tenantID, id, req.Subject, req.Body); err != nil {
		writeErr(w, http.StatusNotFound, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) handleManualIngest(w http.ResponseWriter, r *http.Request) {
	tenantID := tenantFromRequest(r)
	var raw RawInquiry
	if err := json.NewDecoder(r.Body).Decode(&raw); err != nil {
		writeErr(w, http.StatusBadRequest, err)
		return
	}
	raw.SourcePlatform = "manual"
	if raw.ReceivedAt.IsZero() {
		raw.ReceivedAt = time.Now().UTC()
	}
	conv, err := s.proc.Process(r.Context(), tenantID, raw)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusCreated, conv)
}

// ── helpers ────────────────────────────────────────────────────────────────────

func tenantFromRequest(r *http.Request) string {
	if t := r.Header.Get("X-Tenant-ID"); t != "" {
		return t
	}
	// Fallback: parse from URL prefix /api/v1/tenants/{id}/...
	parts := strings.Split(r.URL.Path, "/")
	for i, p := range parts {
		if p == "tenants" && i+1 < len(parts) {
			return parts[i+1]
		}
	}
	return "default"
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeErr(w http.ResponseWriter, status int, err error) {
	writeJSON(w, status, map[string]string{"error": err.Error()})
}

type errMsg string

func (e errMsg) Error() string { return string(e) }
