// quality-service — Phase 4 Sprint 22 (20/20 validators — Phase 4 complete)
//
// Startup sequence:
//  1. Load config from environment variables.
//  2. Open the shared SQLite Knowledge Graph.
//  3. Register validators V01–V20 (Sprint 22 — Phase 4 complete).
//  4. Start Prometheus /metrics HTTP endpoint.
//  5. Run validation cycles over pending vehicles.
//     (continuous daemon mode blocks until SIGINT/SIGTERM)
//
// Environment variables:
//   QUALITY_DB_PATH               path to shared SQLite KG            (default: ./data/discovery.db)
//   QUALITY_METRICS_ADDR          Prometheus bind addr                 (default: :9092)
//   QUALITY_BATCH_SIZE            vehicles per cycle                   (default: 100)
//   QUALITY_WORKERS               concurrent workers                   (default: 4)
//   QUALITY_ONE_SHOT              "true" = run once and exit           (default: false)
//   QUALITY_COUNTRIES             comma-separated ISO codes            (default: all)
//   QUALITY_SKIP_V01              "true" = skip VIN Checksum           (default: false)
//   QUALITY_SKIP_V02              "true" = skip NHTSA vPIC             (default: false)
//   QUALITY_SKIP_V03              "true" = skip DAT Codes              (default: false)
//   QUALITY_SKIP_V04              "true" = skip NLP Make/Model         (default: false)
//   QUALITY_SKIP_V05              "true" = skip Image Quality          (default: false)
//   QUALITY_SKIP_V06              "true" = skip Photo Count            (default: false)
//   QUALITY_SKIP_V07              "true" = skip Price Sanity           (default: false)
//   QUALITY_SKIP_V08              "true" = skip Mileage Sanity         (default: false)
//   QUALITY_SKIP_V09              "true" = skip Year Consistency       (default: false)
//   QUALITY_SKIP_V10              "true" = skip Source URL Liveness    (default: false)
//   QUALITY_SKIP_V11              "true" = skip NLG Description Quality (default: false)
//   QUALITY_SKIP_V12              "true" = skip Cross-Source Dedup     (default: false)
//   QUALITY_SKIP_V13              "true" = skip Metadata Completeness  (default: false)
//   QUALITY_SKIP_V14              "true" = skip Freshness              (default: false)
//   QUALITY_SKIP_V15              "true" = skip Dealer Trust           (default: false)
//   QUALITY_SKIP_V16              "true" = skip Photo pHash Dedup      (default: false)
//   QUALITY_SKIP_V17              "true" = skip Sold/Withdrawn         (default: false)
//   QUALITY_SKIP_V18              "true" = skip Language Consistency   (default: false)
//   QUALITY_SKIP_V19              "true" = skip Currency/EUR           (default: false)
//   QUALITY_SKIP_V20              "true" = skip Composite Score        (default: false)
//   IMAGE_HEAD_TIMEOUT_MS         HEAD timeout per photo URL           (default: 3000)
//   URL_LIVENESS_CACHE_TTL_HOURS  cache TTL for liveness checks        (default: 24)
package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/prometheus/client_golang/prometheus/promhttp"

	_ "modernc.org/sqlite"

	"cardex.eu/quality/internal/config"
	"cardex.eu/quality/internal/metrics"
	"cardex.eu/quality/internal/pipeline"
	"cardex.eu/quality/internal/storage"
	"cardex.eu/quality/internal/validator/v01_vin_checksum"
	"cardex.eu/quality/internal/validator/v02_nhtsa_vpic"
	"cardex.eu/quality/internal/validator/v03_dat_codes"
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
	"cardex.eu/quality/internal/validator/v21_entity_resolution"
)

// ensure metrics is initialised (init() registers counters).
var _ = metrics.VehiclesValidated

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(log)

	cfg, err := config.Load()
	if err != nil {
		log.Error("config load failed", "err", err)
		os.Exit(1)
	}

	store, err := storage.New(cfg.DBPath)
	if err != nil {
		log.Error("storage init failed", "err", err)
		os.Exit(1)
	}
	defer store.Close()

	// Register validators.
	var validators []pipeline.Validator
	if !cfg.SkipV01 {
		validators = append(validators, v01_vin_checksum.New())
	}
	if !cfg.SkipV02 {
		validators = append(validators, v02_nhtsa_vpic.New())
	}
	if !cfg.SkipV03 {
		validators = append(validators, v03_dat_codes.New())
	}
	if !cfg.SkipV04 {
		validators = append(validators, v04_nlp_makemodel.New())
	}
	if !cfg.SkipV05 {
		validators = append(validators, v05_image_quality.NewWithClient(
			&http.Client{Timeout: time.Duration(cfg.ImageHeadTimeoutMs) * time.Millisecond},
			500,
		))
	}
	if !cfg.SkipV06 {
		validators = append(validators, v06_photo_count.New())
	}
	if !cfg.SkipV07 {
		validators = append(validators, v07_price_sanity.New())
	}
	if !cfg.SkipV08 {
		validators = append(validators, v08_mileage_sanity.New())
	}
	if !cfg.SkipV09 {
		validators = append(validators, v09_year_consistency.New())
	}
	if !cfg.SkipV10 {
		validators = append(validators, v10_source_url_liveness.NewWithClient(
			&http.Client{
				Timeout: 10 * time.Second,
				CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
					return http.ErrUseLastResponse
				},
			},
			time.Duration(cfg.URLLivenessCacheTTLHours)*time.Hour,
		))
	}
	if !cfg.SkipV11 {
		validators = append(validators, v11_nlg_quality.New())
	}
	if !cfg.SkipV12 {
		// V12 uses a no-op store by default; wired to real KG in Phase 5.
		validators = append(validators, v12_cross_source_dedup.New())
	}
	if !cfg.SkipV13 {
		validators = append(validators, v13_completeness.New())
	}
	if !cfg.SkipV14 {
		validators = append(validators, v14_freshness.New())
	}
	if !cfg.SkipV15 {
		// V15 uses a no-op store by default; wired to real KG in Phase 5.
		validators = append(validators, v15_dealer_trust.New())
	}
	if !cfg.SkipV16 {
		validators = append(validators, v16_photo_phash.NewWithClient(
			&http.Client{Timeout: 15 * time.Second},
		))
	}
	if !cfg.SkipV17 {
		validators = append(validators, v17_sold_status.NewWithClient(
			&http.Client{Timeout: 15 * time.Second},
		))
	}
	if !cfg.SkipV18 {
		validators = append(validators, v18_language_consistency.New())
	}
	if !cfg.SkipV19 {
		validators = append(validators, v19_currency.New())
	}
	if !cfg.SkipV20 {
		// V20 uses a no-op store by default; wired to real KG in Phase 5.
		validators = append(validators, v20_composite.New())
	}
	if !cfg.SkipV21 {
		// V21 entity resolution: TFIDFEmbedder by default (pure Go, no Python needed).
		// Set QUALITY_V21_PYTHON=python3 to enable the mpnet subprocess embedder.
		v21cfg := v21_entity_resolution.Config{Threshold: cfg.V21Threshold}
		if python := os.Getenv("QUALITY_V21_PYTHON"); python != "" {
			v21cfg.Embedder = v21_entity_resolution.NewSubprocessEmbedder(python)
		}
		v21, err := v21_entity_resolution.NewWithDB(store.DB(), v21cfg)
		if err != nil {
			log.Warn("V21 entity resolution init failed — running without",
				"err", err,
			)
		} else {
			validators = append(validators, v21)
		}
	}

	if len(validators) == 0 {
		log.Error("all validators disabled — nothing to do")
		os.Exit(1)
	}

	pl := pipeline.New(store, validators...)

	// Start Prometheus metrics endpoint.
	go func() {
		mux := http.NewServeMux()
		mux.Handle("/metrics", promhttp.Handler())
		mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte("ok"))
		})
		log.Info("metrics server starting", "addr", cfg.MetricsAddr)
		if err := http.ListenAndServe(cfg.MetricsAddr, mux); err != nil {
			log.Error("metrics server error", "err", err)
		}
	}()

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	for {
		if ctx.Err() != nil {
			break
		}
		if err := runCycle(ctx, log, pl, store, cfg); err != nil {
			log.Error("validation cycle error", "err", err)
		}
		if cfg.OneShot {
			log.Info("one-shot mode: exiting after single cycle")
			break
		}
		select {
		case <-ctx.Done():
		case <-time.After(15 * time.Minute):
		}
	}
	log.Info("quality service stopped")
}

// runCycle fetches pending vehicles and runs the full validator pipeline on each.
func runCycle(
	ctx context.Context,
	log *slog.Logger,
	pl *pipeline.Pipeline,
	store *storage.SQLiteStorage,
	cfg *config.Config,
) error {
	vehicles, err := store.ListPendingVehicles(ctx, cfg.BatchSize)
	if err != nil {
		return err
	}
	log.Info("validation cycle starting", "vehicles", len(vehicles))

	// Refresh review queue pending gauge so the Prometheus metric stays current.
	if n, err := store.CountReviewQueuePending(ctx); err == nil {
		metrics.ReviewQueuePending.Set(float64(n))
	}

	for _, v := range vehicles {
		if ctx.Err() != nil {
			break
		}

		start := time.Now()
		summary, _ := pl.ValidateVehicle(ctx, v)
		dur := time.Since(start)

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

		log.Info("vehicle validated",
			"vehicle_id", v.InternalID,
			"critical", summary.HasCritical,
			"results", len(summary.Results),
			"duration_ms", dur.Milliseconds(),
		)
	}
	return nil
}
