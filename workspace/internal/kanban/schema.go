package kanban

import "database/sql"

const kanbanSchema = `
CREATE TABLE IF NOT EXISTS crm_kanban_columns (
    id           TEXT    PRIMARY KEY,
    tenant_id    TEXT    NOT NULL,
    name         TEXT    NOT NULL,
    position     INTEGER NOT NULL DEFAULT 0,
    color        TEXT    NOT NULL DEFAULT '#6B7280',
    vehicle_limit INTEGER NOT NULL DEFAULT 0,
    is_default   INTEGER NOT NULL DEFAULT 0,
    state_key    TEXT,
    created_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, position)
);
CREATE INDEX IF NOT EXISTS idx_kanban_columns_tenant ON crm_kanban_columns(tenant_id, position);

CREATE TABLE IF NOT EXISTS crm_kanban_cards (
    vehicle_id   TEXT    NOT NULL,
    tenant_id    TEXT    NOT NULL,
    column_id    TEXT    NOT NULL REFERENCES crm_kanban_columns(id),
    position     INTEGER NOT NULL DEFAULT 0,
    assignee_id  TEXT,
    priority     TEXT    NOT NULL DEFAULT 'normal',
    labels       TEXT    NOT NULL DEFAULT '[]',
    due_date     TEXT,
    updated_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (vehicle_id)
);
CREATE INDEX IF NOT EXISTS idx_kanban_cards_tenant  ON crm_kanban_cards(tenant_id, column_id, position);
CREATE INDEX IF NOT EXISTS idx_kanban_cards_assignee ON crm_kanban_cards(tenant_id, assignee_id)
    WHERE assignee_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS crm_vehicles (
    id          TEXT NOT NULL,
    tenant_id   TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'sourcing',
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id, tenant_id)
);

CREATE TABLE IF NOT EXISTS crm_events (
    id               TEXT    PRIMARY KEY,
    tenant_id        TEXT    NOT NULL,
    title            TEXT    NOT NULL,
    description      TEXT    NOT NULL DEFAULT '',
    event_type       TEXT    NOT NULL DEFAULT 'other',
    vehicle_id       TEXT,
    contact_id       TEXT,
    deal_id          TEXT,
    start_at         TEXT    NOT NULL,
    end_at           TEXT    NOT NULL,
    all_day          INTEGER NOT NULL DEFAULT 0,
    location         TEXT    NOT NULL DEFAULT '',
    assignee_id      TEXT,
    status           TEXT    NOT NULL DEFAULT 'scheduled',
    reminder_minutes INTEGER NOT NULL DEFAULT 0,
    auto_generated   INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_events_tenant_range  ON crm_events(tenant_id, start_at, end_at);
CREATE INDEX IF NOT EXISTS idx_events_vehicle       ON crm_events(tenant_id, vehicle_id)
    WHERE vehicle_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_status        ON crm_events(tenant_id, status);
`

// EnsureSchema creates kanban and calendar tables if they do not exist.
func EnsureSchema(db *sql.DB) error {
	_, err := db.Exec(kanbanSchema)
	return err
}

// DefaultColumns returns the 11 standard pipeline columns for a new tenant.
func DefaultColumns(tenantID string) []Column {
	defs := []struct {
		name     string
		color    string
		stateKey string
	}{
		{"Sourcing", "#64748B", "sourcing"},
		{"Acquired", "#0EA5E9", "acquired"},
		{"Reconditioning", "#F59E0B", "reconditioning"},
		{"Photography", "#8B5CF6", "photography"},
		{"Listed", "#10B981", "listed"},
		{"Inquiry", "#3B82F6", "inquiry"},
		{"Negotiation", "#F97316", "negotiation"},
		{"Reserved", "#EF4444", "reserved"},
		{"Sold", "#6D28D9", "sold"},
		{"In Transit", "#0891B2", "in_transit"},
		{"Delivered", "#059669", "delivered"},
	}
	now := nowRFC3339()
	cols := make([]Column, len(defs))
	for i, d := range defs {
		cols[i] = Column{
			ID:        newID(),
			TenantID:  tenantID,
			Name:      d.name,
			Position:  i,
			Color:     d.color,
			StateKey:  d.stateKey,
			IsDefault: true,
			CreatedAt: now,
			UpdatedAt: now,
		}
	}
	return cols
}
