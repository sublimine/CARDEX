package kanban

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	metricKanbanMoves = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "workspace",
		Subsystem: "kanban",
		Name:      "moves_total",
		Help:      "Total Kanban card moves (vehicle state transitions).",
	}, []string{"tenant_id", "from_state", "to_state"})

	metricKanbanWIP = promauto.NewGaugeVec(prometheus.GaugeOpts{
		Namespace: "workspace",
		Subsystem: "kanban",
		Name:      "wip_current",
		Help:      "Current number of cards per Kanban column.",
	}, []string{"tenant_id", "column_id"})

	metricCalendarEvents = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "workspace",
		Subsystem: "calendar",
		Name:      "events_total",
		Help:      "Total calendar events created.",
	}, []string{"tenant_id", "event_type"})

	metricCalendarOverdue = promauto.NewGaugeVec(prometheus.GaugeOpts{
		Namespace: "workspace",
		Subsystem: "calendar",
		Name:      "overdue_total",
		Help:      "Number of scheduled events past their end time.",
	}, []string{"tenant_id"})
)
