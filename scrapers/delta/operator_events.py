"""Operator alerting — emit a structured event pinpointing the EXACT failure point.

An alert is (entity_ulid, stage, signal, evidence). It lands in THREE sinks, all
internal (no external channel yet — Elias manages alerts himself):
  1. Redis stream:operator_events   — drives the remediation_dispatcher.
  2. PG operator_alerts table        — queryable history (/v1/alerts endpoint).
  3. JSONL log file                  — a flat file the dashboard can tail.

Self-contained: opens ephemeral connections when not given pooled ones, so any
caller (coordinator, workers) can emit without threading handles through.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import asyncpg
import redis.asyncio as aioredis

log = logging.getLogger(__name__)

PG_DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:56390")
OPERATOR_EVENTS_STREAM = "stream:operator_events"
ALERTS_LOG = Path(os.environ.get("OPERATOR_ALERTS_LOG", "logs/operator_alerts.jsonl"))

STAGES = ("discovery", "resolve", "classify", "extract", "seam", "api")
SIGNALS = ("waf_block", "volume_drift", "parse_fail", "timeout", "dead", "other")
SEVERITIES = ("info", "warning", "critical")


def entity_ulid_for(source_key: str) -> str:
    """Deterministic source-entity id — matches the migration's 'se_'||md5(source_key)."""
    return "se_" + hashlib.md5(source_key.encode("utf-8")).hexdigest()


async def emit_alert(
    *,
    source_key: str,
    stage: str,
    signal: str,
    evidence: dict[str, Any] | None = None,
    entity_ulid: str | None = None,
    severity: str = "warning",
    pg: asyncpg.Connection | asyncpg.Pool | None = None,
    rdb: aioredis.Redis | None = None,
) -> int:
    """Persist + publish one alert. Returns the operator_alerts.alert_id.

    `stage`/`signal`/`severity` are validated against the table's CHECK domains so a
    typo fails loudly here, not as an opaque SQL error.
    """
    if stage not in STAGES:
        raise ValueError(f"bad stage {stage!r}; expected one of {STAGES}")
    if signal not in SIGNALS:
        raise ValueError(f"bad signal {signal!r}; expected one of {SIGNALS}")
    if severity not in SEVERITIES:
        raise ValueError(f"bad severity {severity!r}")
    ent = entity_ulid or entity_ulid_for(source_key)
    ev = evidence or {}
    ev_json = json.dumps(ev, default=str)
    ts = time.time()

    own_pg = pg is None
    own_rdb = rdb is None
    if own_pg:
        pg = await asyncpg.connect(PG_DSN)
    if own_rdb:
        rdb = aioredis.from_url(REDIS_URL, decode_responses=False)
    try:
        # 1) queryable history (entity_ulid may be NULL if the source has no row yet)
        ent_exists = await pg.fetchval("SELECT 1 FROM source_entities WHERE entity_ulid=$1", ent)
        alert_id = await pg.fetchval(
            """INSERT INTO operator_alerts
                 (entity_ulid, source_key, stage, signal, severity, evidence)
               VALUES ($1,$2,$3,$4,$5,$6::jsonb) RETURNING alert_id""",
            ent if ent_exists else None, source_key, stage, signal, severity, ev_json,
        )
        # 2) drive remediation
        await rdb.xadd(
            OPERATOR_EVENTS_STREAM,
            {"alert_id": str(alert_id), "entity_ulid": ent, "source_key": source_key,
             "stage": stage, "signal": signal, "severity": severity,
             "evidence": ev_json, "ts": str(ts)},
            maxlen=1_000_000,
        )
    finally:
        if own_pg:
            await pg.close()
        if own_rdb:
            await rdb.aclose()

    # 3) structured log + flat file (dashboard-readable)
    rec = {"alert_id": alert_id, "entity_ulid": ent, "source_key": source_key,
           "stage": stage, "signal": signal, "severity": severity, "evidence": ev, "ts": ts}
    log.warning("OPERATOR_ALERT id=%s entity=%s stage=%s signal=%s sev=%s ev=%s",
                alert_id, ent, stage, signal, severity, ev_json)
    try:
        ALERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with ALERTS_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
    except OSError as exc:  # flat-file is best-effort; never fail the alert on it
        log.error("operator_alerts.jsonl write failed: %s", exc)
    return alert_id
