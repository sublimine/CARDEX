// extraction-service -- Phase 3 Sprint 18 (12/12 strategies — Phase 3 complete)
//
// Startup sequence:
//  1. Load config from environment variables.
//  2. Open the shared SQLite Knowledge Graph.
//  3. Register extraction strategies E01–E12 (Sprint 18).
//  4. Start Prometheus /metrics HTTP endpoint.
//  5. Run extraction cycles for each configured country.
//     (continuous daemon mode blocks until SIGINT/SIGTERM)
//
// Environment variables:
//   EXTRACTION_DB_PATH          path to shared SQLite KG     (default: ./data/discovery.db)
//   EXTRACTION_METRICS_ADDR     Prometheus bind addr          (default: :9091)
//   EXTRACTION_BATCH_SIZE       dealers per cycle             (default: 50)
//   EXTRACTION_WORKERS          concurrent workers            (default: 4)
//   EXTRACTION_RATE_LIMIT_MS    ms between requests per dealer(default: 2000)
//   EXTRACTION_ONE_SHOT         "true" = run once and exit    (default: false)
//   EXTRACTION_COUNTRIES        comma-separated ISO codes     (default: FR)
//   EXTRACTION_SKIP_E01         "true" = skip JSON-LD strategy         (default: false)
//   EXTRACTION_SKIP_E02         "true" = skip CMS REST strategy         (default: false)
//   EXTRACTION_SKIP_E03         "true" = skip Sitemap XML strategy      (default: false)
//   EXTRACTION_SKIP_E04         "true" = skip RSS/Atom strategy         (default: false)
//   EXTRACTION_SKIP_E05         "true" = skip DMS API strategy          (default: false)
//   EXTRACTION_SKIP_E06         "true" = skip Microdata/RDFa strategy   (default: false)
//   EXTRACTION_SKIP_E07         "true" = skip Playwright XHR strategy   (default: false)
//   EXTRACTION_SKIP_E08         "true" = skip PDF Catalog strategy       (default: false)
//   EXTRACTION_SKIP_E09         "true" = skip Excel/CSV Feeds strategy   (default: false)
//   EXTRACTION_SKIP_E10         "true" = skip Email Inventory strategy   (default: false)
//   EXTRACTION_SKIP_E11         "true" = skip Edge Dealer Push strategy         (default: false)
//   EXTRACTION_SKIP_E12         "true" = skip Manual Review Queue         (default: false)
//   EDGE_GRPC_PORT              gRPC listen port for edge push           (default: 50051)
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

	_ "modernc.org/sqlite" // pure-Go SQLite driver

	"cardex.eu/extraction/internal/config"
	"cardex.eu/extraction/internal/extractor/e01_jsonld"
	"cardex.eu/extraction/internal/extractor/e02_cms_rest"
	"cardex.eu/extraction/internal/extractor/e03_sitemap"
	"cardex.eu/extraction/internal/extractor/e04_rss"
	"cardex.eu/extraction/internal/extractor/e05_dms_api"
	"cardex.eu/extraction/internal/extractor/e06_microdata"
	"cardex.eu/extraction/internal/extractor/e07_playwright_xhr"
	"cardex.eu/extraction/internal/extractor/e08_pdf"
	"cardex.eu/extraction/internal/extractor/e09_excel"
	"cardex.eu/extraction/internal/extractor/e10_email"
	"cardex.eu/extraction/internal/extractor/e11_edge"
	"cardex.eu/extraction/internal/extractor/e12_manual"
	"cardex.eu/extraction/internal/extractor/e13_vlm_vision"
	"cardex.eu/extraction/internal/metrics"
	"cardex.eu/extraction/internal/pipeline"
	"cardex.eu/extraction/internal/storage"
)

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

	// Register strategies.
	var strategies []pipeline.ExtractionStrategy
	if !cfg.SkipE01 {
		strategies = append(strategies, e01_jsonld.NewWithClient(
			&http.Client{Timeout: 15 * time.Second},
			cfg.RateLimitMs,
		))
	}
	if !cfg.SkipE02 {
		strategies = append(strategies, e02_cms_rest.NewWithClient(
			&http.Client{Timeout: 15 * time.Second},
			cfg.RateLimitMs/2, // E02 is cheaper; use shorter inter-page sleep
		))
	}
	if !cfg.SkipE03 {
		strategies = append(strategies, e03_sitemap.NewWithClient(
			&http.Client{Timeout: 15 * time.Second},
			cfg.RateLimitMs,
		))
	}
	if !cfg.SkipE04 {
		strategies = append(strategies, e04_rss.NewWithClient(
			&http.Client{Timeout: 15 * time.Second},
			cfg.RateLimitMs,
		))
	}
	if !cfg.SkipE05 {
		strategies = append(strategies, e05_dms_api.NewWithClient(
			&http.Client{Timeout: 15 * time.Second},
			cfg.RateLimitMs,
		))
	}
	if !cfg.SkipE06 {
		strategies = append(strategies, e06_microdata.NewWithClient(
			&http.Client{Timeout: 15 * time.Second},
			cfg.RateLimitMs,
		))
	}
	if !cfg.SkipE07 {
		// E07 uses a no-op XHR interceptor by default.
		// Inject a real PlaywrightBrowser interceptor to enable SPA extraction.
		strategies = append(strategies, e07_playwright_xhr.New())
	}
	if !cfg.SkipE08 {
		strategies = append(strategies, e08_pdf.NewWithClient(
			&http.Client{Timeout: 30 * time.Second},
			cfg.RateLimitMs,
		))
	}
	if !cfg.SkipE09 {
		strategies = append(strategies, e09_excel.NewWithClient(
			&http.Client{Timeout: 30 * time.Second},
			cfg.RateLimitMs,
		))
	}
	if !cfg.SkipE10 {
		// E10 is a stub: IMAP reader not wired until Phase 4.
		strategies = append(strategies, e10_email.New())
	}
	if !cfg.SkipE11 {
		// E11 receives inventory pushed from dealer-installed edge clients (priority 1500).
		strategies = append(strategies, e11_edge.New())
	}
	if cfg.VLMEnabled && !cfg.SkipE13 {
		// E13: VLM Screenshot Vision — last automated strategy (priority 100).
		// Opt-in via VLM_ENABLED=true. Requires ollama running with a vision model.
		// Model ladder: phi3.5-vision:latest → moondream2 → florence-2-base.
		strategies = append(strategies, e13_vlm_vision.New(e13_vlm_vision.VLMConfig{
			Model:      cfg.VLMModel,
			Endpoint:   cfg.VLMEndpoint,
			Timeout:    cfg.VLMTimeout,
			MaxRetries: cfg.VLMMaxRetries,
		}))
		log.Info("E13 VLM vision enabled", "model", cfg.VLMModel, "timeout", cfg.VLMTimeout)
	}
	if !cfg.SkipE12 {
		// E12 is the last-resort fallback: enqueues dealers for manual review.
		// Priority 0 — only runs when all automated strategies are exhausted.
		strategies = append(strategies, e12_manual.New())
	}

	if len(strategies) == 0 {
		log.Error("all strategies disabled — nothing to do")
		os.Exit(1)
	}

	orch := pipeline.New(store, strategies...)

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
		if err := runCycle(ctx, log, orch, store, cfg); err != nil {
			log.Error("extraction cycle error", "err", err)
		}
		if cfg.OneShot {
			log.Info("one-shot mode: exiting after single cycle")
			break
		}
		// Wait 30 minutes between full cycles in daemon mode.
		select {
		case <-ctx.Done():
		case <-time.After(30 * time.Minute):
		}
	}
	log.Info("extraction service stopped")
}

// runCycle processes one batch of pending dealers for all configured countries.
func runCycle(
	ctx context.Context,
	log *slog.Logger,
	orch *pipeline.Orchestrator,
	store *storage.SQLiteStorage,
	cfg *config.Config,
) error {
	dealers, err := store.ListPendingDealers(ctx, cfg.BatchSize)
	if err != nil {
		return err
	}
	log.Info("extraction cycle starting", "dealers", len(dealers))

	for _, dealer := range dealers {
		if ctx.Err() != nil {
			break
		}

		start := time.Now()
		result, err := orch.ExtractForDealer(ctx, dealer)
		dur := time.Since(start)

		if err != nil {
			log.Warn("extraction failed",
				"dealer_id", dealer.ID,
				"domain", dealer.Domain,
				"err", err,
			)
			metrics.ExtractionTotal.WithLabelValues("none", dealer.CountryCode, "error").Inc()
			continue
		}

		strategyID := result.Strategy
		country := dealer.CountryCode

		metrics.ExtractionDuration.WithLabelValues(strategyID).Observe(dur.Seconds())
		metrics.VehiclesExtracted.WithLabelValues(strategyID, country).Add(float64(len(result.Vehicles)))

		if result.FullSuccess || result.PartialSuccess {
			metrics.ExtractionTotal.WithLabelValues(strategyID, country, "success").Inc()
			log.Info("extraction succeeded",
				"dealer_id", dealer.ID,
				"strategy", strategyID,
				"vehicles", len(result.Vehicles),
				"full_success", result.FullSuccess,
				"duration_ms", dur.Milliseconds(),
			)
		} else {
			metrics.ExtractionTotal.WithLabelValues(strategyID, country, "dead_letter").Inc()
			metrics.DeadLetterTotal.WithLabelValues(country).Inc()
			log.Warn("no extraction strategy succeeded",
				"dealer_id", dealer.ID,
				"domain", dealer.Domain,
			)
		}

		_ = store.MarkExtractionDone(ctx, dealer.ID, strategyID)
	}
	return nil
}
