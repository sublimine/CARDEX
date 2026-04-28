// routes-server — CARDEX Fleet Disposition Intelligence API.
//
// Endpoints:
//
//	GET  /health              → {"status":"ok"}
//	GET  /routes/spread       → MarketSpread per country
//	POST /routes/optimize     → DispositionPlan for one vehicle
//	POST /routes/batch        → BatchPlan for a fleet
//
// Environment variables:
//
//	ROUTES_DB_PATH       path to SQLite KG (default: data/discovery.db)
//	ROUTES_PORT          HTTP port (default: 8504)
//	ROUTES_TRANSPORT_CFG path to YAML transport cost overrides (optional)
package main

import (
	"database/sql"
	"fmt"
	"log/slog"
	"os"

	"cardex.eu/routes"
	_ "modernc.org/sqlite"
)

func main() {
	log := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelInfo}))

	dbPath := env("ROUTES_DB_PATH", "data/discovery.db")
	port := env("ROUTES_PORT", "8504")
	transportCfg := env("ROUTES_TRANSPORT_CFG", "")

	db, err := sql.Open("sqlite", dbPath+"?_journal_mode=WAL&_busy_timeout=5000")
	if err != nil {
		log.Error("cannot open database", "path", dbPath, "err", err)
		os.Exit(1)
	}
	db.SetMaxOpenConns(1)
	defer db.Close()

	if err := db.Ping(); err != nil {
		log.Error("database unreachable", "path", dbPath, "err", err)
		os.Exit(1)
	}

	// Override transport costs from YAML if provided.
	transport, err := routes.LoadTransportMatrix(transportCfg)
	if err != nil {
		log.Error("failed to load transport costs", "file", transportCfg, "err", err)
		os.Exit(1)
	}
	_ = transport // Server builds its own default; expose the loader for future use.

	srv := routes.NewServer(db, log)
	addr := fmt.Sprintf(":%s", port)
	log.Info("CARDEX Routes API starting", "addr", addr, "db", dbPath)

	if err := srv.ListenAndServe(addr); err != nil {
		log.Error("server exited", "err", err)
		os.Exit(1)
	}
}

func env(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}
