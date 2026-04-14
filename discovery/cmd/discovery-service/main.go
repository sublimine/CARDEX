// discovery-service — Phase 2 Sprint 8
//
// Startup sequence:
//  1. Load config from environment variables.
//  2. Open (or create) the SQLite Knowledge Graph and apply migrations.
//  3. Initialise the Playwright browser (unless DISCOVERY_SKIP_BROWSER=true).
//  4. Start Prometheus /metrics HTTP endpoint.
//  5. Run a discovery cycle for each configured country (Family A, B, C, F, G, H).
//     (continuous daemon mode blocks until SIGINT/SIGTERM)
//
// Environment variables:
//   DISCOVERY_DB_PATH         path to SQLite KG file           (default: ./data/discovery.db)
//   METRICS_ADDR              HTTP bind address                 (default: :9090)
//   INSEE_TOKEN               INSEE Sirene Bearer token         (required for FR)
//   INSEE_RATE_PER_MIN        Sirene req/min ceiling            (default: 25)
//   OFFENEREGISTER_DB_PATH    OffeneRegister SQLite path        (default: ./data/offeneregister.db)
//   KVK_API_KEY               KvK Zoeken API key                (optional; Path 2 skipped if absent)
//   KBO_USER                  KBO Open Data portal username     (required for BE)
//   KBO_PASS                  KBO Open Data portal password     (required for BE)
//   DISCOVERY_ONE_SHOT        "true" = run once and exit        (default: false)
//   DISCOVERY_COUNTRIES       comma-separated ISO-3166-1 codes  (default: FR)
//   DISCOVERY_SKIP_BROWSER    "true" = skip Playwright init     (default: false)
//   DISCOVERY_SKIP_FAMILY_C   "true" = skip Family C entirely   (default: false)
//   DISCOVERY_SKIP_FAMILY_F   "true" = skip Family F entirely   (default: false)
//   DISCOVERY_SKIP_FAMILY_G   "true" = skip Family G entirely   (default: false)
//   DISCOVERY_SKIP_FAMILY_H   "true" = skip Family H entirely   (default: false)
package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"

	"github.com/prometheus/client_golang/prometheus/promhttp"

	_ "modernc.org/sqlite" // SQLite driver — pure Go, no CGO

	"cardex.eu/discovery/internal/browser"
	"cardex.eu/discovery/internal/config"
	"cardex.eu/discovery/internal/db"
	"cardex.eu/discovery/internal/families/familia_a"
	"cardex.eu/discovery/internal/families/familia_b"
	"cardex.eu/discovery/internal/families/familia_c"
	"cardex.eu/discovery/internal/families/familia_f"
	"cardex.eu/discovery/internal/families/familia_g"
	"cardex.eu/discovery/internal/families/familia_h"
	"cardex.eu/discovery/internal/kg"
	_ "cardex.eu/discovery/internal/metrics" // register Prometheus metrics
	"cardex.eu/discovery/internal/runner"
)

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}))

	cfg, err := config.LoadFromEnv()
	if err != nil {
		log.Error("config load failed", "err", err)
		os.Exit(1)
	}

	// ── Database ───────────────────────────────────────────────────────────
	database, err := db.Open(cfg.DBPath)
	if err != nil {
		log.Error("db.Open failed", "path", cfg.DBPath, "err", err)
		os.Exit(1)
	}
	defer database.Close()
	log.Info("knowledge graph opened", "path", cfg.DBPath)

	graph := kg.NewSQLiteGraph(database)

	// ── Browser (Playwright) ───────────────────────────────────────────────
	// browser.Browser is nil when SkipBrowser=true or Playwright unavailable.
	// All browser-dependent sub-techniques (F.2 AutoScout24, G.FR.1 Mobilians,
	// H.VWG) skip gracefully when b is nil.
	var b browser.Browser
	if !cfg.SkipBrowser {
		pb, browserErr := browser.New(nil, database)
		if browserErr != nil {
			log.Warn("browser init failed; F.2/G.FR.1/H.VWG will be skipped",
				"err", browserErr,
				"hint", "set DISCOVERY_SKIP_BROWSER=true to suppress this warning",
			)
		} else {
			b = pb
			defer func() {
				if err := b.Close(); err != nil {
					log.Warn("browser close error", "err", err)
				}
			}()
			log.Info("browser initialised (Playwright/Chromium)")
		}
	} else {
		log.Info("browser skipped (DISCOVERY_SKIP_BROWSER=true)")
	}

	// ── Prometheus metrics server ──────────────────────────────────────────
	mux := http.NewServeMux()
	mux.Handle("/metrics", promhttp.Handler())
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	srv := &http.Server{Addr: cfg.MetricsAddr, Handler: mux}
	go func() {
		log.Info("metrics server listening", "addr", cfg.MetricsAddr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Error("metrics server error", "err", err)
		}
	}()

	// ── Discovery run ──────────────────────────────────────────────────────
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	familyACfg := &familia_a.Config{
		InseeToken:           cfg.InseeToken,
		InseeRatePerMin:      cfg.InseeRatePerMin,
		OffeneRegisterDBPath: cfg.OffeneRegisterDBPath,
		KvKAPIKey:            cfg.KvKAPIKey,
		KBOUser:              cfg.KBOUser,
		KBOPass:              cfg.KBOPass,
	}
	familyA := familia_a.New(graph, familyACfg, database)
	familyB := familia_b.New(graph, familia_b.Config{Countries: cfg.Countries})

	type familyRunner interface {
		FamilyID() string
		Run(ctx context.Context, country string) (*runner.FamilyResult, error)
	}
	families := []familyRunner{familyA, familyB}
	if !cfg.SkipFamilyC {
		families = append(families, familia_c.New(graph, database))
	}
	if !cfg.SkipFamilyF {
		families = append(families, familia_f.New(graph, database, b))
	}
	if !cfg.SkipFamilyG {
		families = append(families, familia_g.New(graph, b))
	}
	if !cfg.SkipFamilyH {
		families = append(families, familia_h.New(graph, b))
	}

	for _, country := range cfg.Countries {
		for _, fam := range families {
			log.Info("starting discovery cycle", "family", fam.FamilyID(), "country", country)
			result, err := fam.Run(ctx, country)
			if err != nil {
				log.Error("discovery cycle error",
					"family", fam.FamilyID(),
					"country", country,
					"err", err,
				)
				continue
			}
			log.Info("discovery cycle complete",
				"family", fam.FamilyID(),
				"country", country,
				"new", result.TotalNew,
				"errors", result.TotalErrors,
				"duration_s", result.Duration.Seconds(),
			)
		}
	}

	if !cfg.OneShot {
		log.Info("discovery cycle done; blocking until signal (set DISCOVERY_ONE_SHOT=true to exit)")
		<-ctx.Done()
	}

	log.Info("discovery service shutting down")
	_ = srv.Shutdown(context.Background())
}
