package tax

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"
)

const (
	viesBaseURL    = "https://ec.europa.eu/taxation_customs/vies/rest-api/ms/%s/vat/%s"
	viesDefaultTTL = 24 * time.Hour
	viesUserAgent  = "CardexBot/1.0 tax-engine"
)

// VATIDValidator validates EU VAT IDs against the VIES service.
type VATIDValidator interface {
	Validate(ctx context.Context, vatID string) (bool, error)
	ValidateBoth(ctx context.Context, sellerID, buyerID string) map[string]bool
}

type viesEntry struct {
	valid     bool
	expiresAt time.Time
}

// VIESClient validates VAT IDs via the VIES REST API with a configurable TTL cache.
type VIESClient struct {
	hc    *http.Client
	ttl   time.Duration
	mu    sync.RWMutex
	cache map[string]*viesEntry
}

// NewVIESClient creates a client with the default 24-hour cache TTL.
func NewVIESClient() *VIESClient {
	return NewVIESClientWithTTL(
		&http.Client{Timeout: 10 * time.Second},
		viesDefaultTTL,
	)
}

// NewVIESClientWithTTL creates a client with a custom HTTP client and TTL (for tests).
func NewVIESClientWithTTL(hc *http.Client, ttl time.Duration) *VIESClient {
	return &VIESClient{
		hc:    hc,
		ttl:   ttl,
		cache: make(map[string]*viesEntry),
	}
}

// Validate checks whether vatID is valid according to VIES.
// Empty IDs and non-EU country prefixes return false without an HTTP call.
// Network errors are silently treated as invalid (fallback to margin scheme).
func (c *VIESClient) Validate(ctx context.Context, vatID string) (bool, error) {
	vatID = strings.ToUpper(strings.ReplaceAll(vatID, " ", ""))
	if len(vatID) < 2 {
		return false, nil
	}

	cc := vatID[:2]
	if !IsEUCountry(cc) {
		return false, nil
	}
	number := vatID[2:]

	// Cache read
	c.mu.RLock()
	if e, ok := c.cache[vatID]; ok && time.Now().Before(e.expiresAt) {
		v := e.valid
		c.mu.RUnlock()
		return v, nil
	}
	c.mu.RUnlock()

	valid, err := c.fetchVIES(ctx, cc, number)
	if err != nil {
		return false, nil
	}

	// Cache write
	c.mu.Lock()
	c.cache[vatID] = &viesEntry{valid: valid, expiresAt: time.Now().Add(c.ttl)}
	c.mu.Unlock()

	return valid, nil
}

// ValidateBoth validates seller and buyer concurrently, returning a map of
// vatID → isValid. Empty IDs are omitted from the result.
func (c *VIESClient) ValidateBoth(ctx context.Context, sellerID, buyerID string) map[string]bool {
	ids := make([]string, 0, 2)
	if sellerID != "" {
		ids = append(ids, sellerID)
	}
	if buyerID != "" {
		ids = append(ids, buyerID)
	}
	if len(ids) == 0 {
		return map[string]bool{}
	}

	var mu sync.Mutex
	result := make(map[string]bool, len(ids))
	var wg sync.WaitGroup

	for _, id := range ids {
		wg.Add(1)
		go func(vatID string) {
			defer wg.Done()
			valid, _ := c.Validate(ctx, vatID)
			mu.Lock()
			result[vatID] = valid
			mu.Unlock()
		}(id)
	}

	wg.Wait()
	return result
}

func (c *VIESClient) fetchVIES(ctx context.Context, cc, number string) (bool, error) {
	url := fmt.Sprintf(viesBaseURL, cc, number)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return false, err
	}
	req.Header.Set("User-Agent", viesUserAgent)

	resp, err := c.hc.Do(req)
	if err != nil {
		return false, err
	}
	defer resp.Body.Close()

	var body struct {
		IsValid   bool   `json:"isValid"`
		UserError string `json:"userError"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return false, err
	}
	return body.IsValid, nil
}
