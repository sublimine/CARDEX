package inbox

import (
	"sync"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	metricsOnce sync.Once

	conversationsTotal  *prometheus.CounterVec
	messagesTotal       *prometheus.CounterVec
	responseTimeSeconds *prometheus.HistogramVec
	overdueGauge        prometheus.Gauge
)

func initMetrics() {
	metricsOnce.Do(func() {
		conversationsTotal = promauto.NewCounterVec(prometheus.CounterOpts{
			Name: "workspace_inbox_conversations_total",
			Help: "Total conversations ingested, by status and platform.",
		}, []string{"status", "platform"})

		messagesTotal = promauto.NewCounterVec(prometheus.CounterOpts{
			Name: "workspace_inbox_messages_total",
			Help: "Total messages created, by direction.",
		}, []string{"direction"})

		responseTimeSeconds = promauto.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "workspace_inbox_response_time_seconds",
			Help:    "Time between first inbound message and first outbound reply.",
			Buckets: prometheus.DefBuckets,
		}, []string{})

		overdueGauge = promauto.NewGauge(prometheus.GaugeOpts{
			Name: "workspace_inbox_overdue_total",
			Help: "Number of open conversations past the overdue threshold.",
		})
	})
}

func init() { initMetrics() }

// RecordConversation increments the conversations counter.
func RecordConversation(status, platform string) {
	if conversationsTotal != nil {
		conversationsTotal.WithLabelValues(status, platform).Inc()
	}
}

// RecordMessage increments the messages counter.
func RecordMessage(direction string) {
	if messagesTotal != nil {
		messagesTotal.WithLabelValues(direction).Inc()
	}
}

// RecordResponseTime records a response-time observation.
func RecordResponseTime(seconds float64) {
	if responseTimeSeconds != nil {
		responseTimeSeconds.WithLabelValues().Observe(seconds)
	}
}

// SetOverdue sets the overdue conversations gauge.
func SetOverdue(n float64) {
	if overdueGauge != nil {
		overdueGauge.Set(n)
	}
}
