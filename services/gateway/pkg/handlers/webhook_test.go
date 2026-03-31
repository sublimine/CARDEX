// Package handlers implements HTTP request handlers for the gateway.
package handlers

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/cardex/gateway/pkg/hmac"
)

// mockStreamAdder implements StreamAdder for tests.
type mockStreamAdder struct {
	addFunc func(ctx context.Context, stream string, values map[string]interface{}) (string, error)
}

func (m *mockStreamAdder) AddToStream(ctx context.Context, stream string, values map[string]interface{}) (string, error) {
	if m.addFunc != nil {
		return m.addFunc(ctx, stream, values)
	}
	return "0-1", nil
}

// mockRateLimiter implements RateLimiter for tests.
type mockRateLimiter struct {
	allowFunc func(ctx context.Context, key string, maxTokens int, refillRate float64) (bool, error)
}

func (m *mockRateLimiter) Allow(ctx context.Context, key string, maxTokens int, refillRate float64) (bool, error) {
	if m.allowFunc != nil {
		return m.allowFunc(ctx, key, maxTokens, refillRate)
	}
	return true, nil
}

func TestHandleIngest(t *testing.T) {
	partnerSecret := "test-secret-bca"
	secrets := map[string]string{"BCA": partnerSecret}
	maxReplayAge := 60 * time.Second

	validPayload := IngestPayload{
		PartnerID: "BCA",
		Timestamp: time.Now().UTC(),
		Vehicles: []Vehicle{
			{
				SourceID:    "v1",
				Make:        "BMW",
				Model:       "330i",
				Year:        2024,
				MileageKM:   5000,
				PriceRaw:    35000,
				CurrencyRaw: "EUR",
			},
		},
	}
	validBody, _ := json.Marshal(validPayload)
	validSignature := hmac.Sign(validBody, partnerSecret)

	oldPayload := IngestPayload{
		PartnerID: "BCA",
		Timestamp: time.Now().UTC().Add(-90 * time.Second),
		Vehicles: []Vehicle{
			{SourceID: "v1", Make: "BMW", Model: "330i", Year: 2024, MileageKM: 5000, PriceRaw: 35000, CurrencyRaw: "EUR"},
		},
	}
	oldBody, _ := json.Marshal(oldPayload)
	oldSignature := hmac.Sign(oldBody, partnerSecret)

	tests := []struct {
		name           string
		method         string
		path           string
		body           []byte
		headers        map[string]string
		streamAdder    StreamAdder
		limiter        RateLimiter
		secrets        map[string]string
		wantStatus     int
		wantBodySubstr string
	}{
		{
			name:   "valid ingest happy path one vehicle",
			method: "POST",
			path:   "/v1/ingest",
			body:   validBody,
			headers: map[string]string{
				"X-Partner-ID":   "BCA",
				"X-HMAC-SHA256":  validSignature,
				"Content-Type":   "application/json",
			},
			streamAdder:    &mockStreamAdder{},
			limiter:        &mockRateLimiter{},
			secrets:        secrets,
			wantStatus:     http.StatusAccepted,
			wantBodySubstr: `"accepted":1`,
		},
		{
			name:   "HMAC mismatch returns 401",
			method: "POST",
			path:   "/v1/ingest",
			body:   validBody,
			headers: map[string]string{
				"X-Partner-ID":  "BCA",
				"X-HMAC-SHA256": "deadbeef0123456789abcdef0123456789abcdef0123456789abcdef01234567",
				"Content-Type":  "application/json",
			},
			streamAdder:    &mockStreamAdder{},
			limiter:        &mockRateLimiter{},
			secrets:        secrets,
			wantStatus:     http.StatusUnauthorized,
			wantBodySubstr: "unauthorized",
		},
		{
			name:   "missing X-Partner-ID returns 400",
			method: "POST",
			path:   "/v1/ingest",
			body:   validBody,
			headers: map[string]string{
				"X-HMAC-SHA256": validSignature,
				"Content-Type":  "application/json",
			},
			streamAdder:    &mockStreamAdder{},
			limiter:        &mockRateLimiter{},
			secrets:        secrets,
			wantStatus:     http.StatusBadRequest,
			wantBodySubstr: "missing partner ID",
		},
		{
			name:   "replay attack timestamp over 60s returns 400",
			method: "POST",
			path:   "/v1/ingest",
			body:   oldBody,
			headers: map[string]string{
				"X-Partner-ID":  "BCA",
				"X-HMAC-SHA256": oldSignature,
				"Content-Type":  "application/json",
			},
			streamAdder:    &mockStreamAdder{},
			limiter:        &mockRateLimiter{},
			secrets:        secrets,
			wantStatus:     http.StatusBadRequest,
			wantBodySubstr: "replay detected",
		},
		{
			name:   "unknown partner returns 401",
			method: "POST",
			path:   "/v1/ingest",
			body:   validBody,
			headers: map[string]string{
				"X-Partner-ID":  "UNKNOWN_PARTNER",
				"X-HMAC-SHA256": validSignature,
				"Content-Type":  "application/json",
			},
			streamAdder:    &mockStreamAdder{},
			limiter:        &mockRateLimiter{},
			secrets:        secrets,
			wantStatus:     http.StatusUnauthorized,
			wantBodySubstr: "unauthorized",
		},
		{
			name:   "empty body returns 400",
			method: "POST",
			path:   "/v1/ingest",
			body:   []byte{},
			headers: map[string]string{
				"X-Partner-ID":  "BCA",
				"X-HMAC-SHA256": hmac.Sign([]byte{}, partnerSecret),
				"Content-Type":  "application/json",
			},
			streamAdder:    &mockStreamAdder{},
			limiter:        &mockRateLimiter{},
			secrets:        secrets,
			wantStatus:     http.StatusBadRequest,
			wantBodySubstr: "invalid payload",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(tt.method, tt.path, bytes.NewReader(tt.body))
			for k, v := range tt.headers {
				req.Header.Set(k, v)
			}

			rec := httptest.NewRecorder()
			handler := NewWebhookHandler(tt.streamAdder, tt.limiter, tt.secrets, maxReplayAge)
			handler.HandleIngest(rec, req)

			if rec.Code != tt.wantStatus {
				t.Errorf("HandleIngest() status = %d, want %d", rec.Code, tt.wantStatus)
			}
			if tt.wantBodySubstr != "" && !bytes.Contains(rec.Body.Bytes(), []byte(tt.wantBodySubstr)) {
				t.Errorf("HandleIngest() body = %q, want substring %q", rec.Body.String(), tt.wantBodySubstr)
			}
		})
	}
}
