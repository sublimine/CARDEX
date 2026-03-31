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

	deps := &handlers.Deps{
		DB:      pool,
		Redis:   rdb,
		CH:      ch,
		Meili:   meili.Index("vehicles"),
		NLCCalc: nlcCalc,
	}

	// ---- Router -------------------------------------------------------------
	mux := http.NewServeMux()

	// Health
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"status":"ok"}`))
	})

	// Marketplace (public)
	mux.HandleFunc("GET /api/v1/marketplace/search", deps.MarketplaceSearch)
	mux.HandleFunc("GET /api/v1/marketplace/listing/{ulid}", deps.ListingDetail)
	mux.HandleFunc("POST /api/v1/marketplace/alerts", middleware.Auth(deps.CreatePriceAlert))
	mux.HandleFunc("GET /api/v1/marketplace/alerts", middleware.Auth(deps.ListPriceAlerts))
	mux.HandleFunc("DELETE /api/v1/marketplace/alerts/{id}", middleware.Auth(deps.DeletePriceAlert))

	// Analytics (public)
	mux.HandleFunc("GET /api/v1/analytics/price-index", deps.PriceIndex)
	mux.HandleFunc("GET /api/v1/analytics/market-depth", deps.MarketDepth)
	mux.HandleFunc("GET /api/v1/analytics/demand", deps.DemandSignals)
	mux.HandleFunc("GET /api/v1/analytics/heatmap", deps.Heatmap)
	mux.HandleFunc("GET /api/v1/analytics/dom", deps.DOMDistribution)
	mux.HandleFunc("GET /api/v1/analytics/volatility", deps.PriceVolatility)

	// VIN History (public, free)
	mux.HandleFunc("GET /api/v1/vin/{vin}", deps.VINHistory)

	// Auth
	mux.HandleFunc("POST /api/v1/auth/register", deps.DealerRegister)
	mux.HandleFunc("POST /api/v1/auth/login", deps.DealerLogin)
	mux.HandleFunc("POST /api/v1/auth/refresh", deps.TokenRefresh)

	// Dealer SaaS (JWT required)
	mux.HandleFunc("GET /api/v1/dealer/inventory", middleware.Auth(deps.InventoryList))
	mux.HandleFunc("POST /api/v1/dealer/inventory", middleware.Auth(deps.InventoryCreate))
	mux.HandleFunc("PUT /api/v1/dealer/inventory/{ulid}", middleware.Auth(deps.InventoryUpdate))
	mux.HandleFunc("DELETE /api/v1/dealer/inventory/{ulid}", middleware.Auth(deps.InventoryDelete))
	mux.HandleFunc("POST /api/v1/dealer/inventory/import-url", middleware.Auth(deps.InventoryImportURL))

	mux.HandleFunc("POST /api/v1/dealer/publish", middleware.Auth(deps.PublishJob))
	mux.HandleFunc("GET /api/v1/dealer/publish/{job_id}", middleware.Auth(deps.PublishJobStatus))

	mux.HandleFunc("GET /api/v1/dealer/leads", middleware.Auth(deps.LeadsList))
	mux.HandleFunc("POST /api/v1/dealer/leads", middleware.Auth(deps.LeadCreate))
	mux.HandleFunc("PUT /api/v1/dealer/leads/{id}/status", middleware.Auth(deps.LeadStatusUpdate))

	mux.HandleFunc("GET /api/v1/dealer/pricing/{ulid}", middleware.Auth(deps.PricingIntelligence))
	mux.HandleFunc("GET /api/v1/dealer/audit", middleware.Auth(deps.MarketingAudit))
	mux.HandleFunc("POST /api/v1/dealer/audit/trigger", middleware.Auth(deps.TriggerMarketingAudit))

	mux.HandleFunc("GET /api/v1/dealer/nlc/{ulid}", middleware.Auth(deps.NLCCalculation))
	mux.HandleFunc("GET /api/v1/dealer/sdi/{ulid}", middleware.Auth(deps.SDIScore))

	// TradingCar (public)
	mux.HandleFunc("GET /api/v1/tradingcar/candles", deps.TradingCarCandles)
	mux.HandleFunc("GET /api/v1/tradingcar/tickers", deps.TradingCarTickers)
	mux.HandleFunc("GET /api/v1/tradingcar/scanner", deps.TradingCarScanner)
	mux.HandleFunc("GET /api/v1/tradingcar/compare", deps.TradingCarCompare)

	// Arbitrage (public read, JWT for booking)
	mux.HandleFunc("GET /api/v1/arbitrage/opportunities", deps.ArbitrageOpportunities)
	mux.HandleFunc("GET /api/v1/arbitrage/routes", deps.ArbitrageRouteStats)
	mux.HandleFunc("GET /api/v1/arbitrage/nlc/{ticker}/{origin}/{dest}", deps.ArbitrageNLCBreakdown)
	mux.HandleFunc("POST /api/v1/arbitrage/book/{opportunity_id}", middleware.Auth(deps.ArbitrageBookOpportunity))
	mux.HandleFunc("GET /api/v1/arbitrage/booked", middleware.Auth(deps.ArbitrageBookedList))

	// CRM (JWT required)
	mux.HandleFunc("GET /api/v1/dealer/crm/dashboard", middleware.Auth(deps.CRMDashboard))
	mux.HandleFunc("GET /api/v1/dealer/crm/vehicles", middleware.Auth(deps.CRMVehicleList))
	mux.HandleFunc("POST /api/v1/dealer/crm/vehicles", middleware.Auth(deps.CRMVehicleCreate))
	mux.HandleFunc("GET /api/v1/dealer/crm/vehicles/{ulid}", middleware.Auth(deps.CRMVehicleGet))
	mux.HandleFunc("PUT /api/v1/dealer/crm/vehicles/{ulid}", middleware.Auth(deps.CRMVehicleUpdate))
	mux.HandleFunc("DELETE /api/v1/dealer/crm/vehicles/{ulid}", middleware.Auth(deps.CRMVehicleDelete))
	mux.HandleFunc("GET /api/v1/dealer/crm/contacts", middleware.Auth(deps.CRMContactList))
	mux.HandleFunc("POST /api/v1/dealer/crm/contacts", middleware.Auth(deps.CRMContactCreate))
	mux.HandleFunc("GET /api/v1/dealer/crm/contacts/{ulid}", middleware.Auth(deps.CRMContactGet))
	mux.HandleFunc("PUT /api/v1/dealer/crm/contacts/{ulid}", middleware.Auth(deps.CRMContactUpdate))
	mux.HandleFunc("GET /api/v1/dealer/crm/deals", middleware.Auth(deps.CRMDealList))
	mux.HandleFunc("POST /api/v1/dealer/crm/deals", middleware.Auth(deps.CRMDealCreate))
	mux.HandleFunc("PUT /api/v1/dealer/crm/deals/{ulid}", middleware.Auth(deps.CRMDealUpdate))
	mux.HandleFunc("GET /api/v1/dealer/crm/pipeline/stages", middleware.Auth(deps.CRMPipelineStages))
	mux.HandleFunc("GET /api/v1/dealer/crm/pipeline/kanban", middleware.Auth(deps.CRMPipelineKanban))
	mux.HandleFunc("POST /api/v1/dealer/crm/communications", middleware.Auth(deps.CRMCommCreate))
	mux.HandleFunc("GET /api/v1/dealer/crm/communications", middleware.Auth(deps.CRMCommList))
	mux.HandleFunc("POST /api/v1/dealer/crm/recon", middleware.Auth(deps.CRMReconCreate))
	mux.HandleFunc("PUT /api/v1/dealer/crm/recon/{job_ulid}", middleware.Auth(deps.CRMReconUpdate))
	mux.HandleFunc("GET /api/v1/dealer/crm/financial/pnl", middleware.Auth(deps.CRMFinancialPnL))
	mux.HandleFunc("GET /api/v1/dealer/crm/goals/{period}", middleware.Auth(deps.CRMGoalGet))
	mux.HandleFunc("PUT /api/v1/dealer/crm/goals/{period}", middleware.Auth(deps.CRMGoalSet))

	// ---- Server -------------------------------------------------------------
	port := envOrDefault("PORT", "8080")
	srv := &http.Server{
		Addr:         ":" + port,
		Handler:      middleware.CORS(middleware.RequestID(middleware.Logger(mux))),
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
	srv.Shutdown(shutCtx)
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
		slog.Error("api: clickhouse connect", "error", err)
		os.Exit(1)
	}
	if err := conn.Ping(context.Background()); err != nil {
		slog.Error("api: clickhouse ping", "error", err)
		os.Exit(1)
	}
	slog.Info("api: clickhouse connected")
	return conn
}

func mustMeili() *meilisearch.Client {
	url := envOrDefault("MEILI_URL", "http://localhost:7700")
	key := envOrDefault("MEILI_MASTER_KEY", "")
	return meilisearch.New(url, meilisearch.WithAPIKey(key))
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
