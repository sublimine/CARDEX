package ev_watch

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	metricAnomaliesDetected = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "cardex",
		Subsystem: "ev_watch",
		Name:      "anomalies_detected_total",
		Help:      "Total EV listings flagged as price anomalies (z < -1.5).",
	})

	// metricSevereAnomalies fires when z < -2.0 AND cohort_size >= 30.
	metricSevereAnomalies = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "cardex",
		Subsystem: "ev_watch",
		Name:      "severe_anomaly_total",
		Help:      "EV listings with severe price anomaly (z < -2.0, cohort >= 30): possible battery degradation.",
	})

	metricCohortSize = promauto.NewHistogram(prometheus.HistogramOpts{
		Namespace: "cardex",
		Subsystem: "ev_watch",
		Name:      "cohort_size",
		Help:      "Distribution of EV cohort sizes used for z-score computation.",
		Buckets:   []float64{20, 30, 50, 75, 100, 150, 200, 500},
	})

	metricAnalysisDuration = promauto.NewHistogram(prometheus.HistogramOpts{
		Namespace: "cardex",
		Subsystem: "ev_watch",
		Name:      "analysis_duration_seconds",
		Help:      "Duration of a full EV anomaly analysis run.",
		Buckets:   prometheus.DefBuckets,
	})
)
