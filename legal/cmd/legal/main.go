// Package main implements the CARDEX Legal Hub (Phase 7).
// See .cursor/prompts/phase-07-legal.md for full specification.
package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/redis/go-redis/v9"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	rdb := redis.NewClient(&redis.Options{Addr: envOrDefault("REDIS_ADDR", "127.0.0.1:6379"), PoolSize: 50})
	if err := rdb.Ping(ctx).Err(); err != nil {
		slog.Error("redis connection failed", "error", err)
		os.Exit(1)
	}
	defer rdb.Close()
	slog.Info("phase7: legal hub starting")
	// TODO: Consumer loop on stream:legal_audit_pending (cg_gov)
	<-ctx.Done()
	slog.Info("phase7: legal hub stopped")
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
