package check

// NL provider — RDW Open Data (Rijksdienst voor het Wegverkeer)
//
// What IS publicly available:
//   - Dataset m9d7-ebf2: registered vehicles (make, model, first registration, fuel, weight)
//   - Dataset sgfe-77wx: APK (MOT) inspection results
//   - Dataset 8ys7-d773: reported stolen vehicles
//
// Lookup strategy:
//  1. Search m9d7-ebf2 by voertuigidentificatienummer (VIN) → get kenteken (plate)
//  2. Use kenteken to query APK and stolen datasets
//
// No API key required; rate-limit: ≤1 req/sec per Socrata terms of service.
// Field names sourced from RDW open data catalogue (opendata.rdw.nl).
// If the API changes field names, update the rdwVehicle / rdwAPK structs below.

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"
)

const (
	rdwBase       = "https://opendata.rdw.nl/resource"
	rdwVehiclesDS = "m9d7-ebf2" // Gekentekende voertuigen
	rdwAPKDS      = "sgfe-77wx" // APK inspections
	rdwStolenDS   = "8ys7-d773" // Stolen vehicles
)

// NLProvider fetches data from the Dutch RDW open data portal.
type NLProvider struct {
	httpClient *http.Client
	baseURL    string // overridable for testing
}

// NewNLProvider creates a provider using the production RDW API.
func NewNLProvider() *NLProvider {
	return &NLProvider{
		httpClient: &http.Client{Timeout: 15 * time.Second},
		baseURL:    rdwBase,
	}
}

// NewNLProviderWithBase constructs an NLProvider pointing at a custom base URL (for tests).
func NewNLProviderWithBase(base string) *NLProvider {
	return &NLProvider{
		httpClient: &http.Client{Timeout: 5 * time.Second},
		baseURL:    base,
	}
}

func (p *NLProvider) Country() string { return "NL" }

func (p *NLProvider) SupportsVIN(vin string) bool {
	// RDW's primary index is license plate, but Socrata allows filtering
	// on voertuigidentificatienummer (VIN) via $where queries.
	return len(vin) == 17
}

// rdwVehicle is a partial mapping of the m9d7-ebf2 dataset fields.
// Field names reflect the RDW catalogue as of 2025; verify at opendata.rdw.nl if they change.
type rdwVehicle struct {
	Kenteken                     string `json:"kenteken"`
	VoertuigID                   string `json:"voertuigidentificatienummer"`
	Merk                         string `json:"merk"`
	Handelsbenaming              string `json:"handelsbenaming"`
	DatumEersteToelating         string `json:"datum_eerste_toelating"`       // YYYYMMDD
	BrandstofOmschrijving        string `json:"brandstof_omschrijving"`
	MassaLeegVoertuig            string `json:"massa_ledig_voertuig"`         // kg
	ToegestaneMaximumMassaVoertuig string `json:"toegestane_maximum_massa_voertuig"` // kg
	Voertuigsoort                string `json:"voertuigsoort"`
	AantalCilinders              string `json:"aantal_cilinders"`
	CilinderInhoud               string `json:"cilinderinhoud"` // cc
}

// rdwAPK is a partial mapping of the sgfe-77wx inspection dataset.
type rdwAPK struct {
	Kenteken         string `json:"kenteken"`
	MeldDatum        string `json:"meld_datum_door_keuringsinstantie_dt"` // ISO datetime
	SoortErkenning   string `json:"soort_erkenning_omschrijving"`
	Vervaldatum      string `json:"vervaldatum_keuring_dt"`               // ISO datetime
	KMStand          string `json:"tellerstandoordeel"`                   // may contain mileage judgement
}

// rdwStolen is a partial mapping of the stolen vehicles dataset.
type rdwStolen struct {
	Kenteken string `json:"kenteken"`
}

// FetchHistory queries the RDW API for a vehicle by VIN.
// Returns ErrProviderUnavailable only if the RDW API itself is unreachable;
// a vehicle not found in the database is not an error (empty RegistryData is returned).
func (p *NLProvider) FetchHistory(ctx context.Context, vin string) (*RegistryData, error) {
	vehicle, err := p.fetchVehicle(ctx, vin)
	if err != nil {
		return nil, fmt.Errorf("NL/RDW vehicle lookup: %w", err)
	}
	if vehicle == nil {
		// Vehicle not registered in NL — return empty, not an error.
		return &RegistryData{}, nil
	}

	result := &RegistryData{}

	// First registration.
	if t := parseRDWDate(vehicle.DatumEersteToelating); !t.IsZero() {
		result.Registrations = append(result.Registrations, Registration{
			Date:    t,
			Country: "NL",
			Type:    EventFirstRegistration,
			RawData: map[string]string{
				"kenteken": vehicle.Kenteken,
				"merk":     vehicle.Merk,
				"model":    vehicle.Handelsbenaming,
			},
		})
	}

	// Technical specs.
	specs := &TechnicalSpecs{FuelType: vehicle.BrandstofOmschrijving}
	if kg := parseInt(vehicle.MassaLeegVoertuig); kg > 0 {
		specs.EmptyWeightKg = kg
	}
	if kg := parseInt(vehicle.ToegestaneMaximumMassaVoertuig); kg > 0 {
		specs.GrossWeightKg = kg
	}
	if cc := parseInt(vehicle.CilinderInhoud); cc > 0 {
		specs.DisplacementCC = cc
	}
	result.TechnicalSpecs = specs

	// APK inspections (by kenteken).
	inspections, err := p.fetchAPK(ctx, vehicle.Kenteken)
	if err == nil {
		result.Inspections = inspections
	}

	// Stolen flag (by kenteken).
	stolen, err := p.fetchStolen(ctx, vehicle.Kenteken)
	if err == nil {
		result.StolenFlag = stolen
	}

	return result, nil
}

func (p *NLProvider) fetchVehicle(ctx context.Context, vin string) (*rdwVehicle, error) {
	query := fmt.Sprintf("%s/%s.json?$where=%s",
		p.baseURL, rdwVehiclesDS,
		url.QueryEscape(fmt.Sprintf("voertuigidentificatienummer='%s'", strings.ToUpper(vin))),
	)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, query, nil)
	if err != nil {
		return nil, err
	}
	resp, err := p.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("RDW status %d", resp.StatusCode)
	}
	var rows []rdwVehicle
	if err := json.NewDecoder(resp.Body).Decode(&rows); err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		return nil, nil
	}
	return &rows[0], nil
}

func (p *NLProvider) fetchAPK(ctx context.Context, kenteken string) ([]Inspection, error) {
	query := fmt.Sprintf("%s/%s.json?kenteken=%s",
		p.baseURL, rdwAPKDS, url.QueryEscape(kenteken),
	)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, query, nil)
	if err != nil {
		return nil, err
	}
	resp, err := p.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("RDW APK status %d", resp.StatusCode)
	}
	var rows []rdwAPK
	if err := json.NewDecoder(resp.Body).Decode(&rows); err != nil {
		return nil, err
	}

	var inspections []Inspection
	for _, row := range rows {
		ins := Inspection{
			Country: "NL",
			Center:  row.SoortErkenning,
		}
		if t := parseRDWDateTime(row.MeldDatum); !t.IsZero() {
			ins.Date = t
		}
		if t := parseRDWDateTime(row.Vervaldatum); !t.IsZero() {
			ins.NextDueDate = t
		}
		// RDW does not directly expose pass/fail in this dataset field;
		// the tellerstandoordeel field records an odometer judgement, not inspection result.
		// We mark as pass if a next due date is present (implies it passed).
		if !ins.NextDueDate.IsZero() {
			ins.Result = InspectionPass
		} else {
			ins.Result = InspectionPending
		}
		inspections = append(inspections, ins)
	}
	return inspections, nil
}

func (p *NLProvider) fetchStolen(ctx context.Context, kenteken string) (bool, error) {
	query := fmt.Sprintf("%s/%s.json?kenteken=%s",
		p.baseURL, rdwStolenDS, url.QueryEscape(kenteken),
	)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, query, nil)
	if err != nil {
		return false, err
	}
	resp, err := p.httpClient.Do(req)
	if err != nil {
		return false, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return false, fmt.Errorf("RDW stolen status %d", resp.StatusCode)
	}
	var rows []rdwStolen
	if err := json.NewDecoder(resp.Body).Decode(&rows); err != nil {
		return false, err
	}
	return len(rows) > 0, nil
}

// ── parsing helpers ───────────────────────────────────────────────────────────

// parseRDWDate parses the RDW date format YYYYMMDD.
func parseRDWDate(s string) time.Time {
	if len(s) != 8 {
		return time.Time{}
	}
	t, _ := time.Parse("20060102", s)
	return t
}

// parseRDWDateTime parses ISO 8601 datetimes returned by Socrata.
func parseRDWDateTime(s string) time.Time {
	if s == "" {
		return time.Time{}
	}
	for _, layout := range []string{time.RFC3339, "2006-01-02T15:04:05.000"} {
		if t, err := time.Parse(layout, s); err == nil {
			return t
		}
	}
	return time.Time{}
}

// parseInt converts a string to int, returning 0 on failure.
func parseInt(s string) int {
	var n int
	fmt.Sscanf(s, "%d", &n)
	return n
}
