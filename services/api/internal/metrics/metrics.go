// Package metrics declares the Prometheus instruments for the API service.
//
// Naming follows the repo-wide convention: Namespace "cardex", Subsystem "api",
// so series become cardex_api_*. Metrics auto-register via promauto.
package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// RequestsTotal counts HTTP requests by route, method and status class.
var RequestsTotal = promauto.NewCounterVec(prometheus.CounterOpts{
	Namespace: "cardex",
	Subsystem: "api",
	Name:      "requests_total",
	Help:      "Total HTTP requests handled, by route, method and status class (2xx/4xx/5xx).",
}, []string{"route", "method", "status"})

// RequestDuration measures handler latency in seconds by route.
var RequestDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
	Namespace: "cardex",
	Subsystem: "api",
	Name:      "request_duration_seconds",
	Help:      "HTTP handler latency in seconds, by route.",
	Buckets:   []float64{0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5},
}, []string{"route"})

// RateLimited counts requests rejected by the rate limiter, by tier.
var RateLimited = promauto.NewCounterVec(prometheus.CounterOpts{
	Namespace: "cardex",
	Subsystem: "api",
	Name:      "rate_limited_total",
	Help:      "Requests rejected with HTTP 429, by tier.",
}, []string{"tier"})

// AuthFailures counts requests rejected for missing/invalid API keys.
var AuthFailures = promauto.NewCounter(prometheus.CounterOpts{
	Namespace: "cardex",
	Subsystem: "api",
	Name:      "auth_failures_total",
	Help:      "Requests rejected with HTTP 401 due to missing or invalid API key.",
})

// RateLimiterDegraded counts how often the rate limiter failed open because
// Redis was unavailable. Alert on a non-zero rate: it means rate limits are not
// being enforced.
var RateLimiterDegraded = promauto.NewCounter(prometheus.CounterOpts{
	Namespace: "cardex",
	Subsystem: "api",
	Name:      "rate_limiter_degraded_total",
	Help:      "Times the rate limiter failed open due to Redis unavailability (limits NOT enforced).",
})

// CacheHits / CacheMisses track Redis response-cache effectiveness.
var (
	CacheHits = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "cardex",
		Subsystem: "api",
		Name:      "cache_hits_total",
		Help:      "Redis response-cache hits, by route.",
	}, []string{"route"})
	CacheMisses = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "cardex",
		Subsystem: "api",
		Name:      "cache_misses_total",
		Help:      "Redis response-cache misses, by route.",
	}, []string{"route"})
)

// AlertsEvaluated counts background alert-evaluation cycles and the matches found.
var (
	AlertEvalRuns = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "cardex",
		Subsystem: "api",
		Name:      "alert_eval_runs_total",
		Help:      "Total background alert-evaluation cycles executed.",
	})
	AlertNotificationsSent = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "cardex",
		Subsystem: "api",
		Name:      "alert_notifications_total",
		Help:      "Alert notifications dispatched, by channel (webhook/email) and result (ok/error).",
	}, []string{"channel", "result"})
)
