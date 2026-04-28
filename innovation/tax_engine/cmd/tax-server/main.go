package main

import (
	"log/slog"
	"net/http"
	"os"

	tax "cardex.eu/tax"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	port := env("TAX_PORT", "8504")
	addr := ":" + port

	vies := tax.NewVIESClient()
	srv := tax.NewServer(vies, logger)

	logger.Info("tax-engine starting", "addr", addr)
	if err := http.ListenAndServe(addr, srv.Handler()); err != nil {
		logger.Error("server failed", "err", err)
		os.Exit(1)
	}
}

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
