package pulse

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	// CriticalDealersTotal is the current count of dealers in the "critical"
	// health tier (score < 30). Updated after each scoring run.
	CriticalDealersTotal = promauto.NewGauge(prometheus.GaugeOpts{
		Namespace: "cardex",
		Subsystem: "pulse",
		Name:      "critical_dealers_total",
		Help:      "Number of dealers currently in the critical health tier (score < 30).",
	})

	// WatchDealersTotal counts dealers in the "watch" or worse tier (score < 70).
	WatchDealersTotal = promauto.NewGauge(prometheus.GaugeOpts{
		Namespace: "cardex",
		Subsystem: "pulse",
		Name:      "watch_dealers_total",
		Help:      "Number of dealers in watch, stress, or critical health tiers (score < 70).",
	})

	// ScoreComputeDuration tracks the wall-clock time for a single dealer scoring run.
	ScoreComputeDuration = promauto.NewHistogram(prometheus.HistogramOpts{
		Namespace: "cardex",
		Subsystem: "pulse",
		Name:      "score_compute_duration_seconds",
		Help:      "Wall-clock time to compute a single dealer health score.",
		Buckets:   prometheus.ExponentialBuckets(0.005, 2, 10),
	})
)
