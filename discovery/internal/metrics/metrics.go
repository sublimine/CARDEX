// Package metrics registers all Prometheus metrics for the discovery service.
// Metrics are registered once at init time; callers import this package for
// the side-effect and use the exported variables directly.
package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	// DealersTotal counts total dealer entities written to the KG, broken down
	// by family and country.
	DealersTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "cardex_discovery_dealers_total",
			Help: "Total dealer entities discovered and written to the Knowledge Graph.",
		},
		[]string{"family", "country"},
	)

	// CycleDuration is a histogram of full discovery-cycle wall-clock durations
	// (one observation per completed family+country run).
	CycleDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "cardex_discovery_cycle_duration_seconds",
			Help:    "Wall-clock duration of a discovery cycle per family and country.",
			Buckets: prometheus.ExponentialBuckets(1, 2, 12), // 1s … ~68 min
		},
		[]string{"family", "country"},
	)

	// HealthCheckStatus is a gauge that is 1 when the family is healthy and 0
	// when its HealthCheck() returned an error.
	HealthCheckStatus = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "cardex_discovery_health_check_status",
			Help: "1 = healthy, 0 = unhealthy. One time series per family.",
		},
		[]string{"family"},
	)

	// SubTechniqueRequests counts outbound HTTP requests made by each
	// sub-technique, labelled by status (2xx, 4xx, 5xx, timeout).
	SubTechniqueRequests = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "cardex_discovery_subtechnique_requests_total",
			Help: "Total HTTP requests issued by each sub-technique.",
		},
		[]string{"sub_technique", "status"},
	)
)
