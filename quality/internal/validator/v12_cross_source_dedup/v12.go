// Package v12_cross_source_dedup implements validation strategy V12 — Cross-Source
// Deduplication Detection.
//
// # Strategy
//
// A VIN should appear at most once per dealer. Multiple listings for the same
// VIN across different dealers may indicate:
//
//   - Legitimate: multi-platform dealer publishing (INFO)
//   - Suspicious: broker re-listing without disclosure (WARNING if 2–5 dealers)
//   - Fraudulent: VIN swapping or ghost dealer networks (CRITICAL if >5 dealers)
//
// The validator queries the knowledge graph for all vehicle records sharing the
// same VIN and analyses the distinct dealer count.
//
// # Dependency injection
//
// A DedupStore interface decouples the validator from a specific storage backend.
// Use New() for a no-op store (always returns empty — safe default in unit tests
// that don't wire up a real KG); use NewWithStore() to inject a real SQLiteStorage.
package v12_cross_source_dedup

import (
	"context"
	"fmt"
	"strings"

	"cardex.eu/quality/internal/pipeline"
)

const (
	strategyID   = "V12"
	strategyName = "Cross-Source Deduplication"

	warnThreshold     = 2  // ≥2 distinct dealers → WARNING
	criticalThreshold = 5  // >5 distinct dealers → CRITICAL
)

// redactVIN returns the last 4 characters of a VIN preceded by asterisks so
// that structured logs and issue strings do not expose full VIN PII.
// Input must already be upper-cased and trimmed (the caller ensures this).
func redactVIN(vin string) string {
	if len(vin) < 4 {
		return "***"
	}
	return "***" + vin[len(vin)-4:]
}

// VehicleRecord is a minimal vehicle entry as returned by the KG query.
type VehicleRecord struct {
	InternalID string
	VIN        string
	SourceURL  string
	DealerID   string
}

// DedupStore queries the knowledge graph for VIN deduplication.
type DedupStore interface {
	GetVehiclesByVIN(ctx context.Context, vin string) ([]*VehicleRecord, error)
}

// noopDedupStore is the default store when no KG is connected.
type noopDedupStore struct{}

func (n *noopDedupStore) GetVehiclesByVIN(_ context.Context, _ string) ([]*VehicleRecord, error) {
	return nil, nil
}

// CrossSourceDedup implements pipeline.Validator for V12.
type CrossSourceDedup struct {
	store DedupStore
}

// New returns a CrossSourceDedup validator with a no-op store.
func New() *CrossSourceDedup { return NewWithStore(&noopDedupStore{}) }

// NewWithStore returns a CrossSourceDedup validator backed by the given store.
func NewWithStore(s DedupStore) *CrossSourceDedup { return &CrossSourceDedup{store: s} }

func (v *CrossSourceDedup) ID() string                 { return strategyID }
func (v *CrossSourceDedup) Name() string               { return strategyName }
func (v *CrossSourceDedup) Severity() pipeline.Severity { return pipeline.SeverityCritical }

// Validate queries the KG for vehicles sharing this VIN and analyses the result.
func (v *CrossSourceDedup) Validate(ctx context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error) {
	result := &pipeline.ValidationResult{
		ValidatorID: strategyID,
		VehicleID:   vehicle.InternalID,
		Severity:    pipeline.SeverityInfo,
		Suggested:   make(map[string]string),
		Evidence:    make(map[string]string),
	}

	vin := strings.ToUpper(strings.TrimSpace(vehicle.VIN))
	if len(vin) != 17 {
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = "VIN not 17 chars — skipping dedup check (V01 owns VIN format)"
		result.Confidence = 1.0
		return result, nil
	}

	records, err := v.store.GetVehiclesByVIN(ctx, vin)
	if err != nil {
		// Storage error → soft fail (INFO) so we don't block the pipeline.
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = "dedup store unavailable: " + err.Error()
		result.Confidence = 0.0
		return result, nil
	}

	if len(records) == 0 {
		result.Pass = true
		result.Confidence = 1.0
		return result, nil
	}

	// Collect distinct dealers.
	dealers := make(map[string]struct{})
	var sourceURLs []string
	for _, r := range records {
		dealers[r.DealerID] = struct{}{}
		sourceURLs = append(sourceURLs, r.SourceURL)
	}
	distinctDealers := len(dealers)

	result.Evidence["vin"] = redactVIN(vin)
	result.Evidence["total_records"] = fmt.Sprintf("%d", len(records))
	result.Evidence["distinct_dealers"] = fmt.Sprintf("%d", distinctDealers)
	result.Evidence["source_urls"] = strings.Join(sourceURLs, " | ")

	_, ourDealerPresent := dealers[vehicle.DealerID]

	switch {
	case distinctDealers == 1 && ourDealerPresent:
		// Only our own dealer — multi-platform publishing by same dealer.
		if len(records) > 1 {
			result.Pass = true
			result.Severity = pipeline.SeverityInfo
			result.Issue = fmt.Sprintf("VIN appears %d times for same dealer — multi-platform publishing", len(records))
			result.Confidence = 0.9
		} else {
			result.Pass = true
			result.Confidence = 1.0
		}

	case distinctDealers == 1 && !ourDealerPresent:
		// One other dealer also has this VIN — low concern but worth noting.
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = "VIN also listed by one other dealer"
		result.Confidence = 0.9

	case distinctDealers < warnThreshold:
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Confidence = 0.9

	case distinctDealers >= warnThreshold && distinctDealers <= criticalThreshold:
		result.Pass = false
		result.Severity = pipeline.SeverityWarning
		result.Issue = fmt.Sprintf("VIN %s appears under %d distinct dealers — possible broker re-listing", redactVIN(vin), distinctDealers)
		result.Confidence = 0.85
		result.Suggested["action"] = "verify ownership chain — VIN may be listed by multiple brokers"

	default: // distinctDealers > criticalThreshold
		result.Pass = false
		result.Severity = pipeline.SeverityCritical
		result.Issue = fmt.Sprintf("VIN %s appears under %d distinct dealers — highly suspicious (VIN swapping / fraud)", redactVIN(vin), distinctDealers)
		result.Confidence = 0.95
		result.Suggested["action"] = "flag for fraud review — cross-dealer VIN proliferation"
	}
	return result, nil
}
