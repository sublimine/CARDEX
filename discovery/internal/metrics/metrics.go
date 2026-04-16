// Package metrics registers all Prometheus metrics for the discovery service.
// Metrics are registered once at init time; callers import this package for
// the side-effect and use the exported variables directly.
//
// Naming convention: Namespace="cardex", Subsystem="discovery"
// → all metric names are "cardex_discovery_<name>".
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
			Namespace: "cardex",
			Subsystem: "discovery",
			Name:      "dealers_total",
			Help:      "Total dealer entities discovered and written to the Knowledge Graph.",
		},
		[]string{"family", "country"},
	)

	// CycleDuration is a histogram of full discovery-cycle wall-clock durations
	// (one observation per completed family+country run).
	CycleDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Namespace: "cardex",
			Subsystem: "discovery",
			Name:      "cycle_duration_seconds",
			Help:      "Wall-clock duration of a discovery cycle per family and country.",
			Buckets:   prometheus.ExponentialBuckets(1, 2, 12), // 1s … ~68 min
		},
		[]string{"family", "country"},
	)

	// HealthCheckStatus is a gauge that is 1 when the family is healthy and 0
	// when its HealthCheck() returned an error.
	HealthCheckStatus = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Namespace: "cardex",
			Subsystem: "discovery",
			Name:      "health_check_status",
			Help:      "1 = healthy, 0 = unhealthy. One time series per family.",
		},
		[]string{"family"},
	)

	// SubTechniqueRequests counts outbound HTTP requests made by each
	// sub-technique, labelled by status class (2xx, 3xx, 4xx, 5xx, err).
	// Allowed status values: "2xx", "3xx", "4xx", "5xx", "err".
	SubTechniqueRequests = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Namespace: "cardex",
			Subsystem: "discovery",
			Name:      "subtechnique_requests_total",
			Help:      "Total HTTP requests issued by each sub-technique.",
		},
		[]string{"sub_technique", "status"},
	)

	// ScrapeErrors counts scraping errors per family and error type.
	// Incremented whenever a family run returns a non-retryable error.
	ScrapeErrors = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Namespace: "cardex",
			Subsystem: "discovery",
			Name:      "scrape_errors_total",
			Help:      "Total scraping errors by family and error type.",
		},
		[]string{"family", "error_type"},
	)

	// ScrapeRequests counts total scraping attempts per family (success + error).
	ScrapeRequests = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Namespace: "cardex",
			Subsystem: "discovery",
			Name:      "scrape_requests_total",
			Help:      "Total scraping attempts (both successful and failed) per family.",
		},
		[]string{"family"},
	)

	// SQLiteWALBytes is the current size in bytes of the SQLite WAL file.
	// Updated by the discovery service on each cycle.
	// Alert threshold: > 500 MB (see alertmanager/rules.yml SQLiteWALSizeHigh).
	SQLiteWALBytes = promauto.NewGauge(
		prometheus.GaugeOpts{
			Namespace: "cardex",
			Subsystem: "discovery",
			Name:      "sqlite_wal_size_bytes",
			Help:      "Current size of the SQLite WAL file in bytes.",
		},
	)

	// LastBackupTimestamp is a Unix timestamp (seconds) of the last successful
	// backup run. Updated by the backup script via the metrics endpoint.
	// Alert: stale if time() - LastBackupTimestamp > 90000 (25h).
	LastBackupTimestamp = promauto.NewGauge(
		prometheus.GaugeOpts{
			Namespace: "cardex",
			Subsystem: "discovery",
			Name:      "last_backup_timestamp_seconds",
			Help:      "Unix timestamp of the last successful backup.",
		},
	)
)
