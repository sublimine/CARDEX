// Package main is the CARDEX Workspace Service entry point.
//
// Exposes HTTP sub-trees on a single port:
//
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
	"cardex.eu/workspace/internal/finance"
	"cardex.eu/workspace/internal/inbox"
	"cardex.eu/workspace/internal/kanban"
	"cardex.eu/workspace/internal/media"
	"cardex.eu/workspace/internal/syndication"
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

	// ── Syndication schema (engine/scheduler wired externally by ops jobs) ───
	if err := syndication.EnsureSchema(db); err != nil {
		log.Error("syndication schema", "err", err)
		os.Exit(1)
	}

	// ── Root mux ─────────────────────────────────────────────────────────────
	mux := http.NewServeMux()

	// Documents
	mux.Handle("/api/v1/documents/", documents.Handler(docSvc))

	// Inbox (owns /api/v1/inbox, /api/v1/templates, /api/v1/ingest)
	inboxMux := inboxSrv.Handler()
	mux.Handle("/api/v1/inbox/", inboxMux)
	mux.Handle("/api/v1/inbox", inboxMux)
	mux.Handle("/api/v1/templates/", inboxMux)
	mux.Handle("/api/v1/templates", inboxMux)
	mux.Handle("/api/v1/ingest/", inboxMux)

	// Finance (vehicles P&L, fleet, transactions)
	mux.Handle("/api/v1/vehicles/", finHandler)
	mux.Handle("/api/v1/fleet/", finHandler)
	mux.Handle("/api/v1/transactions/", finHandler)

	// Media reorder — mounted AFTER finance so the more-specific pattern wins
	// for PUT /api/v1/vehicles/{id}/media/reorder vs GET /api/v1/vehicles/{id}/pnl
	mux.Handle("PUT /api/v1/vehicles/{id}/media/reorder", media.ReorderHandler(mediaSto))

	// Kanban + Calendar
	kanbanSrv.Register(mux)

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
