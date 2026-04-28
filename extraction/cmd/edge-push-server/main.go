// edge-push-server — standalone gRPC server for the E12 Edge Push endpoint.
//
// This binary is deployed separately from the main extraction-service and
// listens for inbound ListingBatch streams from Tauri desktop clients.
//
// Environment variables:
//
//	EDGE_DB_PATH        path to SQLite KG (default: ./data/discovery.db)
//	EDGE_GRPC_PORT      gRPC listen port (default: 50051)
//	EDGE_TLS_CERT       path to TLS certificate (required in production)
//	EDGE_TLS_KEY        path to TLS private key  (required in production)
//	EDGE_METRICS_ADDR   Prometheus /metrics addr  (default: :9102)
//	EDGE_INSECURE       "true" disables TLS (development only)
package main

import (
	"context"
	"crypto/tls"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"

	"github.com/prometheus/client_golang/prometheus/promhttp"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"

	_ "modernc.org/sqlite"

	"cardex.eu/extraction/internal/extractor/e12_edge/server"
	"cardex.eu/extraction/internal/storage"
)

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(log)

	cfg := loadConfig()

	// ── Storage (shared SQLite KG) ────────────────────────────────────────────
	store, err := storage.New(cfg.dbPath)
	if err != nil {
		log.Error("storage init failed", "err", err)
		os.Exit(1)
	}
	defer store.Close()

	// ── Edge DB (edge_dealers + edge_inventory_staging tables) ────────────────
	db, err := server.NewDB(cfg.dbPath)
	if err != nil {
		log.Error("edge DB init failed", "err", err)
		os.Exit(1)
	}
	defer db.Close()

	// ── gRPC server options ───────────────────────────────────────────────────
	var opts []grpc.ServerOption
	if cfg.insecure {
		log.Warn("TLS disabled — EDGE_INSECURE=true (development only)")
		opts = append(opts, grpc.Creds(insecure.NewCredentials()))
	} else {
		tlsCfg, err := loadTLS(cfg.certFile, cfg.keyFile)
		if err != nil {
			log.Error("TLS load failed", "cert", cfg.certFile, "key", cfg.keyFile, "err", err)
			os.Exit(1)
		}
		opts = append(opts, grpc.Creds(credentials.NewTLS(tlsCfg)))
		log.Info("TLS enabled", "cert", cfg.certFile)
	}

	// ── Prometheus metrics ────────────────────────────────────────────────────
	go func() {
		mux := http.NewServeMux()
		mux.Handle("/metrics", promhttp.Handler())
		mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusOK)
		})
		log.Info("metrics server starting", "addr", cfg.metricsAddr)
		if err := http.ListenAndServe(cfg.metricsAddr, mux); err != nil {
			log.Error("metrics server error", "err", err)
		}
	}()

	// ── Start gRPC server ─────────────────────────────────────────────────────
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	addr := fmt.Sprintf(":%d", cfg.grpcPort)
	srv := server.New(db, store)

	log.Info("edge-push-server starting", "addr", addr)
	if err := server.ListenAndServe(ctx, addr, srv, opts...); err != nil {
		log.Error("edge-push-server stopped", "err", err)
		os.Exit(1)
	}
	log.Info("edge-push-server stopped")
}

// ─── Config ───────────────────────────────────────────────────────────────────

type config struct {
	dbPath      string
	grpcPort    int
	certFile    string
	keyFile     string
	metricsAddr string
	insecure    bool
}

func loadConfig() config {
	c := config{
		dbPath:      envStr("EDGE_DB_PATH", "./data/discovery.db"),
		grpcPort:    envInt("EDGE_GRPC_PORT", 50051),
		certFile:    envStr("EDGE_TLS_CERT", ""),
		keyFile:     envStr("EDGE_TLS_KEY", ""),
		metricsAddr: envStr("EDGE_METRICS_ADDR", ":9102"),
		insecure:    os.Getenv("EDGE_INSECURE") == "true",
	}
	return c
}

func envStr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func envInt(key string, def int) int {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	var n int
	if _, err := fmt.Sscan(v, &n); err != nil || n <= 0 {
		return def
	}
	return n
}

func loadTLS(certFile, keyFile string) (*tls.Config, error) {
	if certFile == "" || keyFile == "" {
		return nil, fmt.Errorf("EDGE_TLS_CERT and EDGE_TLS_KEY must be set (or set EDGE_INSECURE=true)")
	}
	cert, err := tls.LoadX509KeyPair(certFile, keyFile)
	if err != nil {
		return nil, err
	}
	return &tls.Config{
		Certificates: []tls.Certificate{cert},
		MinVersion:   tls.VersionTLS13,
	}, nil
}
