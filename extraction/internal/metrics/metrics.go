// Package metrics registers Prometheus metrics for the extraction pipeline.
//
// Naming convention: Namespace="cardex", Subsystem="extraction"
// → all metric names are "cardex_extraction_<name>".
package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	// ExtractionTotal counts completed extraction cycles by strategy, country,
	// and result ("success"|"partial"|"failure").
	ExtractionTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "cardex",
		Subsystem: "extraction",
		Name:      "total",
		Help:      "Total extraction cycles completed, by strategy and country.",
	}, []string{"strategy", "country", "result"})

	// VehiclesExtracted counts vehicles extracted per strategy and country.
	VehiclesExtracted = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "cardex",
		Subsystem: "extraction",
		Name:      "vehicles_extracted_total",
		Help:      "Total vehicles extracted, by strategy and country.",
	}, []string{"strategy", "country"})

	// VehiclesPersisted counts vehicle records written to the KG.
	VehiclesPersisted = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "cardex",
		Subsystem: "extraction",
		Name:      "vehicles_persisted_total",
		Help:      "Total vehicle records persisted to the knowledge graph.",
	}, []string{"country"})

	// ExtractionDuration observes extraction latency per strategy.
	ExtractionDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Namespace: "cardex",
		Subsystem: "extraction",
		Name:      "duration_seconds",
		Help:      "Extraction duration per strategy.",
		Buckets:   []float64{0.1, 0.5, 1, 2, 5, 10, 30, 60, 120},
	}, []string{"strategy"})

	// CascadeDepth observes how many strategies were attempted before success.
	CascadeDepth = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Namespace: "cardex",
		Subsystem: "extraction",
		Name:      "cascade_depth",
		Help:      "Number of strategies attempted before success or dead-letter.",
		Buckets:   []float64{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12},
	}, []string{"country"})

	// DeadLetterTotal counts dealers entering the dead-letter queue.
	DeadLetterTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "cardex",
		Subsystem: "extraction",
		Name:      "dead_letter_total",
		Help:      "Dealers for which all strategies failed (routed to E11/E12).",
	}, []string{"country"})

	// StrategyApplicableRate tracks how often each strategy passes Applicable().
	StrategyApplicableRate = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "cardex",
		Subsystem: "extraction",
		Name:      "strategy_applicable_total",
		Help:      "How many times each strategy passed the Applicable() check.",
	}, []string{"strategy"})

	// ParseErrors counts JSON-LD / XML / JSON parse errors by strategy.
	ParseErrors = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "cardex",
		Subsystem: "extraction",
		Name:      "parse_errors_total",
		Help:      "Parse errors encountered during extraction.",
	}, []string{"strategy", "error_code"})

	// QueueDepth is the current number of dealers pending extraction.
	// Updated after each batch dequeue. Used by the ExtractionQueueUnbounded alert.
	QueueDepth = promauto.NewGauge(prometheus.GaugeOpts{
		Namespace: "cardex",
		Subsystem: "extraction",
		Name:      "queue_depth",
		Help:      "Current number of dealers pending extraction.",
	})
)

// E13Requests counts per-image VLM inference calls by E13.
// status = "success" | "error" | "timeout"
var E13Requests = promauto.NewCounterVec(prometheus.CounterOpts{
	Namespace: "cardex",
	Subsystem: "extraction",
	Name:      "e13_requests_total",
	Help:      "Total VLM inference requests made by E13, by status.",
}, []string{"status"})

// E13Latency observes per-image VLM inference latency.
// Phi-3.5-vision Q4_K_M on Hetzner CX42 CPU: expected p50 ≈ 45 s.
var E13Latency = promauto.NewHistogram(prometheus.HistogramOpts{
	Namespace: "cardex",
	Subsystem: "extraction",
	Name:      "e13_latency_seconds",
	Help:      "Per-image VLM inference latency for strategy E13.",
	Buckets:   []float64{5, 10, 20, 30, 45, 60, 90, 120, 180},
})

// E13FieldsExtracted is the average vehicle fields extracted per image
// in the most recent E13 dealer run.
var E13FieldsExtracted = promauto.NewGauge(prometheus.GaugeOpts{
	Namespace: "cardex",
	Subsystem: "extraction",
	Name:      "e13_fields_extracted",
	Help:      "Average vehicle fields extracted per image in the last E13 run.",
})
