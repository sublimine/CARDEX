package main

import (
	"database/sql"
	"log/slog"
	"os"

	_ "github.com/lib/pq"
)

const ddl = `
-- Activación de identificadores criptográficos
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- TABLA 1: CLIENTES B2B (Concesionarios)
CREATE TABLE IF NOT EXISTS dealers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    token_balance INT DEFAULT 0,
    trust_score NUMERIC(5,2) DEFAULT 100.00,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- TABLA 2: ACTIVOS PURIFICADOS (El Dark Pool Persistente)
CREATE TABLE IF NOT EXISTS assets (
    internal_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    shadow_id VARCHAR(255) UNIQUE NOT NULL,
    nlc_price NUMERIC(10,2) NOT NULL,
    deep_payload JSONB NOT NULL,
    phash_visual VARCHAR(64),
    status VARCHAR(50) DEFAULT 'AVAILABLE',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- TABLA 3: LIBRO MAYOR DE TRANSACCIONES (Auditoría Financiera)
CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    dealer_id UUID REFERENCES dealers(id),
    asset_internal_id UUID REFERENCES assets(internal_id),
    credits_deducted INT NOT NULL,
    action_type VARCHAR(50) NOT NULL,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Índices de alto rendimiento para consultas HFT
CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status);
CREATE INDEX IF NOT EXISTS idx_assets_phash ON assets(phash_visual);
`

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo})))

	connStr := os.Getenv("DATABASE_URL")
	if connStr == "" {
		connStr = "postgres://cardex_admin:alpha_secure_99@127.0.0.1:5432/cardex_core?sslmode=disable"
	}

	db, err := sql.Open("postgres", connStr)
	if err != nil {
		slog.Error("phase:migrate connection failed", "error", err)
		os.Exit(1)
	}
	defer db.Close()

	if err := db.Ping(); err != nil {
		slog.Error("phase:migrate ping failed", "error", err)
		os.Exit(1)
	}

	_, err = db.Exec(ddl)
	if err != nil {
		slog.Error("phase:migrate ddl failed", "error", err)
		os.Exit(1)
	}

	slog.Info("phase:migrate schema injected", "tables", "dealers, assets, transactions")
}
