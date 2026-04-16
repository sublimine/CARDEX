// Package run exposes a minimal public API over the quality module's internal
// packages, intended exclusively for e2e integration tests.
//
// Production code uses the quality-service binary. This package exists so that
// an external test module can run the full V01–V20 validator pipeline in-process
// without importing internal packages directly.
package run

import (
	"context"
	"fmt"
	"net/http"
	"time"

	"github.com/prometheus/client_golang/prometheus"

	"cardex.eu/quality/internal/metrics"
	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/storage"
	"cardex.eu/quality/internal/validator/v01_vin_checksum"
	"cardex.eu/quality/internal/validator/v04_nlp_makemodel"
	"cardex.eu/quality/internal/validator/v05_image_quality"
	"cardex.eu/quality/internal/validator/v06_photo_count"
	"cardex.eu/quality/internal/validator/v07_price_sanity"
	"cardex.eu/quality/internal/validator/v08_mileage_sanity"
	"cardex.eu/quality/internal/validator/v09_year_consistency"
	"cardex.eu/quality/internal/validator/v10_source_url_liveness"
	"cardex.eu/quality/internal/validator/v11_nlg_quality"
	"cardex.eu/quality/internal/validator/v12_cross_source_dedup"
	"cardex.eu/quality/internal/validator/v13_completeness"
	"cardex.eu/quality/internal/validator/v14_freshness"
	"cardex.eu/quality/internal/validator/v15_dealer_trust"
	"cardex.eu/quality/internal/validator/v16_photo_phash"
	"cardex.eu/quality/internal/validator/v17_sold_status"
	"cardex.eu/quality/internal/validator/v18_language_consistency"
	"cardex.eu/quality/internal/validator/v19_currency"
	"cardex.eu/quality/internal/validator/v20_composite"
)

// Vehicle is the canonical vehicle record passed through the quality pipeline.
// Type alias so e2e tests can construct Vehicle values without importing internal packages.
type Vehicle = pipeline.Vehicle

// ValidationResult is the outcome of a single validator run.
type ValidationResult = pipeline.ValidationResult

// RunResult summarises the quality pipeline outcome for one vehicle.
type RunResult struct {
	VehicleID        string
	HasCritical      bool
	ScorePercent     float64
	Decision         string
	ValidatorResults []*ValidationResult
}

// RunPipeline executes validators V01, V04–V20 (skipping V02/V03 which require
// external APIs) against v, persisting results to dbPath so that V20 can read
// them for composite scoring.
//
// httpClient is injected for network validators (V05 image quality, V10 URL
// liveness, V16 pHash, V17 sold status). In tests, pass an *http.Client whose
// Transport routes to a local fixture HTTP server.
//
// dbPath must already have the full discovery+quality schema applied.
func RunPipeline(ctx context.Context, dbPath string, v *Vehicle, httpClient *http.Client) (*RunResult, error) {
	store, err := storage.New(dbPath)
	if err != nil {
		return nil, fmt.Errorf("quality/run: open storage: %w", err)
	}
	defer store.Close()

	validators := []pipeline.Validator{
		// V01 — VIN checksum (no network)
		v01_vin_checksum.New(),
		// V02 skipped — NHTSA vPIC external API
		// V03 skipped — DAT Codes credentials required
		// V04 — NLP make/model (no network)
		v04_nlp_makemodel.New(),
		// V05 — image quality (HEAD + magic bytes via httpClient)
		v05_image_quality.NewWithClient(httpClient, 0),
		// V06 — photo count (no network)
		v06_photo_count.New(),
		// V07 — price sanity (embedded baseline, no network)
		v07_price_sanity.New(),
		// V08 — mileage sanity (no network)
		v08_mileage_sanity.New(),
		// V09 — year consistency (no network)
		v09_year_consistency.New(),
		// V10 — source URL liveness (HEAD via httpClient, 1-s cache for tests)
		v10_source_url_liveness.NewWithClient(httpClient, 1*time.Second),
		// V11 — NLG description quality (no network)
		v11_nlg_quality.New(),
		// V12 — cross-source dedup (no-op store — passes for new vehicles)
		v12_cross_source_dedup.New(),
		// V13 — completeness (no network)
		v13_completeness.New(),
		// V14 — freshness (no network)
		v14_freshness.New(),
		// V15 — dealer trust (no-op store — passes for new dealers)
		v15_dealer_trust.New(),
		// V16 — photo pHash (downloads image via httpClient)
		v16_photo_phash.NewWithClient(httpClient),
		// V17 — sold status (HEAD via httpClient)
		v17_sold_status.NewWithClient(httpClient),
		// V18 — language consistency (no network)
		v18_language_consistency.New(),
		// V19 — currency/EUR (no network)
		v19_currency.New(),
		// V20 — composite score (reads V01–V19 results from store)
		v20_composite.NewWithStore(store),
	}

	pl := pipeline.New(store, validators...)
	summary, _ := pl.ValidateVehicle(ctx, v)

	res := &RunResult{
		VehicleID:        summary.VehicleID,
		HasCritical:      summary.HasCritical,
		ValidatorResults: summary.Results,
	}

	// Extract composite score and decision from V20 result.
	for _, r := range summary.Results {
		if r.ValidatorID == "V20" {
			res.Decision = r.Suggested["publication_decision"]
			if pct, ok := r.Evidence["score_pct"]; ok {
				fmt.Sscanf(pct, "%f", &res.ScorePercent) //nolint:errcheck
			}
		}
	}

	// Increment Prometheus metrics (mirrors runCycle in quality-service main).
	metrics.VehiclesValidated.Inc()
	for _, r := range summary.Results {
		result := "pass"
		if !r.Pass {
			result = "fail"
		}
		metrics.ValidationTotal.WithLabelValues(r.ValidatorID, string(r.Severity), result).Inc()
		if !r.Pass && r.Severity == pipeline.SeverityCritical {
			metrics.CriticalFailures.WithLabelValues(r.ValidatorID).Inc()
		}
	}

	return res, nil
}

// VehiclesValidatedCount reads the current value of the
// cardex_quality_vehicles_validated_total Prometheus counter from the default
// registry. Returns 0 if the metric is not yet registered or has not been
// incremented. Used in e2e tests to assert that the pipeline ran.
func VehiclesValidatedCount() float64 {
	mfs, err := prometheus.DefaultGatherer.Gather()
	if err != nil {
		return 0
	}
	for _, mf := range mfs {
		if mf.GetName() == "cardex_quality_vehicles_validated_total" {
			if mm := mf.GetMetric(); len(mm) > 0 {
				return mm[0].GetCounter().GetValue()
			}
		}
	}
	return 0
}
