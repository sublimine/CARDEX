// Package main is the CARDEX Workspace Service entry point.
//
// Exposes two HTTP sub-trees on a single port:
//
//	/api/v1/documents/*  — PDF document generation (contracts, invoices, sheets, CMR)
//	/api/v1/inbox/*      — Unified dealer inbox (conversations, messages, templates)
//	/api/v1/ingest/*     — Inquiry ingestion (web webhook, manual)
//	/health              — Health check
//
// Environment variables:
//
//	WORKSPACE_PORT      (default: 8506)
//	WORKSPACE_DB_PATH   (default: data/workspace.db)
//	WORKSPACE_MEDIA_DIR (default: data/workspace/media)
//	SMTP_HOST           (default: "")
//	SMTP_PORT           (default: 25)
//	SMTP_USER           (default: "")
//	SMTP_PASS           (default: "")
//	SMTP_FROM           (default: "")
package main

import (
	"context"
	"database/sql"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"time"

	"cardex.eu/workspace/internal/documents"
	"cardex.eu/workspace/internal/inbox"
	_ "modernc.org/sqlite"
)

func main() {
	log := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))

	port := envOrDefault("WORKSPACE_PORT", "8506")
	dbPath := envOrDefault("WORKSPACE_DB_PATH", "data/workspace.db")
	mediaDir := envOrDefault("WORKSPACE_MEDIA_DIR", "data/workspace/media")

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

	ctx := context.Background()

	// Documents service
	docSvc, err := documents.NewService(ctx, db, mediaDir)
	if err != nil {
		log.Error("documents service init", "err", err)
		os.Exit(1)
	}

	// Inbox service (schema includes CRM base tables + inbox tables)
	if err := inbox.EnsureSchema(db); err != nil {
		log.Error("inbox schema", "err", err)
		os.Exit(1)
	}
	if err := inbox.SeedSystemTemplates(db); err != nil {
		log.Error("seed templates", "err", err)
		os.Exit(1)
	}
	inboxSrv := inbox.NewServer(db, smtpCfg, log)

	// Root mux
	mux := http.NewServeMux()

	// Mount documents handler
	docHandler := documents.Handler(docSvc)
	mux.Handle("/api/v1/documents/", docHandler)

	// Mount inbox handler (inbox owns all /api/v1/inbox and /api/v1/ingest and /api/v1/templates routes)
	inboxMux := inboxSrv.Handler()
	mux.Handle("/api/v1/inbox/", inboxMux)
	mux.Handle("/api/v1/inbox", inboxMux)
	mux.Handle("/api/v1/templates/", inboxMux)
	mux.Handle("/api/v1/templates", inboxMux)
	mux.Handle("/api/v1/ingest/", inboxMux)

	// Health
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"status":"ok","time":"%s"}`, time.Now().UTC().Format(time.RFC3339))
	})

	addr := ":" + port
	log.Info("workspace-service starting", "addr", addr, "db", dbPath)
	srv := &http.Server{
		Addr:         addr,
		Handler:      mux,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 60 * time.Second,
		IdleTimeout:  120 * time.Second,
	}
	if err := srv.ListenAndServe(); err != nil {
		log.Error("server error", "err", err)
		os.Exit(1)
	}
}

func envOrDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
