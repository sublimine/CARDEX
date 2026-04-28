package check

// NL provider — RDW Open Data (Rijksdienst voor het Wegverkeer)
//
// Datasets consulted (all Socrata, no API key required):
//   m9d7-ebf2 Gekentekende voertuigen — basic registration, weight, color, doors, APK expiry,
//             wam_verzekerd (insurance), export_indicator, openstaande_terugroepactie_indicator
//   8ys7-d773 Gekentekende_voertuigen_brandstof — fuel type, Euro emission level, net power kW
//   sgfe-77wx Open_Data_RDW_Keuringen — APK inspection results with dates
//   a34c-vvps Open_Data_RDW_Gebreken — APK defects found per inspection
//   t49b-isb7 Open_Data_RDW_Terugroepacties — recall (terugroepactie) records
//
// Lookup strategy:
//  1. Query m9d7-ebf2 by VIN → get kenteken (plate) + rich vehicle data
//  2. Use kenteken to query fuel, APK, defects, and recalls in parallel
//  3. Derive alerts from insurance, export, and recall indicators in main record
//
// Rate limit: ≤1 req/sec per Socrata ToS; keep parallel calls to ≤5.

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

const (
	rdwBase       = "https://opendata.rdw.nl/resource"
	rdwVehiclesDS = "m9d7-ebf2" // Gekentekende voertuigen (primary)
	// rdwFuelDS declared in plate_nl.go ("8ys7-d773")
	rdwAPKDS      = "sgfe-77wx" // APK inspection results
	rdwDefectsDS  = "a34c-vvps" // APK defects (gebreken)
	rdwRecallsDS  = "t49b-isb7" // Terugroepacties (recalls)
)

// NLProvider fetches data from the Dutch RDW open data portal.
type NLProvider struct {
	httpClient *http.Client
	baseURL    string // overridable for testing
}

// NewNLProvider creates a provider using the production RDW API.
func NewNLProvider() *NLProvider {
	return &NLProvider{
		httpClient: &http.Client{Timeout: 20 * time.Second},
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
	return len(vin) == 17
}

// rdwVehicle maps the m9d7-ebf2 dataset fields used by this provider.
type rdwVehicle struct {
	Kenteken                       string `json:"kenteken"`
	VoertuigID                     string `json:"voertuigidentificatienummer"`
	Merk                           string `json:"merk"`
	Handelsbenaming                string `json:"handelsbenaming"`
	DatumEersteToelating           string `json:"datum_eerste_toelating"`             // YYYYMMDD
	EersteKleur                    string `json:"eerste_kleur"`                       // color
	Inrichting                     string `json:"inrichting"`                         // body type
	AantalZitplaatsen              string `json:"aantal_zitplaatsen"`
	AantalDeuren                   string `json:"aantal_deuren"`
	AantalCilinders                string `json:"aantal_cilinders"`
	CilinderInhoud                 string `json:"cilinderinhoud"`                     // cc
	MassaLeegVoertuig              string `json:"massa_ledig_voertuig"`               // kg
	ToegestaneMaximumMassaVoertuig string `json:"toegestane_maximum_massa_voertuig"` // kg
	Voertuigsoort                  string `json:"voertuigsoort"`
	WamVerzekerd                   string `json:"wam_verzekerd"`                      // "Ja"/"Nee"
	ExportIndicator                string `json:"export_indicator"`                   // "Ja"/"Nee"
	OpenstaandeTerugroepActie      string `json:"openstaande_terugroepactie_indicator"` // "Ja"/"Nee"
	VervaldatumAPK                 string `json:"vervaldatum_apk_dt"`                 // ISO datetime
}

// rdwFuel maps the 8ys7-d773 fuel/emissions dataset.
type rdwFuel struct {
	Kenteken             string `json:"kenteken"`
	BrandstofOmschrijving string `json:"brandstof_omschrijving"` // fuel type
	UitlaatEmissieNiveau string `json:"uitlaatemissieniveau"`   // Euro norm
	NettoMaximumVermogen string `json:"nettomaximumvermogen"`  // kW (string float)
}

// rdwAPK maps the sgfe-77wx inspection dataset.
type rdwAPK struct {
	Kenteken       string `json:"kenteken"`
	MeldDatum      string `json:"meld_datum_door_keuringsinstantie_dt"` // ISO datetime
	SoortErkenning string `json:"soort_erkenning_omschrijving"`
	Vervaldatum    string `json:"vervaldatum_keuring_dt"` // ISO datetime
}

// rdwDefect maps the a34c-vvps APK defects dataset.
type rdwDefect struct {
	Kenteken          string `json:"kenteken"`
	MeldDatum         string `json:"meld_datum_door_keuringsinstantie_dt"`
	GebrekID          string `json:"gebrek_identificatie"`
	AantalGebreken    string `json:"aantal_gebreken_geconstateerd"`
	SoortErkenning    string `json:"soort_erkenning_omschrijving"`
}

// rdwRecall maps the t49b-isb7 recall dataset.
type rdwRecall struct {
	Kenteken       string `json:"kenteken"`
	ReferentieCode string `json:"referentiecode_rdw"`
	CodeStatus     string `json:"code_status"` // "O"=open, "P"=producer fix reported
	Status         string `json:"status"`
}

// FetchHistory queries multiple RDW datasets for a vehicle by VIN.
func (p *NLProvider) FetchHistory(ctx context.Context, vin string) (*RegistryData, error) {
	vehicle, err := p.fetchVehicle(ctx, vin)
	if err != nil {
		return nil, fmt.Errorf("NL/RDW vehicle lookup: %w", err)
	}
	if vehicle == nil {
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

	// Technical specs from main dataset.
	specs := &TechnicalSpecs{
		FuelType:      "", // filled by fuel dataset below
		NumberOfSeats: parseInt(vehicle.AantalZitplaatsen),
	}
	if kg := parseInt(vehicle.MassaLeegVoertuig); kg > 0 {
		specs.EmptyWeightKg = kg
	}
	if kg := parseInt(vehicle.ToegestaneMaximumMassaVoertuig); kg > 0 {
		specs.GrossWeightKg = kg
	}
	if cc := parseInt(vehicle.CilinderInhoud); cc > 0 {
		specs.DisplacementCC = cc
	}

	// Alerts derived from main record fields.
	if strings.EqualFold(vehicle.WamVerzekerd, "nee") {
		result.Alerts = append(result.Alerts, Alert{
			ID:          "nl_no_insurance",
			Type:        AlertNoInsurance,
			Severity:    SeverityWarning,
			Title:       "Sin seguro obligatorio (WAM)",
			Description: "El RDW indica que el vehículo no tiene seguro obligatorio activo en los Países Bajos.",
			Source:      "RDW m9d7-ebf2",
		})
	}
	if strings.EqualFold(vehicle.ExportIndicator, "ja") {
		result.Alerts = append(result.Alerts, Alert{
			ID:          "nl_exported",
			Type:        AlertExported,
			Severity:    SeverityWarning,
			Title:       "Vehículo exportado (NL)",
			Description: "El RDW indica que este vehículo ha sido dado de baja por exportación.",
			Source:      "RDW m9d7-ebf2",
		})
	}

	// Fan out remaining dataset queries in parallel.
	var (
		fuelData    []rdwFuel
		inspections []Inspection
		recalls     []Recall
		mu          sync.Mutex
	)

	var wg sync.WaitGroup

	wg.Add(1)
	go func() {
		defer wg.Done()
		fuels, ferr := p.fetchFuel(ctx, vehicle.Kenteken)
		if ferr == nil && len(fuels) > 0 {
			mu.Lock()
			fuelData = fuels
			mu.Unlock()
		}
	}()

	wg.Add(1)
	go func() {
		defer wg.Done()
		ins, ierr := p.fetchAPK(ctx, vehicle.Kenteken)
		if ierr == nil {
			mu.Lock()
			inspections = ins
			mu.Unlock()
		}
	}()

	wg.Add(1)
	go func() {
		defer wg.Done()
		recs, rerr := p.fetchRecalls(ctx, vehicle.Kenteken)
		if rerr == nil {
			mu.Lock()
			recalls = recs
			mu.Unlock()
		}
	}()

	wg.Wait()

	// Apply fuel data to specs.
	if len(fuelData) > 0 {
		f := fuelData[0]
		specs.FuelType = f.BrandstofOmschrijving
		specs.EuroNorm = f.UitlaatEmissieNiveau
		if kw := parseFloat(f.NettoMaximumVermogen); kw > 0 {
			specs.PowerKw = int(kw)
		}
	}
	result.TechnicalSpecs = specs

	result.Inspections = inspections
	result.Recalls = recalls

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

func (p *NLProvider) fetchFuel(ctx context.Context, kenteken string) ([]rdwFuel, error) {
	query := fmt.Sprintf("%s/%s.json?kenteken=%s",
		p.baseURL, rdwFuelDS, url.QueryEscape(kenteken),
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
		return nil, fmt.Errorf("RDW fuel status %d", resp.StatusCode)
	}
	var rows []rdwFuel
	if err := json.NewDecoder(resp.Body).Decode(&rows); err != nil {
		return nil, err
	}
	return rows, nil
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
		if !ins.NextDueDate.IsZero() {
			ins.Result = InspectionPass
		} else {
			ins.Result = InspectionPending
		}
		inspections = append(inspections, ins)
	}
	return inspections, nil
}

func (p *NLProvider) fetchRecalls(ctx context.Context, kenteken string) ([]Recall, error) {
	query := fmt.Sprintf("%s/%s.json?kenteken=%s",
		p.baseURL, rdwRecallsDS, url.QueryEscape(kenteken),
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
		return nil, fmt.Errorf("RDW recalls status %d", resp.StatusCode)
	}
	var rows []rdwRecall
	if err := json.NewDecoder(resp.Body).Decode(&rows); err != nil {
		return nil, err
	}

	var recalls []Recall
	for _, row := range rows {
		status := RecallClosed
		if row.CodeStatus == "O" {
			status = RecallOpen
		}
		recalls = append(recalls, Recall{
			CampaignID:  row.ReferentieCode,
			Description: row.Status,
			Status:      status,
			Country:     "NL",
			Source:      "RDW terugroepacties (t49b-isb7)",
		})
	}
	return recalls, nil
}

// ── parsing helpers ───────────────────────────────────────────────────────────

func parseRDWDate(s string) time.Time {
	if len(s) != 8 {
		return time.Time{}
	}
	t, _ := time.Parse("20060102", s)
	return t
}

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

func parseInt(s string) int {
	var n int
	fmt.Sscanf(s, "%d", &n)
	return n
}

