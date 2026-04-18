package check

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	metricRequestsTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "workspace",
		Subsystem: "check",
		Name:      "requests_total",
		Help:      "Total vehicle history report requests.",
	}, []string{"cache_hit"})

	metricProviderLatency = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Namespace: "workspace",
		Subsystem: "check",
		Name:      "provider_latency_seconds",
		Help:      "Time spent fetching data from each registry provider.",
		Buckets:   prometheus.DefBuckets,
	}, []string{"provider", "country"})

	metricProviderErrors = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "workspace",
		Subsystem: "check",
		Name:      "provider_errors_total",
		Help:      "Errors returned by registry providers.",
	}, []string{"provider", "country", "error_type"})

	metricMileageInconsistencies = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "workspace",
		Subsystem: "check",
		Name:      "mileage_inconsistencies_total",
		Help:      "Number of reports flagged for mileage inconsistency.",
	})
)
