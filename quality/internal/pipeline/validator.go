// Package pipeline defines the core interfaces for the quality validation pipeline.
package pipeline

import (
	"context"
	"time"

	"cardex.eu/quality/internal/nlg"
)

// Severity classifies validation failures.
type Severity string

const (
	SeverityCritical Severity = "CRITICAL" // blocks publication
	SeverityWarning  Severity = "WARNING"  // flag but allow
	SeverityInfo     Severity = "INFO"     // metadata only
)

// Validator defines a specific validation technique (V01–V20).
type Validator interface {
	ID() string
	Name() string
	Severity() Severity
	Validate(ctx context.Context, vehicle *Vehicle) (*ValidationResult, error)
}

// Vehicle is the canonical vehicle record passed through the quality pipeline.
type Vehicle struct {
	InternalID    string
	VIN           string
	Make          string
	Model         string
	Year          int
	Mileage       int
	Fuel          string
	Transmission  string
	PriceEUR      int
	PhotoURLs     []string
	SourceURL     string
	DealerID      string
	SourceCountry string
	Title         string // raw title from extraction source
	Description   string // full listing description (raw or NLG-generated)
	ExtractedAt   time.Time // when this record was extracted/scraped
	Metadata      map[string]string

	// AIGeneratedMeta must be populated when Description was produced by a
	// local LLM. Nil means the description is human-authored or sourced
	// verbatim from the original listing. Non-nil enables AI Act Art. 50(2)
	// machine-readable disclosure in all API responses.
	AIGeneratedMeta *nlg.AIGeneratedMetadata
}

// ValidationResult is the outcome of a single validator run on one vehicle.
type ValidationResult struct {
	ValidatorID string
	VehicleID   string
	Pass        bool
	Severity    Severity
	Issue       string             // human-readable description of the issue
	Confidence  float64            // 0.0–1.0
	Suggested   map[string]string  // suggested corrections (field → corrected value)
	Evidence    map[string]string  // raw evidence (e.g., NHTSA decoded fields)
}
