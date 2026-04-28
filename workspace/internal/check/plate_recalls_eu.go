package check

// EU Safety Gate (RAPEX) recall checker.
//
// Source: https://ec.europa.eu/safety-gate-alerts/api/download/weeklyReport/list/xml/en
// Free, public, no authentication.
//
// The Safety Gate publishes a weekly XML listing all reports since 2005.
// Each report contains product safety alerts including Motor Vehicles.
// This resolver:
//   1. Downloads the report index (list of all weekly report URLs).
//   2. For each Motor Vehicles alert, checks if it matches the queried make/model.
//
// Because the index covers 2005–present, we cache it for 7 days.
// Individual report downloads are skipped; we use the notification carousel
// endpoint to get recent vehicle alerts efficiently.
//
// Alert matching is by make name (fuzzy) — RAPEX does not carry VINs.

import (
	"context"
	"encoding/xml"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"
)

const (
	rapexListURL      = "https://ec.europa.eu/safety-gate-alerts/api/download/weeklyReport/list/xml/en"
	rapexLatestReport = "https://ec.europa.eu/safety-gate-alerts/api/download/weeklyReport/detail/xml/%s?language=en"
)

// rapexWeeklyList is the top-level element of the report index XML.
type rapexWeeklyList struct {
	XMLName xml.Name       `xml:"Safety-Gate"`
	Reports []rapexReport  `xml:"weeklyReport"`
}

type rapexReport struct {
	Reference       string `xml:"reference"`
	PublicationDate string `xml:"publicationDate"`
	Year            int    `xml:"year"`
	Week            int    `xml:"week"`
	URL             string `xml:"URL"`
}

// rapexDetailList is the top-level element of a weekly report XML.
type rapexDetailList struct {
	XMLName       xml.Name           `xml:"Safety-Gate"`
	Notifications []rapexNotification `xml:"notifications"`
}

type rapexNotification struct {
	CaseNumber string `xml:"caseNumber"`
	Category   string `xml:"category"`
	Brand      string `xml:"brand"`
	Product    string `xml:"product"`
	Name       string `xml:"name"`
	RiskType   string `xml:"riskType"`
	Danger     string `xml:"danger"`
	Measures   string `xml:"measures"`
	Reference  string `xml:"reference"` // alert detail URL
}

// EURAPEXAlert is the output type for a Safety Gate alert matching a vehicle.
type EURAPEXAlert struct {
	CaseNumber string
	Category   string
	Brand      string
	Product    string
	RiskType   string
	Danger     string
	DetailURL  string
}

// RAPEXResolver fetches and caches EU Safety Gate motor vehicle alerts.
type RAPEXResolver struct {
	client    *http.Client
	mu        sync.RWMutex
	alerts    []rapexNotification // motor-vehicle alerts from last N weeks
	fetchedAt time.Time
	ttl       time.Duration
}

// NewRAPEXResolver returns a resolver caching motor-vehicle alerts for 7 days.
func NewRAPEXResolver() *RAPEXResolver {
	return &RAPEXResolver{
		client: &http.Client{Timeout: 20 * time.Second},
		ttl:    7 * 24 * time.Hour,
	}
}

// Resolve returns all EU Safety Gate alerts matching the given make/model.
// Matching is case-insensitive on the Brand and Product fields.
// Returns an empty slice (not an error) when no alerts match.
func (r *RAPEXResolver) Resolve(ctx context.Context, make, model string) ([]EURAPEXAlert, error) {
	alerts, err := r.getAlerts(ctx)
	if err != nil {
		return nil, err
	}

	makeLower := strings.ToLower(strings.TrimSpace(make))
	modelLower := strings.ToLower(strings.TrimSpace(model))

	var matches []EURAPEXAlert
	for _, a := range alerts {
		brandLower := strings.ToLower(a.Brand)
		productLower := strings.ToLower(a.Product + " " + a.Name)
		if !strings.Contains(brandLower, makeLower) && !strings.Contains(makeLower, brandLower) {
			continue
		}
		if modelLower != "" && !strings.Contains(productLower, modelLower) {
			continue
		}
		matches = append(matches, EURAPEXAlert{
			CaseNumber: a.CaseNumber,
			Category:   a.Category,
			Brand:      a.Brand,
			Product:    a.Name,
			RiskType:   a.RiskType,
			Danger:     a.Danger,
			DetailURL:  a.Reference,
		})
	}
	return matches, nil
}

// getAlerts returns cached motor-vehicle alerts, refreshing when TTL expires.
// Fetches the report index, then downloads the 4 most recent weekly reports
// and filters for "Motor vehicles" category alerts.
func (r *RAPEXResolver) getAlerts(ctx context.Context) ([]rapexNotification, error) {
	r.mu.RLock()
	if len(r.alerts) > 0 && time.Since(r.fetchedAt) < r.ttl {
		out := r.alerts
		r.mu.RUnlock()
		return out, nil
	}
	r.mu.RUnlock()

	r.mu.Lock()
	defer r.mu.Unlock()
	if len(r.alerts) > 0 && time.Since(r.fetchedAt) < r.ttl {
		return r.alerts, nil
	}

	// Step 1: download the index.
	indexBody, err := r.fetch(ctx, rapexListURL)
	if err != nil {
		return nil, fmt.Errorf("rapex index fetch: %w", err)
	}
	var index rapexWeeklyList
	if err := xml.Unmarshal(indexBody, &index); err != nil {
		return nil, fmt.Errorf("rapex index parse: %w", err)
	}

	// Step 2: download the 8 most recent weekly reports and collect motor vehicle alerts.
	limit := 8
	if len(index.Reports) < limit {
		limit = len(index.Reports)
	}
	var collected []rapexNotification
	for i := 0; i < limit; i++ {
		rep := index.Reports[i]
		body, err := r.fetch(ctx, rep.URL)
		if err != nil {
			continue // non-fatal; skip this week
		}
		var detail rapexDetailList
		if err := xml.Unmarshal(body, &detail); err != nil {
			continue
		}
		for _, n := range detail.Notifications {
			if strings.Contains(strings.ToLower(n.Category), "motor vehicle") {
				collected = append(collected, n)
			}
		}
	}

	r.alerts = collected
	r.fetchedAt = time.Now()
	return collected, nil
}

func (r *RAPEXResolver) fetch(ctx context.Context, url string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/xml, text/xml, */*")
	resp, err := r.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrPlateResolutionUnavailable, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	return io.ReadAll(io.LimitReader(resp.Body, 5*1024*1024))
}
