# Delta always-on + operator alerting + auto-remediation

Closes the last unwired piece of the CEO vision (BLUEPRINT §5): altas/bajas in **seconds**,
an alert that pinpoints the **exact** failure point, and the orphan `remediate()` given a
**real call-site**. Built on the existing delta engine (`compute_delta`/`indexer`) and the
per-entity API — nothing rewritten.

## Components
| File | Role |
|---|---|
| `operator_events.py` | `emit_alert(entity, stage, signal, evidence)` → Redis `stream:operator_events` + PG `operator_alerts` + JSONL log. The structured alert. |
| `delta_worker.py` | Always-on consumer of `stream:harvest_batches`; applies SEEN/GONE via `indexer.insert_batch`/`delete_stale` in real time. At-least-once (ACK / XAUTOCLAIM reclaim / DLQ). |
| `remediation_dispatcher.py` | Consumer of `stream:operator_events`; routes signal→action; **calls the orphan `remediate()`**. Anti-churn cap (`MAX_REMEDIATIONS`) → DLQ. |
| `run_proofs.py` | The 3 end-to-end proofs (latency, alert, remediation). |

Wiring into the existing engine (small, reversible diffs):
- `scrapers/common/indexer.py` — `insert_batch` now auto-registers the source entity and
  sets `vehicle_index.entity_ulid = se_||md5(domain)`, so every new pointer is **live in the
  per-entity API the instant it lands** (degrades gracefully when the entity schema is absent).
  `delete_stale` now carries `url_original` on GONE events (clients see *which* car vanished).
- `scrapers/coordinator.py` — the drift `log.warning` is replaced by a real
  `operator_events.emit_alert(stage="extract", signal="volume_drift", …)`.
- `services/entity_api/app.py` — `GET /v1/alerts` exposes the operator_alerts feed.
- `scripts/migrations/0002_operator_alerts.{up,down}.sql` — the queryable alert table.

## Signal → action map (remediation_dispatcher)
| signal | action |
|---|---|
| `volume_drift` | **`remediate()`** — re-detect config, re-scrape sample, revalidate (the orphan call-site) |
| `parse_fail` | mark config drift for manual review (`status=escalated`, `action=config_review`) |
| `waf_block` | escalate / mark requires-proxy (`action=mark_requires_proxy`) |
| `timeout`/`dead` | retry-with-backoff (`status=open`) |

Anti-churn: per-entity `re-scrape` attempts within `WINDOW` are capped at `MAX_REMEDIATIONS`;
past the cap the alert routes to `stream:dlq` and `status=dlq` — no remediation livelock.

## Run (host)
PG is the canonical store (5432); Redis transport is the host-reachable throwaway (56390).
The canonical seam Redis is in-network — production workers run with `REDIS_URL=redis://:<pw>@cardex-redis:6379`.
```bash
DATABASE_URL=postgresql://cardex:cardex_dev_only@localhost:5432/cardex REDIS_URL=redis://localhost:56390 \
  python -m scrapers.delta.delta_worker            # always-on delta
DATABASE_URL=... REDIS_URL=... python -m scrapers.delta.remediation_dispatcher   # remediation
PYTHONIOENCODING=utf-8 ... python -m scrapers.delta.run_proofs                    # the 3 proofs
```

## Verified proofs (2026-06-08)
1. **Delta always-on:** push a new listing → visible in `/v1/entities/{ulid}/delta` in **~1.9 s**
   (SEEN); remove it → **GONE in ~0.3 s**. Event-driven, not a nightly batch.
2. **Exact-point alert:** a `volume_drift` alert persisted with `(entity_ulid, stage=extract,
   signal=volume_drift, evidence={volume:3, expected_min:50})`, visible from `operator_alerts`
   and `GET /v1/alerts`.
3. **Dispatcher call-site:** the dispatcher consumed the operator_event and invoked
   `remediate()` → `status=resolved, recovered=true, persisted=1, version 2→3`.

Plus: the dormant `stream:enrich_pending` consumer group was reactivated (group `cg_delta_link`,
backlog delivered, not acked so A6 still enriches).
