package pipeline

import (
	"context"
	"fmt"
)

// Storage persists validation results to the knowledge graph.
type Storage interface {
	PersistValidation(ctx context.Context, result *ValidationResult) error
	GetVehicleByID(ctx context.Context, id string) (*Vehicle, error)
}

// VehicleValidationSummary collects all validator results for a single vehicle.
type VehicleValidationSummary struct {
	VehicleID   string
	Results     []*ValidationResult
	HasCritical bool
}

// Pipeline runs an ordered set of validators on vehicles.
type Pipeline struct {
	validators []Validator
	storage    Storage
}

// New creates a Pipeline with the given validators and storage backend.
func New(storage Storage, validators ...Validator) *Pipeline {
	return &Pipeline{validators: validators, storage: storage}
}

// ValidateVehicle runs every registered validator against the vehicle, persists
// each result, and returns a summary. Returns a non-nil error on the first
// critical failure encountered, but still completes all remaining validators.
func (p *Pipeline) ValidateVehicle(ctx context.Context, v *Vehicle) (*VehicleValidationSummary, error) {
	summary := &VehicleValidationSummary{VehicleID: v.InternalID}
	var criticalErr error

	for _, val := range p.validators {
		result, err := val.Validate(ctx, v)
		if err != nil {
			return summary, fmt.Errorf("validator %s: %w", val.ID(), err)
		}
		if p.storage != nil {
			if err := p.storage.PersistValidation(ctx, result); err != nil {
				return summary, fmt.Errorf("persist %s result: %w", val.ID(), err)
			}
		}
		summary.Results = append(summary.Results, result)
		if !result.Pass && result.Severity == SeverityCritical && criticalErr == nil {
			summary.HasCritical = true
			criticalErr = fmt.Errorf("critical validation failure from %s: %s", val.ID(), result.Issue)
		}
	}
	return summary, criticalErr
}
