"""CARDEX delta-always-on + operator alerting + auto-remediation wiring.

Modules:
  operator_events        — emit structured alerts (the exact failure point) to
                           stream:operator_events + operator_alerts table + JSONL log.
  delta_worker           — always-on consumer of stream:harvest_batches: applies
                           SEEN/GONE to vehicle_index/vehicle_events in real time.
  remediation_dispatcher — consumes stream:operator_events and wires the orphan
                           remediate() to a real call-site (anti-churn cap -> DLQ).
"""
