package inbox_test

// Track C — Bug-fix TDD tests for inbox.
// Each test is written to FAIL before the fix and PASS after.

import (
	"context"
	"database/sql"
	"testing"

	_ "modernc.org/sqlite"

	"cardex.eu/workspace/internal/inbox"
)

func openInboxDB(t *testing.T) *sql.DB {
	t.Helper()
	db, err := sql.Open("sqlite", ":memory:")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	return db
}

// ── Bug 4: TemplateStore methods ignore context ────────────────────────────────

// TestTemplateList_RespectsCancelledContext verifies that TemplateStore.List
// returns an error when the context is already cancelled at call time.
//
// FAILS before fix: List(tenantID, lang) uses context.Background() internally
//   and does not accept a ctx parameter — so context cancellation is impossible
//   to propagate. (The test will not compile, proving the API gap.)
// PASSES after fix: List(ctx, tenantID, lang) propagates ctx to QueryContext,
//   causing QueryContext to return context.Canceled immediately.
func TestTemplateList_RespectsCancelledContext(t *testing.T) {
	db := openInboxDB(t)
	if err := inbox.EnsureSchema(db); err != nil {
		t.Fatalf("EnsureInboxSchema: %v", err)
	}

	ts := inbox.NewTemplateStore(db)

	// Already-cancelled context.
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	_, err := ts.List(ctx, "tenant-1", "")
	if err == nil {
		t.Fatal("Bug 4: List did not return an error for a cancelled context — context not propagated")
	}
}

// TestTemplateGetByID_RespectsCancelledContext checks the same for GetByID.
func TestTemplateGetByID_RespectsCancelledContext(t *testing.T) {
	db := openInboxDB(t)
	if err := inbox.EnsureSchema(db); err != nil {
		t.Fatalf("EnsureInboxSchema: %v", err)
	}

	ts := inbox.NewTemplateStore(db)

	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	_, err := ts.GetByID(ctx, "tenant-1", "nonexistent-id")
	if err == nil {
		t.Fatal("Bug 4: GetByID did not return an error for a cancelled context — context not propagated")
	}
}

// TestTemplateCreate_RespectsCancelledContext checks the same for Create.
func TestTemplateCreate_RespectsCancelledContext(t *testing.T) {
	db := openInboxDB(t)
	if err := inbox.EnsureSchema(db); err != nil {
		t.Fatalf("EnsureInboxSchema: %v", err)
	}

	ts := inbox.NewTemplateStore(db)

	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	err := ts.Create(ctx, &inbox.Template{
		TenantID: "tenant-1",
		Name:     "test",
		Language: "en",
		Subject:  "s",
		Body:     "b",
	})
	if err == nil {
		t.Fatal("Bug 4: Create did not return an error for a cancelled context — context not propagated")
	}
}
