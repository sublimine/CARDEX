// Package model defines the DealerTrustProfile data structure and helpers.
package model

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"time"
)

// DealerTrustProfile is the portable KYB trust credential for a dealer.
// It is issued by the Trust Engine and expires after 90 days (rolling).
//
// eIDAS 2 readiness: EIDASWalletDID is a placeholder for the EU Digital Identity
// Wallet DID that will link this credential to a verifiable presentation once
// eIDAS 2 Regulation (EU) 910/2014 amendments are live (expected 2026–2027).
type DealerTrustProfile struct {
	DealerID          string    `json:"dealer_id"`
	DealerName        string    `json:"dealer_name"`
	Country           string    `json:"country"`
	VATID             string    `json:"vat_id"`
	VIESStatus        string    `json:"vies_status"`         // "valid" | "invalid" | "unchecked"
	RegistryStatus    string    `json:"registry_status"`     // "registered" | "not_found" | "unchecked"
	RegistryAge       int       `json:"registry_age_years"`  // years since commercial registration
	V15Score          float64   `json:"v15_score"`           // 0–100 from quality pipeline V15
	ListingVolume     int       `json:"listing_volume"`      // active listings in index
	AvgCompositeScore float64   `json:"avg_composite_score"` // 0–100 avg quality composite
	IndexTenureDays   int       `json:"index_tenure_days"`   // days since first discovery
	AnomalyCount      int       `json:"anomaly_count"`       // anomaly signals (EV Watch + rejected listings)
	TrustScore        float64   `json:"trust_score"`         // 0–100 weighted composite
	TrustTier         string    `json:"trust_tier"`          // "platinum" | "gold" | "silver" | "unverified"
	BadgeURL          string    `json:"badge_url"`           // embeddable SVG badge URL
	IssuedAt          time.Time `json:"issued_at"`
	ExpiresAt         time.Time `json:"expires_at"` // IssuedAt + 90 days
	ProfileHash       string    `json:"profile_hash"` // SHA-256 for tamper-evident verification
	EIDASWalletDID    string    `json:"eidas_wallet_did,omitempty"` // placeholder; populated when eIDAS 2 live
}

// TierFromScore maps a 0–100 trust score to the canonical tier label.
func TierFromScore(score float64) string {
	switch {
	case score >= 85:
		return "platinum"
	case score >= 70:
		return "gold"
	case score >= 50:
		return "silver"
	default:
		return "unverified"
	}
}

// ComputeHash returns an HMAC-SHA-256 fingerprint of the profile binding
// dealer ID, trust score, and issuance time. The secret key comes from
// CARDEX_TRUST_HASH_SECRET — without it the function falls back to a plain
// SHA-256 hash so existing data keeps verifying, but a startup check in
// cmd/trust-service refuses to start when the env var is empty in
// non-development mode.
//
// Plain SHA-256 (the previous design) was trivially reproducible by anyone
// who knew the dealer ID, score, and issuance time — all public fields of
// the JSON profile. With HMAC, forging a valid hash requires knowledge of
// the server-side secret.
func ComputeHash(dealerID string, score float64, issuedAt time.Time) string {
	payload := fmt.Sprintf("%s:%.6f:%d", dealerID, score, issuedAt.Unix())
	if secret := os.Getenv("CARDEX_TRUST_HASH_SECRET"); secret != "" {
		mac := hmac.New(sha256.New, []byte(secret))
		mac.Write([]byte(payload))
		return hex.EncodeToString(mac.Sum(nil))
	}
	h := sha256.New()
	h.Write([]byte(payload))
	return hex.EncodeToString(h.Sum(nil))
}

// VerifyHash returns true iff `got` matches the recomputed hash for the
// (dealerID, score, issuedAt) tuple. Uses hmac.Equal to avoid timing leaks.
func VerifyHash(dealerID string, score float64, issuedAt time.Time, got string) bool {
	want := ComputeHash(dealerID, score, issuedAt)
	return hmac.Equal([]byte(want), []byte(got))
}

// IsExpired reports whether the profile has passed its 90-day validity window.
func (p *DealerTrustProfile) IsExpired(now time.Time) bool {
	return now.After(p.ExpiresAt)
}
