// quality-service — Phase 4 Sprint 19
//
// Startup sequence:
//  1. Load config from environment variables.
//  2. Open the shared SQLite Knowledge Graph.
//  3. Register validators V01–V04 (Sprint 19).
//  4. Start Prometheus /metrics HTTP endpoint.
//  5. Run validation cycles over pending vehicles.
//     (continuous daemon mode blocks until SIGINT/SIGTERM)
//
// Environment variables:
//   QUALITY_DB_PATH        path to shared SQLite KG    (default: ./data/discovery.db)
//   QUALITY_METRICS_ADDR   Prometheus bind addr         (default: :9092)
//   QUALITY_BATCH_SIZE     vehicles per cycle           (default: 100)
//   QUALITY_WORKERS        concurrent workers           (default: 4)
//   QUALITY_ONE_SHOT       "true" = run once and exit   (default: false)
//   QUALITY_COUNTRIES      comma-separated ISO codes    (default: all)
//   QUALITY_SKIP_V01       "true" = skip VIN Checksum   (default: false)
//   QUALITY_SKIP_V02       "true" = skip NHTSA vPIC     (default: false)
//   QUALITY_SKIP_V03       "true" = skip DAT Codes      (default: false)
//   QUALITY_SKIP_V04       "true" = skip NLP Make/Model (default: false)
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
