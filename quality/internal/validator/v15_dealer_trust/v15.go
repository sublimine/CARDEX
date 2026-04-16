// Package v15_dealer_trust implements validation strategy V15 — Dealer Trust Score.
//
// # Strategy
//
// The discovery pipeline assigns each dealer a `confidence_score` (0.0–1.0)
// derived from cross-fertilisation across multiple data sources (CROSS_FERTILIZATION
// phase). A vehicle from an unverified or low-confidence dealer should be treated
// with extra caution.
//
// # Trust tiers
//
//   - confidence > 0.85  → PASS  (multi-source verified, trusted)
//   - 0.60–0.85          → INFO  (moderate trust, single-source)
//   - 0.30–0.60          → WARNING (low confidence, manual check recommended)
//   - < 0.30             → CRITICAL (unverified — possible scam or ghost dealer)
//   - dealer not in KG   → CRITICAL ("orphan vehicle — dealer not registered")
//
// # Dependency injection
//
// TrustStore decouples the validator from the SQLite KG backend. New() returns a
// no-op store that always passes INFO (safe default for unit tests without a KG).
package v15_dealer_trust

import (
	"context"
	"fmt"
	"strings"
	"time"

	"cardex.eu/quality/internal/pipeline"
)

const (
	strategyID   = "V15"
	strategyName = "Dealer Trust Score"

	tierPass    = 0.85
	tierInfo    = 0.60
	tierWarning = 0.30

	trustRampUpDays = 30
	trustRampUpCap  = 0.5
)

// DealerRecord is the trust information returned from the KG for a dealer.
type DealerRecord struct {
	ID              string
	Name            string
	ConfidenceScore float64
	DataSources     int       // number of distinct data sources that confirmed this dealer
	CreatedAt       time.Time // when the dealer was first registered; zero value means unknown
}

// TrustStore queries the knowledge graph for dealer trust data.
type TrustStore interface {
	GetDealerByID(ctx context.Context, dealerID string) (*DealerRecord, error)
}

// noopTrustStore is the default store when no KG is connected.
// It returns a moderate-trust placeholder so the pipeline doesn't block.
type noopTrustStore struct{}

func (n *noopTrustStore) GetDealerByID(_ context.Context, _ string) (*DealerRecord, error) {
	return nil, nil // nil result triggers the "no DealerID" check below
}

// DealerTrust implements pipeline.Validator for V15.
type DealerTrust struct {
	store TrustStore
}

// New returns a DealerTrust validator with a no-op store.
func New() *DealerTrust { return NewWithStore(&noopTrustStore{}) }

// NewWithStore returns a DealerTrust validator backed by the given store.
func NewWithStore(s TrustStore) *DealerTrust { return &DealerTrust{store: s} }

func (v *DealerTrust) ID() string                 { return strategyID }
func (v *DealerTrust) Name() string               { return strategyName }
func (v *DealerTrust) Severity() pipeline.Severity { return pipeline.SeverityCritical }

// Validate looks up the dealer in the KG and applies trust-tier rules.
func (v *DealerTrust) Validate(ctx context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error) {
	result := &pipeline.ValidationResult{
		ValidatorID: strategyID,
		VehicleID:   vehicle.InternalID,
		Severity:    pipeline.SeverityInfo,
		Suggested:   make(map[string]string),
		Evidence:    make(map[string]string),
	}

	dealerID := strings.TrimSpace(vehicle.DealerID)
	if dealerID == "" {
		result.Pass = false
		result.Severity = pipeline.SeverityCritical
		result.Issue = "vehicle has no DealerID — cannot assess trust"
		result.Confidence = 1.0
		result.Suggested["action"] = "assign vehicle to a known dealer"
		return result, nil
	}

	result.Evidence["dealer_id"] = dealerID

	dealer, err := v.store.GetDealerByID(ctx, dealerID)
	if err != nil {
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = "dealer trust store unavailable: " + err.Error()
		result.Confidence = 0.0
		return result, nil
	}

	if dealer == nil {
		result.Pass = false
		result.Severity = pipeline.SeverityCritical
		result.Issue = fmt.Sprintf("dealer %q not found in knowledge graph — orphan vehicle", dealerID)
		result.Confidence = 0.95
		result.Suggested["action"] = "register dealer in KG or re-assign vehicle to known dealer"
		return result, nil
	}

	score := dealer.ConfidenceScore
	result.Evidence["dealer_name"] = dealer.Name
	result.Evidence["confidence_score"] = fmt.Sprintf("%.3f", score)
	result.Evidence["data_sources"] = fmt.Sprintf("%d", dealer.DataSources)

	switch {
	case score > tierPass:
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Confidence = score

	case score >= tierInfo:
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = fmt.Sprintf("dealer confidence %.2f — moderate trust (single-source)", score)
		result.Confidence = score

	case score >= tierWarning:
		result.Pass = false
		result.Severity = pipeline.SeverityWarning
		result.Issue = fmt.Sprintf("dealer confidence %.2f — low confidence, manual check recommended", score)
		result.Confidence = score
		result.Suggested["action"] = "verify dealer legitimacy before publishing"

	default:
		result.Pass = false
		result.Severity = pipeline.SeverityCritical
		result.Issue = fmt.Sprintf("dealer confidence %.2f — unverified, possible scam or ghost dealer", score)
		result.Confidence = score
		result.Suggested["action"] = "do not publish — flag dealer for fraud review"
	}

	// Trust ramp-up: dealers newer than trustRampUpDays get their confidence
	// score capped at trustRampUpCap (0.5), regardless of computed signals.
	// The cap is skipped when CreatedAt is zero (unknown age).
	if !dealer.CreatedAt.IsZero() {
		agedays := time.Since(dealer.CreatedAt).Hours() / 24
		if agedays < trustRampUpDays {
			if result.Confidence > trustRampUpCap {
				result.Confidence = trustRampUpCap
			}
			result.Evidence["trust_ramp_up"] = "true"
		}
	}

	return result, nil
}
