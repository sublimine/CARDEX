// Package main — CARDEX REST API server.
//
// Route groups:
//   /api/v1/marketplace  — public car search, listing detail, price alerts
//   /api/v1/analytics    — price index, market depth, demand signals, heatmap
//   /api/v1/vin          — free VIN history report (OSINT + accumulated mileage)
//   /api/v1/dealer       — dealer SaaS: inventory, multiposting, CRM, audit
//   /api/v1/auth         — dealer registration, JWT RS256 login
//
// Authentication: public endpoints open; dealer endpoints require JWT RS256.
// CORS: configured for Next.js web app origin.
package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/cardex/alpha/pkg/nlc"
	"github.com/cardex/alpha/pkg/tax"
	"github.com/cardex/api/internal/handlers"
	"github.com/cardex/api/internal/middleware"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"

	clickhouse "github.com/ClickHouse/clickhouse-go/v2"
	meilisearch "github.com/meilisearch/meilisearch-go"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	// ---- Connections --------------------------------------------------------
	pool := mustPG(ctx)
	rdb := mustRedis(ctx)
	ch := mustClickHouse()
	meili := mustMeili()
	defer pool.Close()
	defer rdb.Close()

	// ---- Dependencies -------------------------------------------------------
	nlcCalc := nlc.New(rdb, &tax.SpainCalculator{}, &tax.FranceCalculator{}, &tax.NetherlandsCalculator{})

	var meiliIndex meilisearch.IndexManager
	if meili != nil {
		idx := meili.Index("vehicles")
		meiliIndex = idx
	}

	deps := &handlers.Deps{
		DB:      pool,
		Redis:   rdb,
		CH:      ch,
		Meili:   meiliIndex,
		NLCCalc: nlcCalc,
	}

	rl := middleware.NewRateLimiter(rdb)

	// ---- Router -------------------------------------------------------------
	mux := http.NewServeMux()

	// Health (no rate limit)
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"status":"ok"}`))
	})

	// Marketplace (public — 120 req/min per IP)
	mux.Handle("GET /api/v1/marketplace/search", rl.Public(http.HandlerFunc(deps.MarketplaceSearch)))
	mux.Handle("GET /api/v1/marketplace/listing/{ulid}", rl.Public(http.HandlerFunc(deps.ListingDetail)))
	mux.Handle("POST /api/v1/marketplace/alerts", rl.Public(middleware.Auth(deps.CreatePriceAlert)))
	mux.HandleFunc("GET /api/v1/marketplace/alerts", middleware.Auth(deps.ListPriceAlerts))
	mux.HandleFunc("DELETE /api/v1/marketplace/alerts/{id}", middleware.Auth(deps.DeletePriceAlert))

	// Analytics (public — 120 req/min)
	mux.Handle("GET /api/v1/analytics/price-index", rl.Public(http.HandlerFunc(deps.PriceIndex)))
	mux.Handle("GET /api/v1/analytics/market-depth", rl.Public(http.HandlerFunc(deps.MarketDepth)))
	mux.Handle("GET /api/v1/analytics/demand", rl.Public(http.HandlerFunc(deps.DemandSignals)))
	mux.Handle("GET /api/v1/analytics/heatmap", rl.Public(http.HandlerFunc(deps.Heatmap)))
	mux.Handle("GET /api/v1/analytics/dom", rl.Public(http.HandlerFunc(deps.DOMDistribution)))
	mux.Handle("GET /api/v1/analytics/volatility", rl.Public(http.HandlerFunc(deps.PriceVolatility)))

	// VIN History (public, free — 120 req/min)
	mux.Handle("GET /api/v1/vin/{vin}", rl.Public(http.HandlerFunc(deps.VINHistory)))

	// Auth (strict — 20 req/min per IP)
	mux.Handle("POST /api/v1/auth/register", rl.Strict(http.HandlerFunc(deps.DealerRegister)))
	mux.Handle("POST /api/v1/auth/login", rl.Strict(http.HandlerFunc(deps.DealerLogin)))
	mux.Handle("POST /api/v1/auth/refresh", rl.Strict(http.HandlerFunc(deps.TokenRefresh)))
	mux.Handle("POST /api/v1/auth/forgot-password", rl.Strict(http.HandlerFunc(deps.ForgotPassword)))
	mux.Handle("POST /api/v1/auth/reset-password", rl.Strict(http.HandlerFunc(deps.ResetPassword)))
	mux.Handle("GET /api/v1/auth/verify-email", rl.Strict(http.HandlerFunc(deps.VerifyEmail)))

	// Dealer SaaS (JWT required — 600 req/min per entity)
	mux.Handle("GET /api/v1/dealer/inventory", rl.Authenticated(middleware.Auth(deps.InventoryList)))
	mux.Handle("POST /api/v1/dealer/inventory", rl.Authenticated(middleware.Auth(deps.InventoryCreate)))
	mux.Handle("PUT /api/v1/dealer/inventory/{ulid}", rl.Authenticated(middleware.Auth(deps.InventoryUpdate)))
	mux.Handle("DELETE /api/v1/dealer/inventory/{ulid}", rl.Authenticated(middleware.Auth(deps.InventoryDelete)))
	mux.Handle("POST /api/v1/dealer/inventory/import-url", rl.Authenticated(middleware.Auth(deps.InventoryImportURL)))

	mux.Handle("POST /api/v1/dealer/publish", rl.Authenticated(middleware.Auth(deps.PublishJob)))
	mux.Handle("GET /api/v1/dealer/publish/{job_id}", rl.Authenticated(middleware.Auth(deps.PublishJobStatus)))

	mux.Handle("GET /api/v1/dealer/leads", rl.Authenticated(middleware.Auth(deps.LeadsList)))
	mux.Handle("POST /api/v1/dealer/leads", rl.Authenticated(middleware.Auth(deps.LeadCreate)))
	mux.Handle("PUT /api/v1/dealer/leads/{id}/status", rl.Authenticated(middleware.Auth(deps.LeadStatusUpdate)))

	mux.Handle("GET /api/v1/dealer/pricing/{ulid}", rl.Authenticated(middleware.Auth(deps.PricingIntelligence)))
	mux.Handle("GET /api/v1/dealer/audit", rl.Authenticated(middleware.Auth(deps.MarketingAudit)))
	mux.Handle("POST /api/v1/dealer/audit/trigger", rl.Authenticated(middleware.Auth(deps.TriggerMarketingAudit)))

	mux.Handle("GET /api/v1/dealer/nlc/{ulid}", rl.Authenticated(middleware.Auth(deps.NLCCalculation)))
	mux.Handle("GET /api/v1/dealer/sdi/{ulid}", rl.Authenticated(middleware.Auth(deps.SDIScore)))

	// TradingCar (public — 120 req/min)
	mux.Handle("GET /api/v1/tradingcar/candles", rl.Public(http.HandlerFunc(deps.TradingCarCandles)))
	mux.Handle("GET /api/v1/tradingcar/tickers", rl.Public(http.HandlerFunc(deps.TradingCarTickers)))
	mux.Handle("GET /api/v1/tradingcar/scanner", rl.Public(http.HandlerFunc(deps.TradingCarScanner)))
	mux.Handle("GET /api/v1/tradingcar/compare", rl.Public(http.HandlerFunc(deps.TradingCarCompare)))

	// Arbitrage (public read — 120/min; booking JWT — 600/min)
	mux.Handle("GET /api/v1/arbitrage/opportunities", rl.Public(http.HandlerFunc(deps.ArbitrageOpportunities)))
	mux.Handle("GET /api/v1/arbitrage/routes", rl.Public(http.HandlerFunc(deps.ArbitrageRouteStats)))
	mux.Handle("GET /api/v1/arbitrage/nlc/{ticker}/{origin}/{dest}", rl.Public(http.HandlerFunc(deps.ArbitrageNLCBreakdown)))
	mux.Handle("POST /api/v1/arbitrage/book/{opportunity_id}", rl.Authenticated(middleware.Auth(deps.ArbitrageBookOpportunity)))
	mux.Handle("GET /api/v1/arbitrage/booked", rl.Authenticated(middleware.Auth(deps.ArbitrageBookedList)))

	// CRM (JWT — 600 req/min)
	mux.Handle("GET /api/v1/dealer/crm/dashboard", rl.Authenticated(middleware.Auth(deps.CRMDashboard)))
	mux.Handle("GET /api/v1/dealer/crm/vehicles", rl.Authenticated(middleware.Auth(deps.CRMVehicleList)))
	mux.Handle("POST /api/v1/dealer/crm/vehicles", rl.Authenticated(middleware.Auth(deps.CRMVehicleCreate)))
	mux.Handle("GET /api/v1/dealer/crm/vehicles/{ulid}", rl.Authenticated(middleware.Auth(deps.CRMVehicleGet)))
	mux.Handle("PUT /api/v1/dealer/crm/vehicles/{ulid}", rl.Authenticated(middleware.Auth(deps.CRMVehicleUpdate)))
	mux.Handle("DELETE /api/v1/dealer/crm/vehicles/{ulid}", rl.Authenticated(middleware.Auth(deps.CRMVehicleDelete)))
	mux.Handle("GET /api/v1/dealer/crm/contacts", rl.Authenticated(middleware.Auth(deps.CRMContactList)))
	mux.Handle("POST /api/v1/dealer/crm/contacts", rl.Authenticated(middleware.Auth(deps.CRMContactCreate)))
	mux.Handle("GET /api/v1/dealer/crm/contacts/{ulid}", rl.Authenticated(middleware.Auth(deps.CRMContactGet)))
	mux.Handle("PUT /api/v1/dealer/crm/contacts/{ulid}", rl.Authenticated(middleware.Auth(deps.CRMContactUpdate)))
	mux.Handle("GET /api/v1/dealer/crm/deals", rl.Authenticated(middleware.Auth(deps.CRMDealList)))
	mux.Handle("POST /api/v1/dealer/crm/deals", rl.Authenticated(middleware.Auth(deps.CRMDealCreate)))
	mux.Handle("PUT /api/v1/dealer/crm/deals/{ulid}", rl.Authenticated(middleware.Auth(deps.CRMDealUpdate)))
	mux.Handle("GET /api/v1/dealer/crm/pipeline/stages", rl.Authenticated(middleware.Auth(deps.CRMPipelineStages)))
	mux.Handle("GET /api/v1/dealer/crm/pipeline/kanban", rl.Authenticated(middleware.Auth(deps.CRMPipelineKanban)))
	mux.Handle("POST /api/v1/dealer/crm/communications", rl.Authenticated(middleware.Auth(deps.CRMCommCreate)))
	mux.Handle("GET /api/v1/dealer/crm/communications", rl.Authenticated(middleware.Auth(deps.CRMCommList)))
	mux.Handle("POST /api/v1/dealer/crm/recon", rl.Authenticated(middleware.Auth(deps.CRMReconCreate)))
	mux.Handle("PUT /api/v1/dealer/crm/recon/{job_ulid}", rl.Authenticated(middleware.Auth(deps.CRMReconUpdate)))
	mux.Handle("GET /api/v1/dealer/crm/financial/pnl", rl.Authenticated(middleware.Auth(deps.CRMFinancialPnL)))
	mux.Handle("GET /api/v1/dealer/crm/goals/{period}", rl.Authenticated(middleware.Auth(deps.CRMGoalGet)))
	mux.Handle("PUT /api/v1/dealer/crm/goals/{period}", rl.Authenticated(middleware.Auth(deps.CRMGoalSet)))

	// Notifications (JWT — 600 req/min)
	mux.Handle("GET /api/v1/dealer/notifications", rl.Authenticated(middleware.Auth(deps.NotificationList)))
	mux.Handle("GET /api/v1/dealer/notifications/unread-count", rl.Authenticated(middleware.Auth(deps.NotificationUnreadCount)))
	mux.Handle("POST /api/v1/dealer/notifications/read-all", rl.Authenticated(middleware.Auth(deps.NotificationMarkAllRead)))
	mux.Handle("PATCH /api/v1/dealer/notifications/{ulid}/read", rl.Authenticated(middleware.Auth(deps.NotificationMarkRead)))
	mux.Handle("DELETE /api/v1/dealer/notifications/{ulid}", rl.Authenticated(middleware.Auth(deps.NotificationDelete)))

	// ── Intelligence & Analytics avanzado ─────────────────────────────────────────
	mux.Handle("GET /api/v1/analytics/mds", rl.Public(http.HandlerFunc(deps.MarketDaysSupply)))
	mux.Handle("GET /api/v1/analytics/turn-time", rl.Public(http.HandlerFunc(deps.TurnTimePrediction)))
	mux.Handle("GET /api/v1/ext/market-check", rl.Strict(http.HandlerFunc(deps.MarketCheck)))

	// ── VIN Valuation Engine (Gap 2) ──────────────────────────────────────────────
	// Real-time market valuation using Cardex scrape data (vs DATgroup static DB)
	mux.Handle("GET /api/v1/analytics/vin-valuation", rl.Authenticated(middleware.Auth(deps.VINValuation)))

	// ── Residual Value Forecasting (Gap 3) ────────────────────────────────────────
	// MDS-adjusted depreciation curves (Indicata competitor)
	mux.Handle("GET /api/v1/analytics/residual", rl.Authenticated(middleware.Auth(deps.ResidualValue)))

	// ── Multipublicación Real (Gap 4) ─────────────────────────────────────────────
	mux.Handle("GET /api/v1/dealer/publishing", rl.Authenticated(middleware.Auth(deps.PublishingList)))
	mux.Handle("POST /api/v1/dealer/publishing", rl.Authenticated(middleware.Auth(deps.PublishingCreate)))
	mux.Handle("PATCH /api/v1/dealer/publishing/{pub_ulid}", rl.Authenticated(middleware.Auth(deps.PublishingUpdate)))
	mux.Handle("DELETE /api/v1/dealer/publishing/{pub_ulid}", rl.Authenticated(middleware.Auth(deps.PublishingDelete)))
	mux.Handle("GET /api/v1/dealer/publishing/feed/autoscout24.xml", rl.Authenticated(middleware.Auth(deps.PublishingFeedAS24)))
	mux.Handle("GET /api/v1/dealer/publishing/export", rl.Authenticated(middleware.Auth(deps.PublishingExport)))

	// ── Optimal Pricing ───────────────────────────────────────────────────────────
	mux.Handle("GET /api/v1/dealer/pricing/{ulid}/optimal", rl.Authenticated(middleware.Auth(deps.OptimalPrice)))

	// ── AI Assist ─────────────────────────────────────────────────────────────────
	mux.Handle("POST /api/v1/dealer/inventory/generate-description", rl.Authenticated(middleware.Auth(deps.GenerateDescription)))

	// ── Admin Panel ───────────────────────────────────────────────────────────────
	mux.Handle("GET /api/v1/admin/stats", rl.Authenticated(middleware.Auth(middleware.RequireAdmin(deps.AdminStats))))
	mux.Handle("GET /api/v1/admin/entities", rl.Authenticated(middleware.Auth(middleware.RequireAdmin(deps.AdminEntityList))))
	mux.Handle("PATCH /api/v1/admin/entities/{ulid}", rl.Authenticated(middleware.Auth(middleware.RequireAdmin(deps.AdminEntityUpdate))))
	mux.Handle("GET /api/v1/admin/users", rl.Authenticated(middleware.Auth(middleware.RequireAdmin(deps.AdminUserList))))
	mux.Handle("GET /api/v1/admin/scrapers", rl.Authenticated(middleware.Auth(middleware.RequireAdmin(deps.AdminScraperStatus))))

	// ── Census Intelligence (public — coverage matrix, gaps, population) ─────
	mux.Handle("GET /api/v1/census/coverage-matrix", rl.Public(http.HandlerFunc(deps.CoverageMatrix)))
	mux.Handle("GET /api/v1/census/gaps", rl.Public(http.HandlerFunc(deps.CoverageGaps)))
	mux.Handle("GET /api/v1/census/population-estimate", rl.Public(http.HandlerFunc(deps.PopulationEstimate)))
	mux.Handle("GET /api/v1/census/coverage-heatmap", rl.Public(http.HandlerFunc(deps.CoverageHeatmap)))

	// ---- Server -------------------------------------------------------------
	port := envOrDefault("PORT", "8080")
	srv := &http.Server{
		Addr:         ":" + port,
		Handler:      middleware.CORS(middleware.Recover(middleware.RequestID(middleware.Logger(mux)))),
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	go func() {
		slog.Info("api: listening", "port", port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("api: server error", "error", err)
			os.Exit(1)
		}
	}()

	<-ctx.Done()
	slog.Info("api: shutting down")
	shutCtx, shutCancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer shutCancel()
	if err := srv.Shutdown(shutCtx); err != nil {
		slog.Error("api: shutdown error", "error", err)
	}
	slog.Info("api: stopped")
}

func mustPG(ctx context.Context) *pgxpool.Pool {
	url := envOrDefault("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex?sslmode=disable")
	pool, err := pgxpool.New(ctx, url)
	if err != nil {
		slog.Error("api: pgxpool connect", "error", err)
		os.Exit(1)
	}
	if err := pool.Ping(ctx); err != nil {
		slog.Error("api: postgres ping", "error", err)
		os.Exit(1)
	}
	slog.Info("api: postgres connected")
	return pool
}

func mustRedis(ctx context.Context) *redis.Client {
	rdb := redis.NewClient(&redis.Options{
		Addr:     envOrDefault("REDIS_ADDR", "127.0.0.1:6379"),
		Password: envOrDefault("REDIS_PASS", ""),
		PoolSize: 30,
	})
	if err := rdb.Ping(ctx).Err(); err != nil {
		slog.Error("api: redis connect", "error", err)
		os.Exit(1)
	}
	slog.Info("api: redis connected")
	return rdb
}

func mustClickHouse() clickhouse.Conn {
	conn, err := clickhouse.Open(&clickhouse.Options{
		Addr: []string{envOrDefault("CLICKHOUSE_ADDR", "127.0.0.1:9000")},
		Auth: clickhouse.Auth{
			Database: envOrDefault("CLICKHOUSE_DB", "cardex"),
			Username: envOrDefault("CLICKHOUSE_USER", "cardex"),
			Password: envOrDefault("CLICKHOUSE_PASSWORD", "cardex_dev_only"),
		},
	})
	if err != nil {
		slog.Warn("api: clickhouse unavailable — analytics endpoints will return 503", "error", err)
		return nil
	}
	if err := conn.Ping(context.Background()); err != nil {
		slog.Warn("api: clickhouse ping failed — analytics endpoints will return 503", "error", err)
		return nil
	}
	slog.Info("api: clickhouse connected")
	return conn
}

func mustMeili() meilisearch.ServiceManager {
	url := envOrDefault("MEILI_URL", "http://localhost:7700")
	key := envOrDefault("MEILI_MASTER_KEY", "")
	client := meilisearch.New(url, meilisearch.WithAPIKey(key))
	if _, err := client.Health(); err != nil {
		slog.Warn("api: meilisearch unavailable — search endpoints will return 503", "error", err)
		return nil
	}
	slog.Info("api: meilisearch connected")
	return client
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
