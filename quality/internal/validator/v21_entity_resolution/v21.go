// Package v21_entity_resolution implements V21 — Multilingual Dealer Entity Resolution.
//
// # Strategy
//
// Multiple discovery sources (Familia A–O) may observe the same physical dealer
// under slightly different name/address representations:
//
//   - "BMW Autohaus GmbH München" (mobile.de)
//   - "Autohaus München BMW" (Handelsregister)
//   - "Autohaus München GmbH" (OSM)
//
// V21 resolves these to a canonical entity by embedding the dealer text
// (name + city + country) into a shared vector space and comparing with
// cosine similarity. Matches above a configurable threshold are merged under
// a canonical entity ID.
//
// # Embedding backend
//
// Two backends are provided (via TextEmbedder interface):
//
//  1. SubprocessEmbedder — calls Python with paraphrase-multilingual-mpnet-base-v2
//     (278M params, 768-dim). Preferred in production when Python+torch is available.
//
//  2. TFIDFEmbedder — pure-Go character 3-gram TF hashing (256-dim). Used in
//     tests and as a fallback when Python is unavailable. Accuracy is lower but
//     still effective for dealer name normalisation.
//
// # ONNX / BGE-M3 status
//
// BGE-M3 (568M, 1024-dim) is the roadmap target. The Go ONNX bindings
// (onnxruntime-go) require CGO and are not yet stable for CPU-only linux/amd64
// cross-compilation. Tracked as TODO(V21-ONNX): Phase 5+.
//
// # Integration
//
// V21 runs after V20 (composite scorer). It does not gate publication —
// Severity is INFO. Its output enriches the dealer_entity record with
// canonical_dealer_id so deduplication can be applied at query time.
//
// # Prometheus metrics
//
//   - cardex_quality_entity_resolution_matches_total — counter of entity merges
//   - cardex_quality_entity_resolution_latency_seconds — histogram
package v21_entity_resolution

import (
	"context"
	"database/sql"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	"cardex.eu/quality/internal/pipeline"
)

const (
	strategyID   = "V21"
	strategyName = "Multilingual Dealer Entity Resolution"
)

var (
	metricMatches = promauto.NewCounter(prometheus.CounterOpts{
		Name: "cardex_quality_entity_resolution_matches_total",
		Help: "Total number of dealer entity merges performed by V21.",
	})
	metricLatency = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "cardex_quality_entity_resolution_latency_seconds",
		Help:    "V21 embedding + search latency per vehicle record.",
		Buckets: prometheus.DefBuckets,
	})
)

// Config holds V21 configuration.
type Config struct {
	// Threshold is the minimum cosine similarity to consider two dealers the same
	// entity. Default: DefaultThresh (0.85).
	Threshold float32
	// Embedder is the backend used to produce embeddings. Default: TFIDFEmbedder.
	Embedder TextEmbedder
}

// EntityResolution is the V21 validator.
type EntityResolution struct {
	cfg   Config
	index *EmbeddingIndex
	log   *slog.Logger
}

// New constructs V21 with a no-op (nil DB) index. The validator is functional
// but will not persist embeddings. Use NewWithDB for production.
func New() *EntityResolution {
	return NewWithConfig(Config{})
}

// NewWithConfig constructs V21 with the given config.
func NewWithConfig(cfg Config) *EntityResolution {
	if cfg.Threshold == 0 {
		cfg.Threshold = DefaultThresh
	}
	if cfg.Embedder == nil {
		cfg.Embedder = &TFIDFEmbedder{}
	}
	return &EntityResolution{
		cfg: cfg,
		log: slog.Default().With("validator", strategyID),
	}
}

// NewWithDB constructs V21 with a live SQLite embedding index.
func NewWithDB(db *sql.DB, cfg Config) (*EntityResolution, error) {
	if cfg.Threshold == 0 {
		cfg.Threshold = DefaultThresh
	}
	if cfg.Embedder == nil {
		cfg.Embedder = &TFIDFEmbedder{}
	}
	idx, err := NewEmbeddingIndex(db, cfg.Embedder.Dim())
	if err != nil {
		return nil, err
	}
	return &EntityResolution{
		cfg:   cfg,
		index: idx,
		log:   slog.Default().With("validator", strategyID),
	}, nil
}

// ID returns "V21".
func (v *EntityResolution) ID() string { return strategyID }

// Name returns the human-readable name.
func (v *EntityResolution) Name() string { return strategyName }

// Severity is INFO — entity resolution enriches records, does not block publication.
func (v *EntityResolution) Severity() pipeline.Severity { return pipeline.SeverityInfo }

// Validate embeds the dealer text for this vehicle's dealer, searches for
// similar entities in the index, and returns the canonical entity ID if a
// match is found.
func (v *EntityResolution) Validate(ctx context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error) {
	start := time.Now()
	defer func() {
		metricLatency.Observe(time.Since(start).Seconds())
	}()

	result := &pipeline.ValidationResult{
		ValidatorID: strategyID,
		VehicleID:   vehicle.InternalID,
		Pass:        true,
		Severity:    pipeline.SeverityInfo,
		Evidence:    map[string]string{},
		Suggested:   map[string]string{},
	}

	// Build dealer text: "DealerID Name City Country" — we use DealerID as
	// the entity key and combine available metadata fields.
	dealerText := buildDealerText(vehicle)
	if dealerText == "" {
		result.Issue = "no dealer text available for embedding"
		return result, nil
	}

	// Embed dealer text.
	embedding, err := v.cfg.Embedder.Embed(ctx, dealerText)
	if err != nil {
		v.log.Warn("V21: embed failed",
			"dealer_id", vehicle.DealerID,
			"err", err,
		)
		result.Issue = fmt.Sprintf("embedding failed: %v", err)
		return result, nil
	}

	result.Confidence = 0.9
	result.Evidence["embedder"] = v.cfg.Embedder.Name()
	result.Evidence["dealer_text"] = dealerText

	// If no index is wired, just record the embedding attempt.
	if v.index == nil {
		result.Evidence["index"] = "no-op (no DB wired)"
		return result, nil
	}

	// Upsert this entity into the index.
	if err := v.index.Upsert(ctx, IndexEntry{
		EntityID:  vehicle.DealerID,
		Text:      dealerText,
		Embedding: embedding,
	}); err != nil {
		v.log.Warn("V21: index upsert failed",
			"dealer_id", vehicle.DealerID,
			"err", err,
		)
	}

	// Search for similar entities.
	matches, err := v.index.Search(ctx, embedding, v.cfg.Threshold, vehicle.DealerID)
	if err != nil {
		v.log.Warn("V21: index search failed",
			"dealer_id", vehicle.DealerID,
			"err", err,
		)
		return result, nil
	}

	if len(matches) == 0 {
		result.Evidence["entity_status"] = "unique"
		return result, nil
	}

	// Best match above threshold — suggest canonical entity ID.
	best := matches[0]
	metricMatches.Inc()
	result.Evidence["canonical_dealer_id"] = best.EntityID
	result.Evidence["canonical_text"] = best.Text
	result.Evidence["cosine_similarity"] = fmt.Sprintf("%.4f", best.Similarity)
	result.Evidence["entity_status"] = "merged"
	result.Suggested["canonical_dealer_id"] = best.EntityID

	v.log.Info("V21: entity resolved",
		"source_dealer", vehicle.DealerID,
		"canonical_dealer", best.EntityID,
		"similarity", best.Similarity,
	)

	return result, nil
}

// buildDealerText constructs a searchable text representation of a dealer
// from vehicle metadata. Combines DealerID, SourceCountry for a minimal
// but meaningful signal.
func buildDealerText(v *pipeline.Vehicle) string {
	parts := []string{}
	if v.DealerID != "" {
		parts = append(parts, v.DealerID)
	}
	if v.SourceCountry != "" {
		parts = append(parts, v.SourceCountry)
	}
	// Additional metadata from Metadata map if present.
	if v.Metadata != nil {
		if name := v.Metadata["dealer_name"]; name != "" {
			parts = append(parts, name)
		}
		if city := v.Metadata["dealer_city"]; city != "" {
			parts = append(parts, city)
		}
		if addr := v.Metadata["dealer_address"]; addr != "" {
			parts = append(parts, addr)
		}
	}
	return strings.Join(parts, " ")
}
