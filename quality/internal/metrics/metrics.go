// Package metrics exposes Prometheus counters and histograms for the quality pipeline.
package metrics

import "github.com/prometheus/client_golang/prometheus"

var (
	// ValidationTotal counts completed validator runs.
	// Labels: validator_id, severity, result ("pass"|"fail"|"skip").
	ValidationTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Namespace: "cardex",
			Subsystem: "quality",
			Name:      "validation_total",
			Help:      "Total number of validation runs, by validator, severity, and result.",
		},
		[]string{"validator_id", "severity", "result"},
	)

	// ValidationDuration tracks how long each validator takes per vehicle.
	ValidationDuration = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Namespace: "cardex",
			Subsystem: "quality",
			Name:      "validation_duration_seconds",
			Help:      "Histogram of validation duration in seconds.",
			Buckets:   prometheus.DefBuckets,
		},
		[]string{"validator_id"},
	)

	// CriticalFailures counts vehicles with at least one CRITICAL validation failure.
	// Labels: validator_id.
	CriticalFailures = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Namespace: "cardex",
			Subsystem: "quality",
			Name:      "critical_failures_total",
			Help:      "Total vehicles with a CRITICAL validation failure.",
		},
		[]string{"validator_id"},
	)

	// VehiclesValidated counts vehicles that completed the full pipeline.
	VehiclesValidated = prometheus.NewCounter(prometheus.CounterOpts{
		Namespace: "cardex",
		Subsystem: "quality",
		Name:      "vehicles_validated_total",
		Help:      "Total vehicles that have been through the full validation pipeline.",
	})

	// PendingVehicles is the current number of vehicles awaiting quality
	// validation. Updated after each batch dequeue.
	// Used by the QualityQueueUnbounded alert.
	PendingVehicles = prometheus.NewGauge(prometheus.GaugeOpts{
		Namespace: "cardex",
		Subsystem: "quality",
		Name:      "pending_vehicles",
		Help:      "Current number of vehicles awaiting quality validation.",
	})
)

func init() {
	prometheus.MustRegister(
		ValidationTotal,
		ValidationDuration,
		CriticalFailures,
		VehiclesValidated,
		PendingVehicles,
	)
}
