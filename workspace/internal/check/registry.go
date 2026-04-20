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
	Alerts         []Alert // provider-specific alerts (insurance, export flag, etc.)
}

// Registration records a change of ownership or first entry into a national registry.
type Registration struct {
	Date    time.Time             `json:"date"`
	Country string                `json:"country"`
	Type    RegistrationEventType `json:"type"`
	RawData map[string]string     `json:"rawData,omitempty"`
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
	Date        time.Time        `json:"date"`
	Result      InspectionResult `json:"result"`
	Mileage     int              `json:"mileageKm,omitempty"`
	Center      string           `json:"center,omitempty"`
	NextDueDate time.Time        `json:"nextInspectionDate,omitempty"`
	Country     string           `json:"country"`
}

// InspectionResult indicates whether the vehicle passed or failed.
type InspectionResult string

const (
	InspectionPass    InspectionResult = "pass"
	InspectionFail    InspectionResult = "fail"
	InspectionPending InspectionResult = "pending"
)

// Recall is a manufacturer or authority-issued safety recall.
// Field names match the frontend RecallEntry type.
type Recall struct {
	CampaignID         string       `json:"campaignId"`
	Manufacturer       string       `json:"manufacturer"`
	Description        string       `json:"description"`
	AffectedComponent  string       `json:"affectedComponent,omitempty"`
	Status             RecallStatus `json:"status"`
	StartDate          time.Time    `json:"startDate,omitempty"`
	Country            string       `json:"country,omitempty"`
	Source             string       `json:"source,omitempty"`
}

// RecallStatus indicates whether the recall is still actionable.
type RecallStatus string

const (
	RecallOpen   RecallStatus = "open"
	RecallClosed RecallStatus = "completed" // matches frontend "completed"
)

// MileageRecord is a timestamped odometer reading from any reliable source.
// Field names match the frontend MileageRecord type.
type MileageRecord struct {
	Date      time.Time `json:"date"`
	Mileage   int       `json:"mileageKm"`
	Source    string    `json:"source"`
	Country   string    `json:"country,omitempty"`
	IsAnomaly bool      `json:"isAnomaly,omitempty"`
}

// TechnicalSpecs contains type-approval and manufacturer data.
type TechnicalSpecs struct {
	EmptyWeightKg    int     `json:"emptyWeightKg,omitempty"`
	GrossWeightKg    int     `json:"grossWeightKg,omitempty"`
	PowerKw          int     `json:"powerKw,omitempty"`
	DisplacementCC   int     `json:"displacementCC,omitempty"`
	CO2GPerKm        float64 `json:"co2GPerKm,omitempty"`
	EuroNorm         string  `json:"euroNorm,omitempty"`
	FuelType         string  `json:"fuelType,omitempty"`
	TransmissionType string  `json:"transmissionType,omitempty"`
	NumberOfSeats    int     `json:"numberOfSeats,omitempty"`
}

// DataSource records which providers were consulted and their outcome.
// Field names match the frontend DataSource type.
type DataSource struct {
	ID        string           `json:"id"`       // = Provider
	Name      string           `json:"name"`     // = Provider (human-readable)
	Country   string           `json:"country"`
	Status    DataSourceStatus `json:"status"`
	Error     string           `json:"-"`        // internal; exposed as Note
	Note      string           `json:"note,omitempty"`
	LatencyMs int64            `json:"latencyMs,omitempty"`
}

// DataSourceStatus describes the result of consulting a provider.
type DataSourceStatus string

const (
	StatusSuccess     DataSourceStatus = "success"
	StatusError       DataSourceStatus = "error"
	StatusUnavailable DataSourceStatus = "unavailable"
	StatusScaffold    DataSourceStatus = "unavailable" // scaffold = unavailable to frontend
)

// Alert represents a finding that warrants immediate attention.
// Field names match the frontend VehicleAlert type.
type Alert struct {
	ID                string        `json:"id"`
	Type              AlertType     `json:"type"`
	Severity          AlertSeverity `json:"severity"`
	Title             string        `json:"title"`
	Description       string        `json:"description"`
	RecommendedAction string        `json:"recommendedAction,omitempty"`
	Source            string        `json:"source"`
}

// AlertType classifies the nature of an alert.
type AlertType string

const (
	AlertStolen          AlertType = "stolen"
	AlertRecallOpen      AlertType = "recall_open"
	AlertMileageRollback AlertType = "mileage_rollback"
	AlertMileageGap      AlertType = "mileage_gap"
	AlertNoInsurance     AlertType = "no_insurance"
	AlertExported        AlertType = "exported"
)

// AlertSeverity grades the urgency of an alert.
type AlertSeverity string

const (
	SeverityCritical AlertSeverity = "critical"
	SeverityWarning  AlertSeverity = "warning"
	SeverityInfo     AlertSeverity = "info"
)

// newAlert builds a fully populated Alert with computed fields.
func newAlert(alertType AlertType, severity AlertSeverity, message string) Alert {
	title, action := alertMeta(alertType)
	return Alert{
		ID:                string(alertType) + "_" + string(severity),
		Type:              alertType,
		Severity:          severity,
		Title:             title,
		Description:       message,
		RecommendedAction: action,
		Source:            "CARDEX Check",
	}
}

func alertMeta(t AlertType) (title, action string) {
	switch t {
	case AlertStolen:
		return "Vehicle reported stolen", "Do not purchase — contact authorities immediately"
	case AlertRecallOpen:
		return "Open safety recall", "Contact the manufacturer or an authorised dealer to schedule recall work"
	case AlertMileageRollback:
		return "Odometer rollback detected", "Request a full service history and consider a professional inspection"
	case AlertMileageGap:
		return "Unusually high annual mileage", "Verify with service records; gap may indicate missing history"
	default:
		return string(t), ""
	}
}
