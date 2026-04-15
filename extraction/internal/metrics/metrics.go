// Package metrics registers Prometheus metrics for the extraction pipeline.
package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	// ExtractionTotal counts successful extraction cycles by strategy and country.
	ExtractionTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "cardex_extraction",
		Name:      "total",
		Help:      "Total extraction cycles completed, by strategy and country.",
	}, []string{"strategy", "country", "result"})

	// VehiclesExtracted counts vehicles extracted per strategy and country.
	VehiclesExtracted = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "cardex_extraction",
		Name:      "vehicles_extracted_total",
		Help:      "Total vehicles extracted, by strategy and country.",
	}, []string{"strategy", "country"})

	// VehiclesPersisted counts vehicle records written to the KG.
	VehiclesPersisted = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "cardex_extraction",
		Name:      "vehicles_persisted_total",
		Help:      "Total vehicle records persisted to the knowledge graph.",
	}, []string{"country"})

	// ExtractionDuration observes extraction latency per strategy.
	ExtractionDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Namespace: "cardex_extraction",
		Name:      "duration_seconds",
		Help:      "Extraction duration per strategy.",
		Buckets:   []float64{0.1, 0.5, 1, 2, 5, 10, 30, 60, 120},
	}, []string{"strategy"})

	// CascadeDepth observes how many strategies were attempted before success.
	CascadeDepth = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Namespace: "cardex_extraction",
		Name:      "cascade_depth",
		Help:      "Number of strategies attempted before success or dead-letter.",
		Buckets:   []float64{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12},
	}, []string{"country"})

	// DeadLetterTotal counts dealers entering the dead-letter queue.
	DeadLetterTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "cardex_extraction",
		Name:      "dead_letter_total",
		Help:      "Dealers for which all strategies failed (routed to E11/E12).",
	}, []string{"country"})

	// StrategyApplicableRate tracks how often each strategy passes Applicable().
	StrategyApplicableRate = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "cardex_extraction",
		Name:      "strategy_applicable_total",
		Help:      "How many times each strategy passed the Applicable() check.",
	}, []string{"strategy"})

	// ParseErrors counts JSON-LD / XML / JSON parse errors by strategy.
	ParseErrors = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "cardex_extraction",
		Name:      "parse_errors_total",
		Help:      "Parse errors encountered during extraction.",
	}, []string{"strategy", "error_code"})
)
