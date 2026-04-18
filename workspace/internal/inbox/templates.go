package inbox

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
	"time"
)

// TemplateStore manages response templates.
type TemplateStore struct {
	db *sql.DB
}

// NewTemplateStore creates a store backed by db.
func NewTemplateStore(db *sql.DB) *TemplateStore {
	return &TemplateStore{db: db}
}

// List returns all templates visible to tenantID in the given language.
// Includes system templates. Pass lang="" to return all languages.
func (s *TemplateStore) List(tenantID, lang string) ([]*Template, error) {
	query := `SELECT id,tenant_id,name,language,subject,body,is_system,created_at,updated_at
	          FROM crm_templates
	          WHERE (tenant_id=? OR tenant_id=?)`
	args := []any{tenantID, systemTenant}
	if lang != "" {
		query += " AND language=?"
		args = append(args, lang)
	}
	query += " ORDER BY is_system DESC, name, language"

	rows, err := s.db.QueryContext(context.Background(), query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []*Template
	for rows.Next() {
		t, err := scanTemplate(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, t)
	}
	return out, rows.Err()
}

// GetByID returns one template, checking tenant ownership or system.
func (s *TemplateStore) GetByID(tenantID, id string) (*Template, error) {
	row := s.db.QueryRowContext(context.Background(),
		`SELECT id,tenant_id,name,language,subject,body,is_system,created_at,updated_at
		 FROM crm_templates WHERE id=? AND (tenant_id=? OR tenant_id=?)`,
		id, tenantID, systemTenant)
	t, err := scanTemplateRow(row)
	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("template %s not found", id)
	}
	return t, err
}

// Create inserts a new custom template for a tenant.
func (s *TemplateStore) Create(t *Template) error {
	if t.ID == "" {
		t.ID = newID()
	}
	now := time.Now().UTC().Format(time.RFC3339)
	t.CreatedAt, _ = time.Parse(time.RFC3339, now)
	t.UpdatedAt = t.CreatedAt
	_, err := s.db.ExecContext(context.Background(),
		`INSERT INTO crm_templates(id,tenant_id,name,language,subject,body,is_system,created_at,updated_at)
		 VALUES(?,?,?,?,?,?,0,?,?)`,
		t.ID, t.TenantID, t.Name, t.Language, t.Subject, t.Body, now, now)
	return err
}

// Update modifies subject and body of a custom (non-system) template.
func (s *TemplateStore) Update(tenantID, id, subject, body string) error {
	nowStr := time.Now().UTC().Format(time.RFC3339)
	res, err := s.db.ExecContext(context.Background(),
		`UPDATE crm_templates SET subject=?,body=?,updated_at=?
		 WHERE id=? AND tenant_id=? AND is_system=0`,
		subject, body, nowStr, id, tenantID)
	if err != nil {
		return err
	}
	n, _ := res.RowsAffected()
	if n == 0 {
		return fmt.Errorf("template %s not found or is a system template", id)
	}
	return nil
}

// Render replaces {{key}} placeholders in subject and body.
// Unknown placeholders are left as-is.
func Render(tmpl *Template, vars map[string]string) (subject, body string) {
	subject = tmpl.Subject
	body = tmpl.Body
	for k, v := range vars {
		ph := "{{" + k + "}}"
		subject = strings.ReplaceAll(subject, ph, v)
		body = strings.ReplaceAll(body, ph, v)
	}
	return
}

// ── scanners ──────────────────────────────────────────────────────────────────

func scanTemplate(rs rowScanner) (*Template, error) {
	t := &Template{}
	var created, updated string
	var isSystem int
	err := rs.Scan(&t.ID, &t.TenantID, &t.Name, &t.Language, &t.Subject, &t.Body, &isSystem, &created, &updated)
	if err != nil {
		return nil, err
	}
	t.IsSystem = isSystem == 1
	t.CreatedAt, _ = time.Parse(time.RFC3339, created)
	t.UpdatedAt, _ = time.Parse(time.RFC3339, updated)
	return t, nil
}

func scanTemplateRow(row *sql.Row) (*Template, error) {
	t := &Template{}
	var created, updated string
	var isSystem int
	err := row.Scan(&t.ID, &t.TenantID, &t.Name, &t.Language, &t.Subject, &t.Body, &isSystem, &created, &updated)
	if err != nil {
		return nil, err
	}
	t.IsSystem = isSystem == 1
	t.CreatedAt, _ = time.Parse(time.RFC3339, created)
	t.UpdatedAt, _ = time.Parse(time.RFC3339, updated)
	return t, nil
}
