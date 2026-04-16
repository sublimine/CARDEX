// Package pipeline defines the core interfaces for the quality validation pipeline.
package pipeline

import (
	"context"
	"fmt"
	"time"
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
}

// NewVehicle constructs a Vehicle and validates its required fields.
// Returns an error if InternalID, VIN, vehicleMake, vehicleModel, SourceURL,
// or DealerID are empty — those are mandatory for the quality pipeline.
func NewVehicle(
	internalID, vin, vehicleMake, vehicleModel string,
	year int,
	sourceURL, dealerID, sourceCountry string,
	extractedAt time.Time,
) (*Vehicle, error) {
	if internalID == "" {
		return nil, fmt.Errorf("NewVehicle: InternalID is required")
	}
	if vin == "" {
		return nil, fmt.Errorf("NewVehicle: VIN is required")
	}
	if vehicleMake == "" {
		return nil, fmt.Errorf("NewVehicle: Make is required")
	}
	if vehicleModel == "" {
		return nil, fmt.Errorf("NewVehicle: Model is required")
	}
	if sourceURL == "" {
		return nil, fmt.Errorf("NewVehicle: SourceURL is required")
	}
	if dealerID == "" {
		return nil, fmt.Errorf("NewVehicle: DealerID is required")
	}
	return &Vehicle{
		InternalID:    internalID,
		VIN:           vin,
		Make:          vehicleMake,
		Model:         vehicleModel,
		Year:          year,
		SourceURL:     sourceURL,
		DealerID:      dealerID,
		SourceCountry: sourceCountry,
		ExtractedAt:   extractedAt,
		Metadata:      map[string]string{},
	}, nil
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
