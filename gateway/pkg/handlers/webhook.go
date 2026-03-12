// Package handlers implements HTTP request handlers for the gateway.
package handlers

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"math"
	"net/http"
	"time"

	cardexhmac "github.com/cardex/gateway/pkg/hmac"
	"github.com/redis/go-redis/v9"
)

// StreamAdder adds entries to a Redis stream. Implemented by redis.Client; mock for tests.
type StreamAdder interface {
	AddToStream(ctx context.Context, stream string, values map[string]interface{}) (string, error)
}

// RateLimiter checks rate limits. Implemented by ratelimit.Limiter; mock for tests.
type RateLimiter interface {
	Allow(ctx context.Context, key string, maxTokens int, refillRate float64) (bool, error)
}

// RedisStreamAdapter adapts redis.Client to StreamAdder.
type RedisStreamAdapter struct {
	RDB *redis.Client
}

// AddToStream implements StreamAdder.
func (a *RedisStreamAdapter) AddToStream(ctx context.Context, stream string, values map[string]interface{}) (string, error) {
	return a.RDB.XAdd(ctx, &redis.XAddArgs{Stream: stream, Values: values}).Result()
}

// IngestPayload represents the expected JSON structure from B2B partners.
type IngestPayload struct {
	PartnerID string    `json:"partner_id"`
	Timestamp time.Time `json:"timestamp"`
	Vehicles  []Vehicle `json:"vehicles"`
}

// Vehicle represents a single vehicle data entry from a B2B feed.
type Vehicle struct {
	VIN          string  `json:"vin,omitempty"`
	SourceID     string  `json:"source_id"`
	Make         string  `json:"make"`
	Model        string  `json:"model"`
	Year         int     `json:"year"`
	MileageKM    int     `json:"mileage_km"`
	Color        string  `json:"color,omitempty"`
	FuelType     string  `json:"fuel_type,omitempty"`
	Transmission string  `json:"transmission,omitempty"`
	CO2GKM       int     `json:"co2_gkm,omitempty"`
	PowerKW      int     `json:"power_kw,omitempty"`
	PriceRaw     float64 `json:"price_raw"`
	CurrencyRaw  string  `json:"currency_raw"`
	Lat          float64 `json:"lat,omitempty"`
	Lng          float64 `json:"lng,omitempty"`
	Description  string  `json:"description,omitempty"`
	SellerType   string  `json:"seller_type,omitempty"` // DEALER, FLEET, INDIVIDUAL
	SellerVATID  string  `json:"seller_vat_id,omitempty"`
}

// WebhookHandler processes incoming B2B webhook requests.
type WebhookHandler struct {
	streamAdder  StreamAdder
	limiter      RateLimiter
	secrets      map[string]string // partner_id → HMAC secret
	maxReplayAge time.Duration
}

// NewWebhookHandler creates a new webhook handler with the given dependencies.
func NewWebhookHandler(streamAdder StreamAdder, limiter RateLimiter, secrets map[string]string, maxReplayAge time.Duration) *WebhookHandler {
	return &WebhookHandler{
		streamAdder:  streamAdder,
		limiter:      limiter,
		secrets:      secrets,
		maxReplayAge: maxReplayAge,
	}
}

// HandleIngest processes a B2B webhook ingest request.
func (h *WebhookHandler) HandleIngest(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	start := time.Now()

	// 1. Read body
	body, err := io.ReadAll(io.LimitReader(r.Body, 10<<20)) // 10MB max
	if err != nil {
		slog.Error("phase3: body read failed", "error", err)
		http.Error(w, "bad request", http.StatusBadRequest)
		return
	}

	// 2. Extract partner ID from header
	partnerID := r.Header.Get("X-Partner-ID")
	if partnerID == "" {
		slog.Warn("phase3: missing X-Partner-ID header", "ip", r.RemoteAddr)
		http.Error(w, "missing partner ID", http.StatusBadRequest)
		return
	}

	// 3. Rate limit check
	allowed, err := h.limiter.Allow(ctx, fmt.Sprintf("ratelimit:%s", partnerID), 1000, 16.67) // 1000/min
	if err != nil {
		slog.Error("phase3: rate limiter error", "error", err, "partner", partnerID)
		http.Error(w, "internal error", http.StatusInternalServerError)
		return
	}
	if !allowed {
		slog.Warn("phase3: rate limited", "partner", partnerID, "ip", r.RemoteAddr)
		w.Header().Set("Retry-After", "60")
		http.Error(w, "rate limited", http.StatusTooManyRequests)
		return
	}

	// 4. HMAC-SHA256 verification
	secret, ok := h.secrets[partnerID]
	if !ok {
		slog.Warn("phase3: unknown partner", "partner", partnerID, "ip", r.RemoteAddr)
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	signature := r.Header.Get("X-HMAC-SHA256")
	if err := cardexhmac.Verify(body, secret, signature); err != nil {
		slog.Warn("phase3: HMAC verification failed",
			"partner", partnerID, "error", err, "ip", r.RemoteAddr)
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}

	// 5. Parse payload
	var payload IngestPayload
	if err := json.Unmarshal(body, &payload); err != nil {
		slog.Warn("phase3: invalid JSON", "partner", partnerID, "error", err)
		http.Error(w, "invalid payload", http.StatusBadRequest)
		return
	}

	// 6. Anti-replay check
	if math.Abs(time.Since(payload.Timestamp).Seconds()) > h.maxReplayAge.Seconds() {
		slog.Warn("phase3: replay detected",
			"partner", partnerID, "payload_ts", payload.Timestamp, "drift_s", time.Since(payload.Timestamp).Seconds())
		http.Error(w, "replay detected", http.StatusBadRequest)
		return
	}

	// 7. Inject each vehicle into stream:ingestion_raw
	injected := 0
	for _, v := range payload.Vehicles {
		vJSON, err := json.Marshal(v)
		if err != nil {
			slog.Error("phase3: marshal vehicle failed", "error", err, "source_id", v.SourceID)
			continue
		}

		_, err = h.streamAdder.AddToStream(ctx, "stream:ingestion_raw", map[string]interface{}{
			"source":      partnerID,
			"channel":     "B2B_WEBHOOK",
			"payload":     string(vJSON),
			"received_at": time.Now().UTC().Format(time.RFC3339Nano),
		})
		if err != nil {
			slog.Error("phase3: XADD failed", "error", err, "stream", "stream:ingestion_raw")
			http.Error(w, "internal error", http.StatusServiceUnavailable)
			return
		}
		injected++
	}

	latency := time.Since(start)
	slog.Info("phase3: ingested",
		"partner", partnerID,
		"vehicles", injected,
		"latency_ms", latency.Milliseconds(),
	)

	w.WriteHeader(http.StatusAccepted)
	fmt.Fprintf(w, `{"accepted":%d}`, injected)
}
