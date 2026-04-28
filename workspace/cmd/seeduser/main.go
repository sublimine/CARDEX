// Command seeduser creates a demo admin user in the workspace SQLite database.
//
// Usage:
//
//	WORKSPACE_DB_PATH=data/workspace.db go run ./cmd/seeduser/
//
// Defaults match workspace-service defaults; override via env vars.
package main

import (
	"database/sql"
	"fmt"
	"log"
	"os"
	"time"

	"golang.org/x/crypto/bcrypt"
	_ "modernc.org/sqlite"
)

func main() {
	dbPath := envOrDefault("WORKSPACE_DB_PATH", "data/workspace.db")

	email    := envOrDefault("SEED_EMAIL",    "admin@cardex.es")
	password := envOrDefault("SEED_PASSWORD", "Cardex2024!")
	name     := envOrDefault("SEED_NAME",     "Admin CARDEX")
	tenantID := envOrDefault("SEED_TENANT",   "t_demo")

	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		log.Fatalf("open db: %v", err)
	}
	defer db.Close()

	// Ensure schema exists (idempotent).
	if _, err := db.Exec(`
		CREATE TABLE IF NOT EXISTS crm_users (
			id            TEXT PRIMARY KEY,
			tenant_id     TEXT NOT NULL,
			email         TEXT NOT NULL,
			password_hash TEXT NOT NULL,
			name          TEXT NOT NULL DEFAULT '',
			role          TEXT NOT NULL DEFAULT 'dealer',
			created_at    TEXT NOT NULL,
			updated_at    TEXT NOT NULL,
			UNIQUE(tenant_id, email)
		)`); err != nil {
		log.Fatalf("ensure schema: %v", err)
	}

	// Check if user already exists.
	var existing string
	err = db.QueryRow(
		`SELECT id FROM crm_users WHERE email=? AND tenant_id=?`, email, tenantID,
	).Scan(&existing)
	if err == nil {
		fmt.Printf("✓ User already exists: %s (id=%s)\n", email, existing)
		return
	}
	if err != sql.ErrNoRows {
		log.Fatalf("query existing user: %v", err)
	}

	// Generate bcrypt hash (cost 10 — fast but secure enough for dev).
	hash, err := bcrypt.GenerateFromPassword([]byte(password), 10)
	if err != nil {
		log.Fatalf("bcrypt: %v", err)
	}

	// Generate a simple deterministic ID for the seed user.
	id := "seed_admin_" + tenantID

	now := time.Now().UTC().Format(time.RFC3339)
	_, err = db.Exec(
		`INSERT INTO crm_users(id,tenant_id,email,password_hash,name,role,created_at,updated_at)
		 VALUES(?,?,?,?,?,?,?,?)`,
		id, tenantID, email, string(hash), name, "admin", now, now,
	)
	if err != nil {
		log.Fatalf("insert user: %v", err)
	}

	fmt.Printf("✓ Demo user created\n")
	fmt.Printf("  Email:     %s\n", email)
	fmt.Printf("  Password:  %s\n", password)
	fmt.Printf("  Tenant ID: %s\n", tenantID)
	fmt.Printf("  User ID:   %s\n", id)
	fmt.Printf("\n  POST /api/v1/auth/login  {\"email\":\"%s\",\"password\":\"%s\"}\n", email, password)
}

func envOrDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
