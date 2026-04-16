// Package a_registries implements enrichment of discovered dealer entities
// using the GNN dealer inference service.
//
// GNN service: innovation/gnn_dealer_inference/serve.py — Flask on port 8501.
// Called after a dealer entity is resolved by the discovery pipeline.
//
// Enrichment stores predicted dealer-to-dealer supply links in the
// dealer_predicted_links table.  The quality and discovery services
// can query this table to weight dealer trust scores and detect
// intermediary/broker patterns.
//
// Table schema (auto-migrated):
//
//	dealer_predicted_links(
//	    id           INTEGER PK,
//	    dealer_a     TEXT,   -- source dealer (predicted supplier)
//	    dealer_b     TEXT,   -- destination dealer (predicted buyer)
//	    probability  REAL,   -- link probability from GNN [0,1]
//	    model_version TEXT,  -- checkpoint hash or semver
//	    predicted_at TIMESTAMP
//	)
//
// Env vars:
//
//	GNN_SERVICE_URL    base URL of the GNN inference service  (default: http://localhost:8501)
//	GNN_TOP_K          top-K links to store per dealer        (default: 5)
//	GNN_TIMEOUT_MS     HTTP timeout in milliseconds           (default: 5000)
//	GNN_SKIP           "true" to disable enrichment           (default: false)
package a_registries

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// ── Prometheus metrics ────────────────────────────────────────────────────────

var (
	metricPredictionsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Namespace: "cardex",
			Subsystem: "gnn",
			Name:      "predictions_total",
			Help:      "Total GNN link-prediction calls, by result (success|error|skip).",
		},
		[]string{"result"},
	)

	metricLatency = promauto.NewHistogram(
		prometheus.HistogramOpts{
			Namespace: "cardex",
			Subsystem: "gnn",
			Name:      "latency_seconds",
			Help:      "GNN /predict-links request latency in seconds.",
			Buckets:   []float64{0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0},
		},
	)

	metricLinksStored = promauto.NewCounter(
		prometheus.CounterOpts{
			Namespace: "cardex",
			Subsystem: "gnn",
			Name:      "links_stored_total",
			Help:      "Total dealer predicted links persisted to dealer_predicted_links.",
		},
	)
)

// ── Types ─────────────────────────────────────────────────────────────────────

// PredictedLink represents a single GNN-inferred supply relationship.
type PredictedLink struct {
	DealerA      string
	DealerB      string
	Probability  float64
	ModelVersion string
	PredictedAt  time.Time
}

// GNNClient calls the GNN inference service.
type GNNClient struct {
	baseURL string
	topK    int
	client  *http.Client
}

// NewGNNClient creates a GNNClient from environment variables.
func NewGNNClient() *GNNClient {
	baseURL := getEnv("GNN_SERVICE_URL", "http://localhost:8501")
	topK := 5
	if s := os.Getenv("GNN_TOP_K"); s != "" {
		if n, err := strconv.Atoi(s); err == nil && n > 0 {
			topK = n
		}
	}
	timeoutMs := 5000
	if s := os.Getenv("GNN_TIMEOUT_MS"); s != "" {
		if n, err := strconv.Atoi(s); err == nil && n > 0 {
			timeoutMs = n
		}
	}
	return &GNNClient{
		baseURL: baseURL,
		topK:    topK,
		client:  &http.Client{Timeout: time.Duration(timeoutMs) * time.Millisecond},
	}
}

// PredictLinks calls POST /predict-links and returns the top-K predicted links.
// Returns nil, nil when GNN_SKIP=true or the service is unreachable.
func (g *GNNClient) PredictLinks(ctx context.Context, dealerID string) ([]PredictedLink, error) {
	if os.Getenv("GNN_SKIP") == "true" {
		metricPredictionsTotal.WithLabelValues("skip").Inc()
		return nil, nil
	}

	body, _ := json.Marshal(map[string]any{
		"dealer_id": dealerID,
		"top_k":     g.topK,
	})

	start := time.Now()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		g.baseURL+"/predict-links", bytes.NewReader(body))
	if err != nil {
		metricPredictionsTotal.WithLabelValues("error").Inc()
		return nil, fmt.Errorf("gnn: build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := g.client.Do(req)
	elapsed := time.Since(start)
	metricLatency.Observe(elapsed.Seconds())

	if err != nil {
		metricPredictionsTotal.WithLabelValues("error").Inc()
		return nil, fmt.Errorf("gnn: POST /predict-links: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		metricPredictionsTotal.WithLabelValues("error").Inc()
		return nil, fmt.Errorf("gnn: service returned %d", resp.StatusCode)
	}

	raw, err := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
	if err != nil {
		metricPredictionsTotal.WithLabelValues("error").Inc()
		return nil, fmt.Errorf("gnn: read response: %w", err)
	}

	var result struct {
		DealerID       string `json:"dealer_id"`
		PredictedLinks []struct {
			DstDealerID string  `json:"dst_dealer_id"`
			Probability float64 `json:"probability"`
		} `json:"predicted_links"`
		Warning string `json:"warning"`
	}
	if err := json.Unmarshal(raw, &result); err != nil {
		metricPredictionsTotal.WithLabelValues("error").Inc()
		return nil, fmt.Errorf("gnn: parse response: %w", err)
	}

	metricPredictionsTotal.WithLabelValues("success").Inc()

	links := make([]PredictedLink, 0, len(result.PredictedLinks))
	now := time.Now().UTC()
	for _, l := range result.PredictedLinks {
		if l.DstDealerID == "" || l.DstDealerID == dealerID {
			continue
		}
		links = append(links, PredictedLink{
			DealerA:      dealerID,
			DealerB:      l.DstDealerID,
			Probability:  l.Probability,
			ModelVersion: "latest",
			PredictedAt:  now,
		})
	}
	return links, nil
}

// ── Storage ───────────────────────────────────────────────────────────────────

const linksSchema = `
CREATE TABLE IF NOT EXISTS dealer_predicted_links (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dealer_a      TEXT    NOT NULL,
    dealer_b      TEXT    NOT NULL,
    probability   REAL    NOT NULL,
    model_version TEXT    NOT NULL,
    predicted_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(dealer_a, dealer_b)
);
CREATE INDEX IF NOT EXISTS idx_dpl_dealer_a ON dealer_predicted_links(dealer_a);
CREATE INDEX IF NOT EXISTS idx_dpl_dealer_b ON dealer_predicted_links(dealer_b);
CREATE INDEX IF NOT EXISTS idx_dpl_probability ON dealer_predicted_links(probability DESC);
`

// EnsureLinksSchema creates the dealer_predicted_links table if absent.
func EnsureLinksSchema(db *sql.DB) error {
	_, err := db.Exec(linksSchema)
	return err
}

// PersistLinks upserts predicted links into the database.
func PersistLinks(ctx context.Context, db *sql.DB, links []PredictedLink) error {
	if len(links) == 0 {
		return nil
	}
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("gnn: begin tx: %w", err)
	}
	defer tx.Rollback() //nolint:errcheck

	stmt, err := tx.PrepareContext(ctx, `
		INSERT INTO dealer_predicted_links
		    (dealer_a, dealer_b, probability, model_version, predicted_at)
		VALUES (?, ?, ?, ?, ?)
		ON CONFLICT(dealer_a, dealer_b) DO UPDATE SET
		    probability   = excluded.probability,
		    model_version = excluded.model_version,
		    predicted_at  = excluded.predicted_at
	`)
	if err != nil {
		return fmt.Errorf("gnn: prepare: %w", err)
	}
	defer stmt.Close()

	for _, l := range links {
		if _, err := stmt.ExecContext(ctx,
			l.DealerA, l.DealerB, l.Probability,
			l.ModelVersion, l.PredictedAt.Format(time.RFC3339),
		); err != nil {
			return fmt.Errorf("gnn: insert link %s→%s: %w", l.DealerA, l.DealerB, err)
		}
		metricLinksStored.Inc()
	}
	return tx.Commit()
}

// ── Enrichment entry point ────────────────────────────────────────────────────

// EnrichDealer calls the GNN service for *dealerID* and stores the results.
// Designed to be called asynchronously after a dealer is resolved by the discovery pipeline.
// Returns nil on skip (GNN_SKIP=true) or unreachable service — non-fatal.
func EnrichDealer(ctx context.Context, db *sql.DB, client *GNNClient, dealerID string) error {
	links, err := client.PredictLinks(ctx, dealerID)
	if err != nil {
		return fmt.Errorf("gnn enrichment %s: %w", dealerID, err)
	}
	if len(links) == 0 {
		return nil
	}
	return PersistLinks(ctx, db, links)
}

// ── Helpers ───────────────────────────────────────────────────────────────────

func getEnv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
