// Command api-service is the CARDEX Cross-Border Price Intelligence REST API.
//
// It exposes market-price percentiles, cross-border arbitrage opportunities, a
// landed-cost calculator, and arbitrage alerts over HTTP, backed by PostgreSQL
// (vehicle listings) and Redis (API keys, rate limiting, response cache, alert
// notification state).
package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/prometheus/client_golang/prometheus/promhttp"

	"cardex.eu/api/internal/alerts"
	"cardex.eu/api/internal/arbitrage"
	"cardex.eu/api/internal/config"
	"cardex.eu/api/internal/docs"
	"cardex.eu/api/internal/httpx"
	"cardex.eu/api/internal/landedcost"
	"cardex.eu/api/internal/marketprice"
	"cardex.eu/api/internal/redisx"
	"cardex.eu/api/internal/restparams"
	"cardex.eu/api/internal/store"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		// Logger not built yet; use a default.
		slog.Error("config load failed", "err", err)
		os.Exit(1)
	}

	log := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: logLevel(cfg.LogLevel)}))
	slog.SetDefault(log)

	rootCtx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// --- Data stores ---
	startupCtx, cancel := context.WithTimeout(rootCtx, 15*time.Second)
	defer cancel()

	pg, err := store.NewPG(startupCtx, cfg.DatabaseURL, cfg.CHFtoEUR)
	if err != nil {
		log.Error("postgres connect failed", "err", err)
		os.Exit(1)
	}
	defer pg.Close()
	if err := pg.Ping(startupCtx); err != nil {
		log.Error("postgres ping failed", "err", err)
		os.Exit(1)
	}

	rdb := redisx.New(cfg.RedisAddr, cfg.RedisPassword, cfg.RedisDB)
	defer rdb.Close()
	if err := rdb.Ping(startupCtx); err != nil {
		log.Warn("redis ping failed — auth (non-bootstrap), rate limiting and cache degraded", "err", err)
	}

	// --- Domain services ---
	mpSvc := marketprice.New(pg)
	arbSvc := arbitrage.New(pg)

	alertStore := alerts.NewStore(pg.Pool())
	if err := alertStore.EnsureSchema(startupCtx); err != nil {
		log.Error("alerts schema setup failed", "err", err)
		os.Exit(1)
	}
	alertsHandler := alerts.NewHandler(alertStore, rdb, log)

	// --- Background alert evaluator ---
	if cfg.AlertsEnabled {
		notifier := alerts.NewNotifier(alerts.SMTPConfig{
			Host: cfg.SMTPHost, Port: cfg.SMTPPort, User: cfg.SMTPUser, Pass: cfg.SMTPPass, From: cfg.SMTPFrom,
		})
		evaluator := alerts.NewEvaluator(alertStore, arbSvc, rdb, notifier, cfg.AlertEvalInterval, log)
		go evaluator.Run(rootCtx)
	}

	// --- Routing ---
	auth := httpx.NewAuthenticator(rdb, log, cfg.BootstrapKey,
		cfg.RateLimitFree, cfg.RateLimitPaid, cfg.RateLimitEnterprise)

	apiMux := http.NewServeMux()
	apiMux.HandleFunc("GET /api/v1/market-price", marketprice.Handler(mpSvc, rdb, cfg.CacheTTL, cfg.QueryTimeout, log))
	apiMux.HandleFunc("GET /api/v1/arbitrage", arbitrage.Handler(arbSvc, rdb, cfg.CacheTTL, cfg.QueryTimeout, log))
	apiMux.HandleFunc("GET /api/v1/landed-cost", landedCostHandler(log))
	apiMux.HandleFunc("POST /api/v1/alerts", alertsHandler.Create)
	apiMux.HandleFunc("GET /api/v1/alerts", alertsHandler.List)
	apiMux.HandleFunc("GET /api/v1/alerts/{id}", alertsHandler.GetOne)
	apiMux.HandleFunc("DELETE /api/v1/alerts/{id}", alertsHandler.Delete)

	root := http.NewServeMux()
	root.Handle("/api/v1/", auth.Middleware()(apiMux))
	root.HandleFunc("GET /healthz", healthHandler(pg, rdb))
	root.Handle("GET /metrics", promhttp.Handler())
	root.HandleFunc("GET /openapi.yaml", docs.SpecHandler())
	root.HandleFunc("GET /docs", docs.DocsHandler())

	handler := httpx.Chain(root,
		httpx.Recover(log),
		httpx.Observe(log),
		httpx.CORS(cfg.CORSOrigins),
	)

	srv := &http.Server{
		Addr:              cfg.Addr,
		Handler:           handler,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
		MaxHeaderBytes:    1 << 20,
	}

	go func() {
		log.Info("api-service listening", "addr", cfg.Addr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Error("server error", "err", err)
			stop()
		}
	}()

	<-rootCtx.Done()
	log.Info("shutting down")
	shutCtx, shutCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutCancel()
	if err := srv.Shutdown(shutCtx); err != nil {
		log.Error("graceful shutdown incomplete", "err", err)
	}
}

// healthHandler reports 200 when PostgreSQL is reachable (Redis is non-critical),
// 503 otherwise.
func healthHandler(pg *store.PGStore, rdb *redisx.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
		defer cancel()
		if err := pg.Ping(ctx); err != nil {
			httpx.WriteError(w, http.StatusServiceUnavailable, "db_unavailable", "database unreachable")
			return
		}
		redisOK := rdb.Ping(ctx) == nil
		httpx.WriteJSON(w, http.StatusOK, map[string]any{
			"status": "ok",
			"redis":  redisOK,
		})
	}
}

// landedCostHandler serves GET /api/v1/landed-cost.
func landedCostHandler(log *slog.Logger) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		from := strings.ToUpper(strings.TrimSpace(q.Get("from")))
		to := strings.ToUpper(strings.TrimSpace(q.Get("to")))
		if from == "" || to == "" {
			httpx.WriteError(w, http.StatusBadRequest, "invalid_parameters", "'from' and 'to' country codes are required")
			return
		}
		if !restparams.SupportedCountries[from] || !restparams.SupportedCountries[to] {
			httpx.WriteError(w, http.StatusBadRequest, "invalid_parameters", "from/to must be one of DE, FR, ES, NL, BE, CH")
			return
		}
		price, err := strconv.ParseFloat(strings.TrimSpace(q.Get("price")), 64)
		if err != nil || price <= 0 {
			httpx.WriteError(w, http.StatusBadRequest, "invalid_parameters", "'price' must be a positive number (EUR)")
			return
		}

		co2 := atoiDefault(q.Get("co2"), 0)
		ageMonths := atoiDefault(q.Get("age_months"), 0)
		km := atoiDefault(q.Get("km"), 0)
		powerKW := atoiDefault(q.Get("power_kw"), 0)

		region, err := parseBERegion(q.Get("be_region"))
		if err != nil {
			httpx.WriteError(w, http.StatusBadRequest, "invalid_parameters", err.Error())
			return
		}

		veh := landedcost.Vehicle{
			PriceCents: int64(price*100 + 0.5),
			CO2gkm:     co2,
			Fuel:       landedcost.NormalizeFuel(q.Get("fuel")),
			AgeMonths:  ageMonths,
			Km:         km,
			PowerKW:    powerKW,
		}
		breakdown := landedcost.Compute(from, to, veh, landedcost.RegistrationOptions{BERegion: region})
		httpx.WriteJSON(w, http.StatusOK, breakdown)
	}
}

// parseBERegion validates the optional be_region parameter.
func parseBERegion(raw string) (landedcost.BERegion, error) {
	switch strings.ToUpper(strings.TrimSpace(raw)) {
	case "", "FLANDERS":
		return landedcost.BEFlanders, nil
	case "WALLONIA":
		return landedcost.BEWallonia, nil
	case "BRUSSELS":
		return landedcost.BEBrussels, nil
	default:
		return "", &paramError{"invalid be_region; supported: FLANDERS, WALLONIA, BRUSSELS"}
	}
}

type paramError struct{ msg string }

func (e *paramError) Error() string { return e.msg }

// atoiDefault parses an int, returning def on error/empty.
func atoiDefault(s string, def int) int {
	s = strings.TrimSpace(s)
	if s == "" {
		return def
	}
	n, err := strconv.Atoi(s)
	if err != nil {
		return def
	}
	return n
}

// logLevel maps a level name to a slog.Level.
func logLevel(name string) slog.Level {
	switch name {
	case "debug":
		return slog.LevelDebug
	case "warn":
		return slog.LevelWarn
	case "error":
		return slog.LevelError
	default:
		return slog.LevelInfo
	}
}
