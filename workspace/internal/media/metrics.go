package media

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	uploadsTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "workspace",
		Subsystem: "media",
		Name:      "uploads_total",
		Help:      "Total number of photo uploads, labelled by status (success|error) and tenant.",
	}, []string{"tenant_id", "status"})

	processingDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Namespace: "workspace",
		Subsystem: "media",
		Name:      "processing_duration_seconds",
		Help:      "Time spent processing a single photo through all variants.",
		Buckets:   prometheus.DefBuckets,
	}, []string{"variant"})

	storageBytesTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "workspace",
		Subsystem: "media",
		Name:      "storage_bytes_total",
		Help:      "Total bytes written to media storage, labelled by variant.",
	}, []string{"variant"})
)
