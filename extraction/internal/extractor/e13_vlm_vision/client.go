// Package e13_vlm_vision implements extraction strategy E13 — VLM Screenshot Vision.
//
// E13 is the last automated extraction strategy in the cascade. When all
// structured-data strategies (E01–E10) have failed to produce usable vehicle
// data, E13 downloads images from the dealer's listing pages and sends them to
// a Vision Language Model (VLM) with a structured prompt to extract vehicle
// fields directly from the visual content.
//
// Target model: Phi-3.5-vision-instruct (4.2B, Q4_K_M ≈ 3 GB VRAM/RAM).
// Fallback models for constrained hardware: Moondream2 (1.9B), Florence-2-base.
// All models are served locally via ollama or llama.cpp — no external API calls.
//
// AI Act Art. 50(2) compliance: every VehicleRaw produced by E13 carries
// AdditionalFields["ai_generated"]["is_ai_generated"]=true with model identifier
// and generation timestamp.
package e13_vlm_vision

import (
	"context"
	"time"
)

// VLMClient is the interface all VLM backends must implement.
// Implementations: OllamaClient (production), MockClient (tests).
//
// SendImage sends image bytes and a text prompt to the VLM backend.
// It returns the raw text response from the model, which is expected to be a
// JSON object. The caller is responsible for parsing the response.
//
// Implementations must respect ctx cancellation and deadlines.
type VLMClient interface {
	SendImage(ctx context.Context, image []byte, prompt string) (string, error)
}

// VLMConfig holds configuration for the VLM client and E13 strategy.
// Populated from environment variables by config.Load().
type VLMConfig struct {
	// Model is the model tag as registered in ollama (e.g. "phi3.5-vision:latest").
	Model string

	// Endpoint is the base URL of the VLM API server.
	// Default: "http://localhost:11434" (ollama default).
	Endpoint string

	// Timeout is the per-request timeout including model inference.
	// For Phi-3.5 on a Hetzner CX42 CPU: expect 30–60 s per image.
	// Default: 120 s.
	Timeout time.Duration

	// MaxRetries is the number of retry attempts on transient errors.
	// Default: 2.
	MaxRetries int
}

// vlmPrompt is the structured extraction prompt sent with every image.
// It instructs the model to return a strict JSON object with vehicle fields.
// The prompt is purposely concise to maximise field recall on small models.
const vlmPrompt = `Extract vehicle listing data from this image.
Return ONLY a JSON object with the following fields (omit fields not visible in the image):
{
  "make": "brand name",
  "model": "model name",
  "year": 2020,
  "price": 25000,
  "price_currency": "EUR",
  "mileage_km": 45000,
  "fuel_type": "diesel|gasoline|hybrid|electric|lpg|cng|hydrogen",
  "transmission": "manual|automatic|semi-automatic",
  "color": "color name",
  "vin": "VIN if visible",
  "dealer_name": "dealer company name",
  "dealer_location": "city, country"
}
Return only the JSON object. No explanation, no markdown, no code fences.`
