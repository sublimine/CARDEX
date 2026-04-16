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

	// ReviewQueuePending is the current number of listings awaiting human review.
	// Updated after each validation cycle by querying review_queue WHERE status='PENDING'.
	ReviewQueuePending = prometheus.NewGauge(prometheus.GaugeOpts{
		Namespace: "cardex",
		Subsystem: "quality",
		Name:      "review_queue_pending",
		Help:      "Current number of vehicle listings pending manual review.",
	})

	// ReviewQueueResolved counts review queue items resolved (approved or rejected).
	// Labels: action ("approved"|"rejected").
	ReviewQueueResolved = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Namespace: "cardex",
			Subsystem: "quality",
			Name:      "review_queue_resolved_total",
			Help:      "Total review queue items resolved, by action (approved or rejected).",
		},
		[]string{"action"},
	)
)

func init() {
	prometheus.MustRegister(
		ValidationTotal,
		ValidationDuration,
		CriticalFailures,
		VehiclesValidated,
		PendingVehicles,
		ReviewQueuePending,
		ReviewQueueResolved,
	)
}

// SanitizeValidatorID returns the validator_id label value if it is a known
// V-code (V01–V20), or "unknown" otherwise. Call this before WithLabelValues
// to prevent unbounded Prometheus cardinality from unexpected values.
func SanitizeValidatorID(v string) string {
	switch v {
	case "V01", "V02", "V03", "V04", "V05", "V06", "V07", "V08", "V09", "V10",
		"V11", "V12", "V13", "V14", "V15", "V16", "V17", "V18", "V19", "V20":
		return v
	}
	return "unknown"
}
