package l3

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// ClassificationInput contains the vehicle data for L3 classification.
type ClassificationInput struct {
	VehicleULID string
	Source      string
	Description string
	SellerType  string
	SellerVAT   string
	Country     string
}

// ClassificationResult is what L3 returns after Qwen inference.
type ClassificationResult struct {
	TaxStatus  string  `json:"tax_status"`
	Confidence float64 `json:"confidence"`
}

// Client calls llama-server HTTP /completion endpoint.
type Client struct {
	baseURL    string
	grammar    string
	httpClient *http.Client
}

const systemPrompt = `You are a tax classification engine for European used vehicle trade.
Given the vehicle listing text, determine the VAT/margin tax status.

Rules:
- If the listing mentions margin scheme, §25a, Differenzbesteuerung, margeregeling, MwSt nicht ausweisbar, REBU, régime de la marge, or similar → REBU
- If the seller is clearly a VAT-registered dealer selling with invoice (Rechnung mit ausgewiesener MwSt, netto prijs excl BTW, HT/TVA) → DEDUCTIBLE
- If seller_type is PRIVATE → always REBU (private individuals cannot issue VAT invoices)
- If you cannot determine with high confidence → REQUIRES_HUMAN_AUDIT

Respond ONLY with the JSON object. No explanation.`

// NewClient creates an L3 HTTP client.
func NewClient(baseURL string, grammar string) *Client {
	return &Client{
		baseURL: baseURL,
		grammar: grammar,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

// Healthy checks if llama-server is reachable.
func (c *Client) Healthy(ctx context.Context) bool {
	req, err := http.NewRequestWithContext(ctx, "GET", c.baseURL+"/health", nil)
	if err != nil {
		return false
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	return resp.StatusCode == http.StatusOK
}

// Classify sends a vehicle to Qwen via llama-server /completion.
func (c *Client) Classify(ctx context.Context, input ClassificationInput) (ClassificationResult, error) {
	userPrompt := fmt.Sprintf(
		"Classify this vehicle listing:\n\nSource: %s\nDescription: %s\nSeller Type: %s\nSeller VAT: %s\nCountry: %s",
		input.Source,
		truncate(input.Description, 500),
		input.SellerType,
		input.SellerVAT,
		input.Country,
	)

	// Build llama-server /completion request
	reqBody := map[string]interface{}{
		"prompt":      fmt.Sprintf("<|im_start|>system\n%s<|im_end|>\n<|im_start|>user\n%s<|im_end|>\n<|im_start|>assistant\n", systemPrompt, userPrompt),
		"n_predict":   100,
		"temperature": 0.0,
		"stop":        []string{"<|im_end|>"},
	}

	if c.grammar != "" {
		reqBody["grammar"] = c.grammar
	}

	bodyBytes, err := json.Marshal(reqBody)
	if err != nil {
		return ClassificationResult{}, fmt.Errorf("l3: marshal request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", c.baseURL+"/completion", bytes.NewReader(bodyBytes))
	if err != nil {
		return ClassificationResult{}, fmt.Errorf("l3: create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return ClassificationResult{}, fmt.Errorf("l3: HTTP request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return ClassificationResult{}, fmt.Errorf("l3: server returned %d: %s", resp.StatusCode, string(body))
	}

	var llamaResp struct {
		Content string `json:"content"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&llamaResp); err != nil {
		return ClassificationResult{}, fmt.Errorf("l3: decode response: %w", err)
	}

	var result ClassificationResult
	if err := json.Unmarshal([]byte(llamaResp.Content), &result); err != nil {
		return ClassificationResult{}, fmt.Errorf("l3: parse classification JSON: %w (raw: %s)", err, llamaResp.Content)
	}

	return result, nil
}

func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen]
}
