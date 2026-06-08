-- 0002_operator_alerts.up.sql
-- Operator alerting: structured, queryable persistence of pipeline failures/drift.
-- Each alert pinpoints the EXACT failure point: (entity, stage, signal, evidence).
-- No external channel yet (Elias manages alerts) -> this table + a JSONL log + a
-- /v1/alerts endpoint are the internal channel the dashboard reads.
-- Reversible: see 0002_operator_alerts.down.sql.

BEGIN;

CREATE TABLE IF NOT EXISTS operator_alerts (
    alert_id           BIGSERIAL PRIMARY KEY,
    entity_ulid        TEXT REFERENCES source_entities(entity_ulid) ON DELETE SET NULL,
    source_key         TEXT,
    stage              TEXT NOT NULL CHECK (stage IN ('discovery','resolve','classify','extract','seam','api')),
    signal             TEXT NOT NULL CHECK (signal IN ('waf_block','volume_drift','parse_fail','timeout','dead','other')),
    severity           TEXT NOT NULL DEFAULT 'warning' CHECK (severity IN ('info','warning','critical')),
    evidence           JSONB NOT NULL DEFAULT '{}'::jsonb,
    status             TEXT NOT NULL DEFAULT 'open'
                       CHECK (status IN ('open','remediating','resolved','escalated','dlq')),
    remediation_action TEXT,
    remediation_result JSONB,
    attempts           SMALLINT NOT NULL DEFAULT 0,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_oa_entity  ON operator_alerts(entity_ulid);
CREATE INDEX IF NOT EXISTS idx_oa_status  ON operator_alerts(status);
CREATE INDEX IF NOT EXISTS idx_oa_signal  ON operator_alerts(signal);
CREATE INDEX IF NOT EXISTS idx_oa_created ON operator_alerts(created_at DESC);

COMMIT;
