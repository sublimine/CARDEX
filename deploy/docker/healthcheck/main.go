// Command healthcheck is a minimal, dependency-free liveness probe for the
// CARDEX Go services that ship on gcr.io/distroless/static (no shell, no
// wget/curl). Docker's HEALTHCHECK runs it directly via exec form.
//
// Target resolution order:
//  1. first CLI argument        (e.g. /healthcheck http://127.0.0.1:9101/healthz)
//  2. HEALTHCHECK_URL env var
//  3. compile-time default of http://127.0.0.1:9101/healthz
//
// Exit 0 when the endpoint returns 2xx within the timeout, exit 1 otherwise.
package main

import (
	"context"
	"net/http"
	"os"
	"time"
)

const (
	defaultURL = "http://127.0.0.1:9101/healthz"
	timeout    = 3 * time.Second
)

func main() {
	url := defaultURL
	if env := os.Getenv("HEALTHCHECK_URL"); env != "" {
		url = env
	}
	if len(os.Args) > 1 && os.Args[1] != "" {
		url = os.Args[1]
	}

	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		os.Exit(1)
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		os.Exit(1)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		os.Exit(1)
	}
	os.Exit(0)
}
