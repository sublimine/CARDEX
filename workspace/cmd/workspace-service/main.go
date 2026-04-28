// Package main is the CARDEX Workspace Service entry point.
//
// Exposes HTTP sub-trees on a single port:
//
//	/api/v1/auth/*         — Authentication (login, register, refresh) — public
//	/api/v1/check/*        — Vehicle history report (VIN decode + registry data) — public with rate limit
//	/api/v1/documents/*    — PDF generation (contracts, invoices, sheets, CMR)
//	/api/v1/inbox/*        — Unified dealer inbox (conversations, messages, templates)
//	/api/v1/ingest/*       — Inquiry ingestion (web webhook, manual)
//	/api/v1/vehicles/*     — Per-vehicle financial transactions, P&L, and media reorder
//	/api/v1/fleet/*        — Fleet-wide P&L aggregation and alerts
//	/api/v1/transactions/* — Transaction update / delete
//	/api/v1/kanban/*       — Kanban board (columns, cards, WIP limits, state machine)
//	/api/v1/calendar/*     — Calendar events (CRUD, upcoming)
//	/health                — Health check
//
// Environment variables:
//
//	WORKSPACE_PORT       (default: 8506)
//	WORKSPACE_DB_PATH    (default: data/workspace.db)
//	WORKSPACE_MEDIA_DIR  (default: data/workspace/media)
//	CARDEX_JWT_SECRET    (default: random 32 bytes — use a fixed value in production)
//	SMTP_HOST            (default: "")
//	SMTP_PORT            (default: 25)
//	SMTP_USER            (default: "")
//	SMTP_PASS            (default: "")
//	SMTP_FROM            (default: "")
package main

import (
	"context"
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"cardex.eu/workspace/internal/auth"
	"cardex.eu/workspace/internal/check"
	"cardex.eu/workspace/internal/check/matraba"
	"cardex.eu/workspace/internal/documents"
	"cardex.eu/workspace/internal/finance"
	"cardex.eu/workspace/internal/inbox"
	"cardex.eu/workspace/internal/kanban"
	"cardex.eu/workspace/internal/media"
	"cardex.eu/workspace/internal/middleware"
	"cardex.eu/workspace/internal/syndication"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	_ "modernc.org/sqlite"
)

func main() {
	log := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))

	port := envOrDefault("WORKSPACE_PORT", "8506")
	dbPath := envOrDefault("WORKSPACE_DB_PATH", "data/workspace.db")
	mediaDir := envOrDefault("WORKSPACE_MEDIA_DIR", "data/workspace/media")

	// ── JWT secret ───────────────────────────────────────────────────────────
	jwtSecret := os.Getenv("CARDEX_JWT_SECRET")
	if jwtSecret == "" {
		b := make([]byte, 32)
		if _, err := rand.Read(b); err != nil {
			log.Error("generate jwt secret", "err", err)
			os.Exit(1)
		}
		jwtSecret = hex.EncodeToString(b)
		log.Warn("CARDEX_JWT_SECRET not set — using ephemeral random secret (tokens will be invalidated on restart)")
	}
	jwtSvc := auth.NewJWTService([]byte(jwtSecret), 24*time.Hour)

	smtpPort, _ := strconv.Atoi(envOrDefault("SMTP_PORT", "25"))
	smtpCfg := inbox.SMTPConfig{
		Host: os.Getenv("SMTP_HOST"),
		Port: smtpPort,
		User: os.Getenv("SMTP_USER"),
		Pass: os.Getenv("SMTP_PASS"),
		From: os.Getenv("SMTP_FROM"),
	}

	if err := os.MkdirAll("data/workspace", 0755); err != nil {
		log.Error("create data dir", "err", err)
		os.Exit(1)
	}

	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		log.Error("open db", "err", err)
		os.Exit(1)
	}
	db.SetMaxOpenConns(1) // SQLite single-writer
	defer db.Close()

	// Context cancelled on SIGTERM/SIGINT for graceful shutdown.
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()

	// ── Auth service (must be first — creates crm_users) ────────────────────
	if err := auth.EnsureSchema(db); err != nil {
		log.Error("auth schema", "err", err)
		os.Exit(1)
	}
	registerToken := os.Getenv("REGISTER_TOKEN")
	if registerToken == "" {
		log.Warn("REGISTER_TOKEN not set — self-registration is disabled")
	}
	authHandler := auth.NewHandlerWithRegisterToken(db, jwtSvc, registerToken)

	// ── Documents service (EnsureSchema called inside NewService) ────────────
	docSvc, err := documents.NewService(ctx, db, mediaDir)
	if err != nil {
		log.Error("documents service init", "err", err)
		os.Exit(1)
	}

	// ── Inbox service (owns CRM base tables: contacts, vehicles, deals, …) ──
	if err := inbox.EnsureSchema(db); err != nil {
		log.Error("inbox schema", "err", err)
		os.Exit(1)
	}
	if err := inbox.SeedSystemTemplates(db); err != nil {
		log.Error("seed templates", "err", err)
		os.Exit(1)
	}
	inboxSrv := inbox.NewServer(db, smtpCfg, log)

	// ── Finance service ──────────────────────────────────────────────────────
	if err := finance.EnsureSchema(db); err != nil {
		log.Error("finance schema", "err", err)
		os.Exit(1)
	}
	finStore := finance.NewStore(db)
	finCalc := finance.NewCalculator(finStore)
	finAlerts := finance.NewAlertService(finStore)
	finHandler := finance.Handler(finStore, finCalc, finAlerts)

	// ── Kanban + Calendar service (EnsureSchema called inside NewStore) ──────
	kanbanStore, err := kanban.NewStore(db)
	if err != nil {
		log.Error("kanban store init", "err", err)
		os.Exit(1)
	}
	kanbanSrv := kanban.NewServer(kanbanStore, log)

	// ── Media storage (reuses shared DB to avoid second SQLite connection) ───
	mediaSto, err := media.NewFSStorageWithDB(db, mediaDir)
	if err != nil {
		log.Error("media storage init", "err", err)
		os.Exit(1)
	}

	// ── Syndication: schema + engine + scheduler ─────────────────────────────
	if err := syndication.EnsureSchema(db); err != nil {
		log.Error("syndication schema", "err", err)
		os.Exit(1)
	}
	syndicationEngine, err := syndication.NewEngine(db, log)
	if err != nil {
		log.Error("syndication engine init", "err", err)
		os.Exit(1)
	}
	// getListing queries crm_vehicles for the minimal fields needed by adapters.
	// Photo URLs are intentionally empty here — they are passed at publish time
	// by the caller that holds the full media export result.
	getListing := func(vehicleID string) (syndication.PlatformListing, error) {
		var l syndication.PlatformListing
		row := db.QueryRowContext(ctx,
			`SELECT id, COALESCE(make,''), COALESCE(model,''), COALESCE(year,0),
			        COALESCE(vin,''), COALESCE(status,'')
			 FROM crm_vehicles WHERE id=?`, vehicleID)
		var statusIgnored string
		if err := row.Scan(&l.VehicleID, &l.Make, &l.Model, &l.Year, &l.VIN, &statusIgnored); err != nil {
			if err == sql.ErrNoRows {
				return l, fmt.Errorf("syndication getListing: vehicle %s not found", vehicleID)
			}
			return l, fmt.Errorf("syndication getListing: %w", err)
		}
		return l, nil
	}
	syndicationScheduler := syndication.NewScheduler(syndicationEngine, getListing, log)
	go syndicationScheduler.Run(ctx)

	// ── Vehicle history check service ────────────────────────────────────────
	if err := check.EnsureSchema(db); err != nil {
		log.Error("check schema", "err", err)
		os.Exit(1)
	}
	checkCache := check.NewCache(db)
	nhtsaBaseURL := envOrDefault("NHTSA_BASE_URL", "https://vpic.nhtsa.dot.gov")
	rdwBaseURL := envOrDefault("RDW_BASE_URL", "https://opendata.rdw.nl/resource")
	checkDecoder := check.NewVINDecoderWithBase(nhtsaBaseURL)
	checkProviders := []check.RegistryProvider{
		check.NewNLProviderWithBase(rdwBaseURL),
		check.NewFRProvider(),
		check.NewBEProvider(),
		check.NewESProvider(),
		check.NewDEProvider(),
		check.NewCHProvider(),
	}
	checkEngine := check.NewEngine(checkCache, checkDecoder, checkProviders)

	// DGT MATRABA store (optional) — once the matraba_vehicles table has
	// been populated by `cmd/matraba-import`, the ES resolver enriches its
	// PlateResult with DGT technical fields (Euro norm, CO₂, homologation,
	// wheelbase, municipality). Absence of the table is not fatal: the
	// resolver operates without it.
	var matrabaStore *matraba.Store
	if err := matraba.EnsureSchema(db); err == nil {
		matrabaStore = matraba.NewStore(db)
	} else {
		slog.Warn("matraba schema init failed — ES enrichment disabled", "err", err)
	}

	// CM_PROXY_URL: when set, ES plate lookups route through the Vercel edge
	// proxy instead of calling comprobarmatricula.com directly, eliminating the
	// per-IP rate limit. Example: "https://cardex-cm-proxy.vercel.app"
	cmProxyURL := os.Getenv("CM_PROXY_URL")
	checkPlateRegistry := check.NewPlateRegistryWithOptions(rdwBaseURL, checkCache, matrabaStore, cmProxyURL)
	checkHandler := check.NewHandlerWithValidatorAndPlates(checkEngine, checkCache, func(token string) bool {
		_, err := jwtSvc.ValidateToken(token)
		return err == nil
	}, checkPlateRegistry)

	// ── Root mux ─────────────────────────────────────────────────────────────
	mux := http.NewServeMux()
	requireAuth := auth.RequireAuth(jwtSvc)

	// Auth endpoints — no middleware (public)
	authHandler.Register(mux)

	// Vehicle history check — public with built-in per-IP rate limiting
	checkHandler.Register(mux)

	// Vehicle dossier — public with built-in per-IP rate limiting (same as check)
	dossierHandler := check.NewDossierHandler(checkPlateRegistry, func(token string) bool {
		_, err := jwtSvc.ValidateToken(token)
		return err == nil
	})
	dossierHandler.Register(mux)

	// All other handlers wrapped with RequireAuth
	// Documents
	mux.Handle("/api/v1/documents/", requireAuth(documents.Handler(docSvc)))

	// Inbox
	inboxMux := inboxSrv.Handler()
	mux.Handle("/api/v1/inbox/", requireAuth(inboxMux))
	mux.Handle("/api/v1/inbox", requireAuth(inboxMux))
	mux.Handle("/api/v1/templates/", requireAuth(inboxMux))
	mux.Handle("/api/v1/templates", requireAuth(inboxMux))
	mux.Handle("/api/v1/ingest/", requireAuth(inboxMux))

	// CRM listing routes (owned by inbox package — uses shared CRM tables).
	// Exact path patterns so they coexist with the finance /vehicles/ subtree.
	mux.Handle("GET /api/v1/vehicles", requireAuth(inboxMux))
	mux.Handle("GET /api/v1/contacts", requireAuth(inboxMux))
	mux.Handle("GET /api/v1/contacts/", requireAuth(inboxMux))
	mux.Handle("GET /api/v1/deals", requireAuth(inboxMux))
	mux.Handle("PATCH /api/v1/deals/", requireAuth(inboxMux))
	mux.Handle("POST /api/v1/deals", requireAuth(inboxMux))

	// Finance
	mux.Handle("/api/v1/vehicles/", requireAuth(finHandler))
	mux.Handle("/api/v1/fleet/", requireAuth(finHandler))
	mux.Handle("/api/v1/transactions/", requireAuth(finHandler))

	// Media reorder
	mux.Handle("PUT /api/v1/vehicles/{id}/media/reorder", requireAuth(media.ReorderHandler(mediaSto)))

	// Kanban + Calendar
	kanbanSrv.RegisterWithMiddleware(mux, requireAuth)

	// KPI summary — aggregates from CRM tables for the dashboard.
	crmStore := inbox.NewCRMStore(db)
	mux.Handle("GET /api/v1/kpi", requireAuth(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		tenantID := r.Header.Get("X-Tenant-ID")
		if tenantID == "" {
			http.Error(w, `{"error":"X-Tenant-ID required"}`, http.StatusBadRequest)
			return
		}
		kpi, err := crmStore.KPISummary(tenantID)
		if err != nil {
			http.Error(w, `{"error":"internal"}`, http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(kpi)
	})))

	// Health (public)
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"status":"ok","time":"%s"}`, time.Now().UTC().Format(time.RFC3339))
	})

	// Wrap main mux with CORS so browser cross-origin calls (tunnel, CDN, etc.) work.
	corsOrigins := []string{
		"http://localhost:5173",
		"http://localhost:3000",
		"http://localhost:4173",
		".trycloudflare.com",
		".ngrok-free.app",
		".ngrok.io",
		".loca.lt",
		".serveo.net",
	}
	if extra := os.Getenv("CORS_ORIGIN"); extra != "" {
		corsOrigins = append(corsOrigins, extra)
	}
	corsHandler := middleware.CORS(corsOrigins)(mux)

	addr := ":" + port
	log.Info("workspace-service starting", "addr", addr, "db", dbPath)
	srv := &http.Server{
		Addr:         addr,
		Handler:      corsHandler,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 60 * time.Second,
		IdleTimeout:  120 * time.Second,
	}

	// ── Prometheus metrics server ─────────────────────────────────────────────
	metricsAddr := envOrDefault("WORKSPACE_METRICS_ADDR", ":9091")
	metricsMux := http.NewServeMux()
	metricsMux.Handle("/metrics", promhttp.Handler())
	metricsSrv := &http.Server{
		Addr:        metricsAddr,
		Handler:     metricsMux,
		ReadTimeout: 5 * time.Second,
	}
	go func() {
		log.Info("metrics server starting", "addr", metricsAddr)
		if err := metricsSrv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Error("metrics server error", "err", err)
		}
	}()

	// Start main server in goroutine so we can listen for shutdown.
	go func() {
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Error("server error", "err", err)
		}
	}()
	log.Info("workspace-service ready", "addr", addr)

	// Block until shutdown signal.
	<-ctx.Done()
	log.Info("shutdown signal received — draining connections")
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	_ = metricsSrv.Shutdown(shutdownCtx)
	if err := srv.Shutdown(shutdownCtx); err != nil {
		log.Error("graceful shutdown error", "err", err)
	}
	log.Info("workspace-service stopped")
}

func envOrDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
