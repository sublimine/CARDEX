package inbox

import (
	"context"
	"database/sql"
	"fmt"
	"time"
)

// ReminderJob scans for overdue open conversations and creates reminder activities.
type ReminderJob struct {
	db      *sql.DB
	overdue time.Duration
}

// NewReminderJob creates a job that flags conversations idle for longer than overdue.
func NewReminderJob(db *sql.DB, overdue time.Duration) *ReminderJob {
	if overdue <= 0 {
		overdue = 72 * time.Hour // 3 days default
	}
	return &ReminderJob{db: db, overdue: overdue}
}

// Run finds all open conversations across all tenants whose last_message_at is
// older than the overdue threshold, creates a crm_activities reminder for each,
// and returns the number of reminders created.
func (j *ReminderJob) Run(ctx context.Context) (int, error) {
	cutoff := time.Now().UTC().Add(-j.overdue).Format(time.RFC3339)

	rows, err := j.db.QueryContext(ctx,
		`SELECT c.id, c.tenant_id, c.deal_id, c.last_message_at
		 FROM crm_conversations c
		 WHERE c.status = 'open'
		   AND c.last_message_at < ?
		   AND NOT EXISTS (
		       SELECT 1 FROM crm_activities a
		       WHERE a.deal_id = c.deal_id
		         AND a.type = 'reminder'
		         AND a.created_at >= ?
		   )`, cutoff, cutoff)
	if err != nil {
		return 0, fmt.Errorf("query overdue: %w", err)
	}
	defer rows.Close()

	type row struct {
		convID, tenantID, dealID string
		lastMsg                  string
	}
	var found []row
	for rows.Next() {
		var r row
		if err := rows.Scan(&r.convID, &r.tenantID, &r.dealID, &r.lastMsg); err != nil {
			return 0, err
		}
		found = append(found, r)
	}
	if err := rows.Err(); err != nil {
		return 0, err
	}

	nowStr := time.Now().UTC().Format(time.RFC3339)
	count := 0
	for _, r := range found {
		if r.dealID == "" {
			continue
		}
		lastMsgTime, _ := time.Parse(time.RFC3339, r.lastMsg)
		days := int(time.Since(lastMsgTime).Hours() / 24)
		body := fmt.Sprintf("Sin respuesta hace %d días — seguimiento recomendado", days)
		_, err := j.db.ExecContext(ctx,
			`INSERT INTO crm_activities(id,tenant_id,deal_id,type,body,created_at) VALUES(?,?,?,?,?,?)`,
			newID(), r.tenantID, r.dealID, "reminder", body, nowStr)
		if err != nil {
			continue
		}
		count++
	}

	SetOverdue(float64(count))
	return count, nil
}

// RunLoop runs the job on the given interval until ctx is cancelled.
func (j *ReminderJob) RunLoop(ctx context.Context, interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			_, _ = j.Run(ctx)
		}
	}
}

// CountOverdue returns the number of open conversations past the overdue threshold.
func (j *ReminderJob) CountOverdue(ctx context.Context) (int, error) {
	cutoff := time.Now().UTC().Add(-j.overdue).Format(time.RFC3339)
	var n int
	err := j.db.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM crm_conversations WHERE status='open' AND last_message_at < ?`, cutoff).Scan(&n)
	return n, err
}
