// Package alerts provides cross-border arbitrage alerts: persistent per-owner
// rules that, on a schedule, scan for opportunities exceeding a margin threshold
// and notify via webhook or email.
package alerts

import (
	"crypto/rand"
	"encoding/hex"
	"time"
)

// Alert is a stored arbitrage-alert rule.
type Alert struct {
	ID            string     `json:"id"`
	Owner         string     `json:"owner"`
	Make          string     `json:"make"`
	Model         string     `json:"model"`
	YearMin       int        `json:"year_min,omitempty"`
	YearMax       int        `json:"year_max,omitempty"`
	Fuel          string     `json:"fuel,omitempty"`
	MileageMin    int        `json:"mileage_min,omitempty"`
	MileageMax    int        `json:"mileage_max,omitempty"`
	BuyCountries  []string   `json:"buy_countries,omitempty"`
	SellCountries []string   `json:"sell_countries,omitempty"`
	MinMarginPct  float64    `json:"min_margin_pct"`
	WebhookURL    string     `json:"webhook_url,omitempty"`
	Email         string     `json:"email,omitempty"`
	Active        bool       `json:"active"`
	CreatedAt     time.Time  `json:"created_at"`
	LastFiredAt   *time.Time `json:"last_fired_at,omitempty"`
}

// CreateRequest is the JSON body for POST /api/v1/alerts.
type CreateRequest struct {
	Make          string   `json:"make"`
	Model         string   `json:"model"`
	YearMin       int      `json:"year_min"`
	YearMax       int      `json:"year_max"`
	Fuel          string   `json:"fuel"`
	MileageMin    int      `json:"mileage_min"`
	MileageMax    int      `json:"mileage_max"`
	BuyCountries  []string `json:"buy_countries"`
	SellCountries []string `json:"sell_countries"`
	MinMarginPct  float64  `json:"min_margin_pct"`
	WebhookURL    string   `json:"webhook_url"`
	Email         string   `json:"email"`
}

// newID returns a random, prefixed alert id.
func newID() string {
	var b [12]byte
	_, _ = rand.Read(b[:])
	return "alrt_" + hex.EncodeToString(b[:])
}
