package e13_vlm_vision

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// OllamaClient sends images to a locally running ollama server.
//
// API: POST {endpoint}/api/generate with JSON body containing model, prompt,
// and base64-encoded images. stream=false waits for the full response.
//
// ollama must be running with a vision-capable model loaded, e.g.:
//
//	ollama pull phi3.5-vision:latest
//	ollama serve
type OllamaClient struct {
	httpClient *http.Client
	endpoint   string
	model      string
}

// NewOllamaClient creates a production OllamaClient.
// endpoint: base URL of the ollama server (e.g. "http://localhost:11434").
// model: the ollama model tag (e.g. "phi3.5-vision:latest").
// timeout: per-request HTTP timeout; should be ≥ VLMConfig.Timeout.
func NewOllamaClient(endpoint, model string, timeout time.Duration) *OllamaClient {
	return &OllamaClient{
		httpClient: &http.Client{Timeout: timeout},
		endpoint:   endpoint,
		model:      model,
	}
}

// ollamaRequest is the JSON body for POST /api/generate.
type ollamaRequest struct {
	Model  string   `json:"model"`
	Prompt string   `json:"prompt"`
	Images []string `json:"images"` // base64-encoded image data (no data-URI prefix)
	Stream bool     `json:"stream"` // false = wait for full response
}

// ollamaResponse is the response body from POST /api/generate (stream=false).
type ollamaResponse struct {
	Response string `json:"response"`
	Done     bool   `json:"done"`
	Error    string `json:"error,omitempty"`
}

// SendImage base64-encodes image, POSTs to /api/generate, returns model response text.
func (c *OllamaClient) SendImage(ctx context.Context, image []byte, prompt string) (string, error) {
	encoded := base64.StdEncoding.EncodeToString(image)
	body := ollamaRequest{
		Model:  c.model,
		Prompt: prompt,
		Images: []string{encoded},
		Stream: false,
	}
	data, err := json.Marshal(body)
	if err != nil {
		return "", fmt.Errorf("ollama: marshal request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		c.endpoint+"/api/generate", bytes.NewReader(data))
	if err != nil {
		return "", fmt.Errorf("ollama: build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("ollama: HTTP error: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return "", fmt.Errorf("ollama: HTTP %d: %s", resp.StatusCode, string(body))
	}

	var result ollamaResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", fmt.Errorf("ollama: decode response: %w", err)
	}
	if result.Error != "" {
		return "", fmt.Errorf("ollama: model error: %s", result.Error)
	}
	return result.Response, nil
}
