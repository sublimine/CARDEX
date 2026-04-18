// Package check implements the CARDEX vehicle history report engine.
// It aggregates data from public registries across 6 European countries (DE/FR/ES/BE/NL/CH)
// plus VIN decoding via NHTSA vPIC.
//
// Rule R1: providers only expose data that is genuinely publicly accessible.
// Where a registry has no public API, the provider returns ErrProviderUnavailable
// with an explanation of what credentials or access would be required.
package check

import (
	"context"
	"errors"
	"time"
)

// ErrProviderUnavailable is returned when a registry has no public API
// or requires professional credentials that are not configured.
var ErrProviderUnavailable = errors.New("provider unavailable: no public API access")

// RegistryProvider is implemented by each country-specific data source.
type RegistryProvider interface {
	// Country returns the ISO 3166-1 alpha-2 code for this provider.
	Country() string
	// SupportsVIN returns true if the provider can use a VIN as lookup key.
	// Some registries require a license plate instead.
	SupportsVIN(vin string) bool
	// FetchHistory retrieves available public data for the given VIN.
	// Returns ErrProviderUnavailable if the registry has no public API.
	FetchHistory(ctx context.Context, vin string) (*RegistryData, error)
}

// RegistryData is the normalised output of a single registry provider.
// All slices may be empty if the registry does not provide that data type.
type RegistryData struct {
	Registrations  []Registration
	Inspections    []Inspection
	Recalls        []Recall
	StolenFlag     bool
	MileageRecords []MileageRecord
	TechnicalSpecs *TechnicalSpecs
}

// Registration records a change of ownership or first entry into a national registry.
type Registration struct {
	Date    time.Time
	Country string
	Type    RegistrationEventType // first, transfer, import, export
	RawData map[string]string     // original provider fields for transparency
}

// RegistrationEventType classifies a registration record.
type RegistrationEventType string

const (
	EventFirstRegistration RegistrationEventType = "first_registration"
	EventTransfer          RegistrationEventType = "transfer"
	EventImport            RegistrationEventType = "import"
	EventExport            RegistrationEventType = "export"
)

// Inspection is the result of a mandatory periodic roadworthiness test (e.g. APK/TÜV/ITV/CT).
type Inspection struct {
	Date         time.Time
	Result       InspectionResult
	Mileage      int    // odometer reading at time of inspection, 0 if unknown
	Center       string // name/ID of the testing centre
	NextDueDate  time.Time
	Country      string
}

// InspectionResult indicates whether the vehicle passed or failed.
type InspectionResult string

const (
	InspectionPass    InspectionResult = "pass"
	InspectionFail    InspectionResult = "fail"
	InspectionPending InspectionResult = "pending"
)

// Recall is a manufacturer or authority-issued safety recall.
type Recall struct {
	CampaignID   string
	Manufacturer string
	Description  string
	Status       RecallStatus
	StartDate    time.Time
	Country      string
	Source       string // e.g. "KBA", "RAPEX", "NHTSA"
}

// RecallStatus indicates whether the recall is still actionable.
type RecallStatus string

const (
	RecallOpen   RecallStatus = "open"
	RecallClosed RecallStatus = "closed"
)

// MileageRecord is a timestamped odometer reading from any reliable source.
type MileageRecord struct {
	Date     time.Time
	Mileage  int
	Source   string // e.g. "APK", "car-pass", "service_record"
	Country  string
}

// TechnicalSpecs contains type-approval and manufacturer data.
type TechnicalSpecs struct {
	EmptyWeightKg    int
	GrossWeightKg    int
	PowerKw          int
	DisplacementCC   int
	CO2GPerKm        float64
	EuroNorm         string // e.g. "Euro 6d"
	FuelType         string
	TransmissionType string
	NumberOfSeats    int
}

// DataSource records which providers were consulted and their outcome.
type DataSource struct {
	Provider  string
	Country   string
	Status    DataSourceStatus
	Error     string   // populated when Status is StatusError or StatusUnavailable
	LatencyMs int64
}

// DataSourceStatus describes the result of consulting a provider.
type DataSourceStatus string

const (
	StatusSuccess     DataSourceStatus = "success"
	StatusError       DataSourceStatus = "error"
	StatusUnavailable DataSourceStatus = "unavailable" // ErrProviderUnavailable
	StatusScaffold    DataSourceStatus = "scaffold"    // provider not yet implemented
)

// Alert represents a finding that warrants immediate attention.
type Alert struct {
	Type     AlertType
	Severity AlertSeverity
	Message  string
}

// AlertType classifies the nature of an alert.
type AlertType string

const (
	AlertStolen              AlertType = "stolen"
	AlertRecallOpen          AlertType = "recall_open"
	AlertMileageRollback     AlertType = "mileage_rollback"
	AlertMileageGap          AlertType = "mileage_high_gap"
)

// AlertSeverity grades the urgency of an alert.
type AlertSeverity string

const (
	SeverityCritical AlertSeverity = "critical"
	SeverityWarning  AlertSeverity = "warning"
	SeverityInfo     AlertSeverity = "info"
)
