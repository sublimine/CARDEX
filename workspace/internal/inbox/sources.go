package inbox

import (
	"context"
	"encoding/json"
	"net/http"
	"sync"
	"time"
)

// ── WebhookSource ──────────────────────────────────────────────────────────────

// WebhookSource accepts incoming inquiries via HTTP POST from the dealer's web form.
// It implements InquirySource via an in-memory mutex-protected queue:
// external callers POST a RawInquiry payload, which is drained on the next Poll call.
type WebhookSource struct {
	mu    sync.Mutex
	queue []RawInquiry
}

// NewWebhookSource creates a WebhookSource.
func NewWebhookSource() *WebhookSource { return &WebhookSource{} }

func (s *WebhookSource) Name() string { return "web" }

// Poll drains and returns all queued inquiries.
func (s *WebhookSource) Poll(_ context.Context, _ time.Time) ([]RawInquiry, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := s.queue
	s.queue = nil
	return out, nil
}

// IngestHandler returns an HTTP handler that enqueues incoming RawInquiry JSON.
// Wire this to POST /api/v1/ingest/web.
func (s *WebhookSource) IngestHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var raw RawInquiry
		if err := json.NewDecoder(r.Body).Decode(&raw); err != nil {
			http.Error(w, `{"error":"invalid JSON"}`, http.StatusBadRequest)
			return
		}
		raw.SourcePlatform = "web"
		if raw.ReceivedAt.IsZero() {
			raw.ReceivedAt = time.Now().UTC()
		}
		if raw.ExternalID == "" {
			raw.ExternalID = newID()
		}
		s.mu.Lock()
		s.queue = append(s.queue, raw)
		s.mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "accepted"})
	}
}

// ── ManualSource ───────────────────────────────────────────────────────────────

// ManualSource accepts inquiries submitted directly by the dealer
// (e.g. logging a phone call or showroom visit).
// Manual inquiries arrive via POST /api/v1/ingest/manual and are processed
// directly by the Server; Poll always returns empty.
type ManualSource struct{}

// NewManualSource creates a ManualSource.
func NewManualSource() *ManualSource { return &ManualSource{} }

func (s *ManualSource) Name() string { return "manual" }

// Poll is a no-op; manual inquiries are handled directly via HTTP.
func (s *ManualSource) Poll(_ context.Context, _ time.Time) ([]RawInquiry, error) {
	return nil, nil
}
