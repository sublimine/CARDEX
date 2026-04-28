package finance

import "database/sql"

const financeSchema = `
CREATE TABLE IF NOT EXISTS crm_transactions (
    id            TEXT    PRIMARY KEY,
    tenant_id     TEXT    NOT NULL,
    vehicle_id    TEXT    NOT NULL,
    type          TEXT    NOT NULL,
    amount_cents  INTEGER NOT NULL,
    currency      TEXT    NOT NULL DEFAULT 'EUR',
    vat_cents     INTEGER NOT NULL DEFAULT 0,
    vat_rate      REAL    NOT NULL DEFAULT 0,
    counterparty  TEXT    NOT NULL DEFAULT '',
    reference     TEXT    NOT NULL DEFAULT '',
    date          TEXT    NOT NULL,
    notes         TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tx_tenant_vehicle ON crm_transactions(tenant_id, vehicle_id);
CREATE INDEX IF NOT EXISTS idx_tx_tenant_type    ON crm_transactions(tenant_id, type);
CREATE INDEX IF NOT EXISTS idx_tx_tenant_date    ON crm_transactions(tenant_id, date);

CREATE TABLE IF NOT EXISTS crm_exchange_rates (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    from_currency TEXT    NOT NULL,
    to_currency   TEXT    NOT NULL,
    rate          REAL    NOT NULL,
    valid_from    TEXT    NOT NULL,
    UNIQUE(from_currency, to_currency, valid_from)
);
CREATE INDEX IF NOT EXISTS idx_fx_pair ON crm_exchange_rates(from_currency, to_currency, valid_from DESC);
`

// EnsureSchema creates the finance tables if they do not exist (idempotent).
func EnsureSchema(db *sql.DB) error {
	_, err := db.Exec(financeSchema)
	return err
}
