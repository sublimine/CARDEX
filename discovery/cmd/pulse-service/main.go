// pulse-service — Sprint 35 CARDEX PULSE
//
// Standalone HTTP service that scores dealer health from live inventory signals.
//
// Environment variables:
//
//	PULSE_DB_PATH        SQLite KG database path        (default: ./data/discovery.db)
//	PULSE_ADDR           HTTP bind address               (default: :8504)
//	PULSE_WEIGHTS_PATH   JSON weight-override file path  (default: none)
//	PULSE_RETAIN_DAYS    History retention in days       (default: 90)
package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/prometheus/client_golang/prometheus/promhttp"
	_ "modernc.org/sqlite"

	"cardex.eu/discovery/internal/db"
	"cardex.eu/discovery/internal/pulse"
)

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))

	dbPath := envOrDefault("PULSE_DB_PATH", "./data/discovery.db")
	addr := envOrDefault("PULSE_ADDR", ":8504")
	weightsPath := os.Getenv("PULSE_WEIGHTS_PATH")
	retainDays := envInt("PULSE_RETAIN_DAYS", 90)

	database, err := db.Open(dbPath)
	if err != nil {
		log.Error("db.Open failed", "path", dbPath, "err", err)
		os.Exit(1)
	}
	defer database.Close()
	log.Info("database opened", "path", dbPath)

	ctx := context.Background()
	if err := pulse.EnsureTable(ctx, database); err != nil {
		log.Error("EnsureTable failed", "err", err)
		os.Exit(1)
	}

	weights, err := pulse.LoadWeights(weightsPath)
	if err != nil {
		log.Error("LoadWeights failed", "err", err)
		os.Exit(1)
	}

	if n, err := pulse.PruneOld(ctx, database, retainDays); err != nil {
		log.Warn("prune old history failed", "err", err)
	} else if n > 0 {
		log.Info("pruned old history", "rows", n, "retain_days", retainDays)
	}

	mux := http.NewServeMux()
	mux.Handle("/metrics", promhttp.Handler())
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	mux.Handle("/pulse/", pulse.Handler(database, weights))

	srv := &http.Server{
		Addr:         addr,
		Handler:      mux,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	sigCtx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	go func() {
		log.Info("pulse-service listening", "addr", addr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Error("server error", "err", err)
		}
	}()

	<-sigCtx.Done()
	log.Info("shutting down")

	shutCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = srv.Shutdown(shutCtx)
}

func envOrDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func envInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}
