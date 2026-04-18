package syndication

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	metricPublishedTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "workspace",
		Subsystem: "syndication",
		Name:      "published_total",
		Help:      "Total syndication publish/update operations by platform and status.",
	}, []string{"platform", "status"})

	metricErrorsTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "workspace",
		Subsystem: "syndication",
		Name:      "errors_total",
		Help:      "Total syndication errors by platform and error type.",
	}, []string{"platform", "error_type"})

	metricLatency = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Namespace: "workspace",
		Subsystem: "syndication",
		Name:      "latency_seconds",
		Help:      "Latency of syndication publish/withdraw/status operations.",
		Buckets:   prometheus.DefBuckets,
	}, []string{"platform"})

	metricActiveListings = promauto.NewGaugeVec(prometheus.GaugeOpts{
		Namespace: "workspace",
		Subsystem: "syndication",
		Name:      "active_listings",
		Help:      "Current number of active (published) listings per platform.",
	}, []string{"platform"})
)
