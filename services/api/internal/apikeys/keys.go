// Package apikeys defines the API-key model and access tiers used for
// authentication and rate limiting.
//
// Keys are stored in Redis under "apikey:<key>" as a JSON document. An optional
// bootstrap key (from config) is granted Enterprise tier without a Redis entry
// so the service is operable before any key has been provisioned.
package apikeys

import "time"

// Tier is a subscription level that determines the rate-limit ceiling and the
// set of countries/features a key may access.
type Tier string

const (
	// TierFree is the no-cost tier (lowest rate limit).
	TierFree Tier = "free"
	// TierPaid is a paid subscription (higher rate limit).
	TierPaid Tier = "paid"
	// TierEnterprise is the top tier (effectively unlimited).
	TierEnterprise Tier = "enterprise"
)

// Valid reports whether t is a recognised tier.
func (t Tier) Valid() bool {
	switch t {
	case TierFree, TierPaid, TierEnterprise:
		return true
	default:
		return false
	}
}

// APIKey is the metadata associated with a key. The raw key string itself is the
// Redis map key and is never echoed back to clients.
type APIKey struct {
	// Name is a human label for the key owner (dealer/company).
	Name string `json:"name"`
	// Tier controls rate limits and feature access.
	Tier Tier `json:"tier"`
	// Active gates the key; an inactive key is rejected even if it exists.
	Active bool `json:"active"`
	// CreatedAt is when the key was provisioned (RFC3339).
	CreatedAt time.Time `json:"created_at"`
}
