package finance

import (
	"sync"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	metricsOnce          sync.Once
	metricTransactionsTotal prometheus.Counter
	metricMarginCents       prometheus.Histogram
	metricAlertsActive      prometheus.Gauge
)

func init() { initMetrics() }

func initMetrics() {
	metricsOnce.Do(func() {
		metricTransactionsTotal = promauto.NewCounter(prometheus.CounterOpts{
			Name: "finance_transactions_total",
			Help: "Total financial transactions created.",
		})
		metricMarginCents = promauto.NewHistogram(prometheus.HistogramOpts{
			Name:    "finance_margin_cents",
			Help:    "Gross margin per vehicle P&L calculation (EUR cents).",
			Buckets: []float64{-500000, -100000, 0, 50000, 100000, 200000, 500000, 1000000, 2000000},
		})
		metricAlertsActive = promauto.NewGauge(prometheus.GaugeOpts{
			Name: "finance_alerts_active",
			Help: "Number of active financial alerts across all vehicles.",
		})
	})
}
