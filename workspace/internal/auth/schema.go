package auth

import "database/sql"

const userSchema = `
CREATE TABLE IF NOT EXISTS crm_users (
    id            TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    email         TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    name          TEXT NOT NULL DEFAULT '',
    role          TEXT NOT NULL DEFAULT 'dealer',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE(tenant_id, email)
);
CREATE INDEX IF NOT EXISTS idx_users_tenant_email ON crm_users(tenant_id, email);
`

// EnsureSchema creates the crm_users table if it does not exist.
func EnsureSchema(db *sql.DB) error {
	_, err := db.Exec(userSchema)
	return err
}
