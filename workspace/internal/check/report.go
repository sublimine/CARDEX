package check

import (
	"context"
	"errors"
	"sort"
	"sync"
	"time"
)

// VehicleReport is the top-level output of GenerateReport.
type VehicleReport struct {
	VIN                string            `json:"vin"`
	DecodedVIN         *VINInfo          `json:"vinDecode,omitempty"`
	GeneratedAt        time.Time         `json:"generatedAt"`
	Countries          []CountryReport   `json:"countries"`
	Recalls            []Recall          `json:"recalls"`
	MileageHistory     []MileageRecord   `json:"mileageHistory"`
	MileageConsistency *ConsistencyScore `json:"mileageConsistency,omitempty"`
	Alerts             []Alert           `json:"alerts"`
	DataSources        []DataSource      `json:"dataSources"`
	// PlateInfo holds the data returned by the plate resolver.
	// Populated only on the plate→report path; nil on direct VIN lookups.
	PlateInfo          *PlateResult      `json:"plateInfo,omitempty"`
}

// CountryReport groups all data returned by a single country's provider.
type CountryReport struct {
	Country        string          `json:"country"`
	Registrations  []Registration  `json:"registrations"`
	Inspections    []Inspection    `json:"inspections"`
	StolenFlag     bool            `json:"stolenFlag"`
	TechnicalSpecs *TechnicalSpecs `json:"technicalSpecs,omitempty"`
}

// ConsistencyScore summarises the quality of the mileage record history.
type ConsistencyScore struct {
	Consistent bool   `json:"consistent"`
	Rollbacks  int    `json:"rollbacks"`
	HighGaps   int    `json:"highGaps"`
	Note       string `json:"note,omitempty"`
}

// Engine orchestrates VIN decoding and provider fetching.
type Engine struct {
	decoder   *VINDecoder
	providers []RegistryProvider
	cache     *Cache
}

// NewEngine creates an Engine with all country providers and the default NHTSA decoder.
func NewEngine(cache *Cache, decoder *VINDecoder, providers []RegistryProvider) *Engine {
	return &Engine{
		decoder:   decoder,
		providers: providers,
		cache:     cache,
	}
}

// providerResult carries the outcome of one parallel provider call.
type providerResult struct {
	provider string
	country  string
	data     *RegistryData
	source   DataSource
}

// GenerateReport decodes the VIN, queries all providers in parallel,
// aggregates results, and caches the outcome.
// The returned report always includes a DataSources list so callers can
// see which providers succeeded, failed, or were unavailable.
func (e *Engine) GenerateReport(ctx context.Context, vin string) (*VehicleReport, error) {
	if err := ValidateVIN(vin); err != nil {
		return nil, err
	}

	// Check cache first.
	if cached, ok := e.cache.GetReport(ctx, vin); ok {
		return cached, nil
	}

	// Decode VIN (NHTSA enrichment, non-fatal on failure).
	vinInfo, err := e.decoder.Decode(ctx, vin)
	if err != nil {
		return nil, err
	}

	// Fan out to all providers in parallel.
	results := make([]providerResult, len(e.providers))
	var wg sync.WaitGroup
	for i, p := range e.providers {
		wg.Add(1)
		go func(idx int, prov RegistryProvider) {
			defer wg.Done()
			start := time.Now()
			providerID := prov.Country() + "_provider"
			ds := DataSource{
				ID:      providerID,
				Name:    providerID,
				Country: prov.Country(),
			}
			if !prov.SupportsVIN(vin) {
				ds.Status = StatusUnavailable
				ds.Error = "provider does not support VIN lookup"
				metricProviderErrors.WithLabelValues(ds.ID, ds.Country, "unsupported").Inc()
				results[idx] = providerResult{provider: ds.ID, country: ds.Country, source: ds}
				return
			}
			data, fetchErr := prov.FetchHistory(ctx, vin)
			ds.LatencyMs = time.Since(start).Milliseconds()
			metricProviderLatency.WithLabelValues(ds.ID, ds.Country).Observe(time.Since(start).Seconds())

			if fetchErr != nil {
				if errors.Is(fetchErr, ErrProviderUnavailable) {
					ds.Status = StatusUnavailable
					ds.Error = fetchErr.Error()
					ds.Note = fetchErr.Error()
				} else {
					ds.Status = StatusError
					ds.Error = fetchErr.Error()
					ds.Note = fetchErr.Error()
					metricProviderErrors.WithLabelValues(ds.ID, ds.Country, "fetch_error").Inc()
				}
				results[idx] = providerResult{provider: ds.ID, country: ds.Country, source: ds}
				return
			}
			ds.Status = StatusSuccess
			results[idx] = providerResult{
				provider: ds.ID,
				country:  ds.Country,
				data:     data,
				source:   ds,
			}
		}(i, p)
	}
	wg.Wait()

	// Aggregate.
	report := &VehicleReport{
		VIN:         vin,
		DecodedVIN:  vinInfo,
		GeneratedAt: time.Now().UTC(),
	}
	for _, r := range results {
		report.DataSources = append(report.DataSources, r.source)
		if r.data == nil {
			continue
		}
		if r.data.StolenFlag {
			report.Alerts = append(report.Alerts, newAlert(AlertStolen, SeverityCritical, "Vehicle reported stolen in "+r.country))
		}
		report.Recalls = append(report.Recalls, r.data.Recalls...)
		report.MileageHistory = append(report.MileageHistory, r.data.MileageRecords...)

		if len(r.data.Registrations) > 0 || len(r.data.Inspections) > 0 || r.data.StolenFlag || r.data.TechnicalSpecs != nil {
			cr := CountryReport{
				Country:        r.country,
				Registrations:  r.data.Registrations,
				Inspections:    r.data.Inspections,
				StolenFlag:     r.data.StolenFlag,
				TechnicalSpecs: r.data.TechnicalSpecs,
			}
			report.Countries = append(report.Countries, cr)
		}
	}

	// Add alerts for open recalls.
	for _, rec := range report.Recalls {
		if rec.Status == RecallOpen {
			report.Alerts = append(report.Alerts, newAlert(AlertRecallOpen, SeverityWarning, "Open recall: "+rec.Description))
		}
	}

	// Sort and analyse mileage.
	report.MileageHistory = sortedMileage(report.MileageHistory)
	report.MileageConsistency = analyseMileage(report.MileageHistory)
	if !report.MileageConsistency.Consistent {
		metricMileageInconsistencies.Inc()
		if report.MileageConsistency.Rollbacks > 0 {
			report.Alerts = append(report.Alerts, newAlert(AlertMileageRollback, SeverityCritical, report.MileageConsistency.Note))
		} else if report.MileageConsistency.HighGaps > 0 {
			report.Alerts = append(report.Alerts, newAlert(AlertMileageGap, SeverityWarning, report.MileageConsistency.Note))
		}
	}

	// Cache and instrument.
	_ = e.cache.SetReport(ctx, report)
	cacheLabel := "false"
	metricRequestsTotal.WithLabelValues(cacheLabel).Inc()

	return report, nil
}

// sortedMileage returns mileage records in chronological order (oldest first).
func sortedMileage(records []MileageRecord) []MileageRecord {
	sort.Slice(records, func(i, j int) bool {
		return records[i].Date.Before(records[j].Date)
	})
	return records
}

const maxKmPerYear = 50_000

// AnalyseMileage checks for odometer rollbacks and unusually high annual jumps.
// Exported for use in tests.
func AnalyseMileage(records []MileageRecord) *ConsistencyScore {
	return analyseMileage(records)
}

func analyseMileage(records []MileageRecord) *ConsistencyScore {
	cs := &ConsistencyScore{Consistent: true}
	if len(records) < 2 {
		return cs
	}
	for i := 1; i < len(records); i++ {
		prev, curr := records[i-1], records[i]
		if curr.Mileage < prev.Mileage && curr.Mileage > 0 && prev.Mileage > 0 {
			cs.Rollbacks++
			cs.Consistent = false
		}
		years := curr.Date.Sub(prev.Date).Hours() / (24 * 365)
		if years > 0 && curr.Mileage > prev.Mileage {
			kmPerYear := float64(curr.Mileage-prev.Mileage) / years
			if kmPerYear > float64(maxKmPerYear) {
				cs.HighGaps++
				cs.Consistent = false
			}
		}
	}
	switch {
	case cs.Rollbacks > 0:
		cs.Note = "Odometer rollback detected — mileage decreased between records"
	case cs.HighGaps > 0:
		cs.Note = "Unusually high annual mileage detected — possible gap in records"
	}
	return cs
}
