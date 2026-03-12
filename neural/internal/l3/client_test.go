package l3

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestClassifySuccess(t *testing.T) {
	// Mock llama-server
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/health" {
			w.WriteHeader(http.StatusOK)
			return
		}
		if r.URL.Path == "/completion" {
			json.NewEncoder(w).Encode(map[string]interface{}{
				"content": `{"tax_status": "REBU", "confidence": 0.97}`,
			})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	client := NewClient(server.URL, "")
	ctx := context.Background()

	// Health check
	if !client.Healthy(ctx) {
		t.Fatal("expected mock server to be healthy")
	}

	// Classify
	result, err := client.Classify(ctx, ClassificationInput{
		VehicleULID: "01JTEST0001",
		Source:      "mobile.de",
		Description: "BMW 320d Touring, Differenzbesteuerung §25a",
		SellerType:  "DEALER",
		SellerVAT:   "DE123456789",
		Country:     "DE",
	})
	if err != nil {
		t.Fatal("Classify failed:", err)
	}
	if result.TaxStatus != "REBU" {
		t.Fatalf("expected REBU, got %s", result.TaxStatus)
	}
	if result.Confidence != 0.97 {
		t.Fatalf("expected 0.97, got %f", result.Confidence)
	}
}

func TestClassifyServerDown(t *testing.T) {
	client := NewClient("http://127.0.0.1:59999", "")
	ctx := context.Background()

	if client.Healthy(ctx) {
		t.Fatal("expected unhealthy for non-existent server")
	}

	_, err := client.Classify(ctx, ClassificationInput{VehicleULID: "01JTEST0002"})
	if err == nil {
		t.Fatal("expected error for non-existent server")
	}
}
