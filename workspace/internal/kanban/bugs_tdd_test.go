package kanban_test

// Track C — Bug-fix TDD tests.
// Each test is written to FAIL before the fix and PASS after.

import (
	"context"
	"database/sql"
	"fmt"
	"sync"
	"sync/atomic"
	"testing"

	_ "modernc.org/sqlite"

	"cardex.eu/workspace/internal/kanban"
)

// openDBForRace opens a named in-memory SQLite DB with concurrent connections.
func openDBForRace(t *testing.T, name string) *sql.DB {
	t.Helper()
	db, err := sql.Open("sqlite", fmt.Sprintf("file:%s?mode=memory&cache=shared", name))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	db.SetMaxOpenConns(5)
	t.Cleanup(func() { db.Close() })
	return db
}

// ── Bug 1: WIP limit count runs outside the transaction (TOCTOU race) ─────────

// TestWIPLimit_EnforcedSingleThread is the baseline: WIP limit works sequentially.
// This passes both before and after the fix.
func TestWIPLimit_EnforcedSingleThread(t *testing.T) {
	db := openDB(t)
	s, _ := kanban.NewStore(db)
	s.InitTenant(ctx(), "wip-seq") //nolint:errcheck

	cols, _ := s.ListColumns(ctx(), "wip-seq")
	// Use no-state-key custom columns to bypass state machine.
	src, _ := s.CreateColumn(ctx(), "wip-seq", "SrcSeq", "#aaa", 0, 99)
	dst, _ := s.CreateColumn(ctx(), "wip-seq", "DstSeq", "#bbb", 1, 100)
	_ = cols

	s.EnsureCard(ctx(), "wip-seq", "filler", dst.ID, 0)   //nolint:errcheck
	s.EnsureCard(ctx(), "wip-seq", "candidate", src.ID, 0) //nolint:errcheck

	_, err := s.MoveCard(ctx(), "wip-seq", "candidate", kanban.MoveRequest{
		TargetColumnID: dst.ID,
		Position:       1,
	})
	if err == nil {
		t.Fatal("expected WIP limit error, got nil")
	}
}

// TestWIPLimit_ConcurrentRace is the race-condition test (Bug 1).
// With count query OUTSIDE the TX, concurrent goroutines can both read count=0,
// both pass the check, and both commit → WIP limit violated.
// FAILS before fix: successCount > limit is possible.
// PASSES after fix: count query runs inside the TX, enforcing the limit atomically.
func TestWIPLimit_ConcurrentRace(t *testing.T) {
	const tenantID = "wip-race"
	db := openDBForRace(t, "wip_concurrent")
	s, err := kanban.NewStore(db)
	if err != nil {
		t.Fatal(err)
	}
	s.InitTenant(context.Background(), tenantID) //nolint:errcheck

	const limit = 2
	src, _ := s.CreateColumn(context.Background(), tenantID, "SrcRace", "#aaa", 0, 80)
	dst, _ := s.CreateColumn(context.Background(), tenantID, "DstRace", "#bbb", limit, 81)

	const numCards = 8
	for i := 0; i < numCards; i++ {
		s.EnsureCard(context.Background(), tenantID, fmt.Sprintf("rc-%d", i), src.ID, i) //nolint:errcheck
	}

	var successCount int64
	var wg sync.WaitGroup
	for i := 0; i < numCards; i++ {
		wg.Add(1)
		go func(vid string) {
			defer wg.Done()
			_, moveErr := s.MoveCard(context.Background(), tenantID, vid, kanban.MoveRequest{
				TargetColumnID: dst.ID,
				Position:       0,
			})
			if moveErr == nil {
				atomic.AddInt64(&successCount, 1)
			}
		}(fmt.Sprintf("rc-%d", i))
	}
	wg.Wait()

	if n := atomic.LoadInt64(&successCount); n > int64(limit) {
		t.Errorf("Bug 1: WIP limit violated — %d cards moved into column with limit=%d", n, limit)
	}
}

// ── Bug 2: tx.ExecContext result (vehicle status sync) is ignored ─────────────

// TestMoveCard_VehicleStatusSynced verifies that after moving a card to a
// state-key column, the vehicle's status in crm_vehicles is updated.
// FAILS before fix: crm_vehicles doesn't exist in kanban schema → error silently
// ignored, no vehicle row written.
// PASSES after fix: kanban schema includes crm_vehicles and EnsureCard upserts it;
// MoveCard captures the error and updates status correctly.
func TestMoveCard_VehicleStatusSynced(t *testing.T) {
	db := openDB(t)
	s, _ := kanban.NewStore(db)
	s.InitTenant(ctx(), "vsync") //nolint:errcheck

	cols, _ := s.ListColumns(ctx(), "vsync")
	var sourcing, acquired kanban.Column
	for _, c := range cols {
		switch c.StateKey {
		case "sourcing":
			sourcing = c
		case "acquired":
			acquired = c
		}
	}

	const vehicleID = "veh-status-test"
	if err := s.EnsureCard(ctx(), "vsync", vehicleID, sourcing.ID, 0); err != nil {
		t.Fatalf("EnsureCard: %v", err)
	}

	if _, err := s.MoveCard(ctx(), "vsync", vehicleID, kanban.MoveRequest{
		TargetColumnID: acquired.ID,
		Position:       0,
	}); err != nil {
		t.Fatalf("MoveCard: %v", err)
	}

	// Verify crm_vehicles.status was updated to "acquired".
	var status string
	err := db.QueryRowContext(ctx(),
		`SELECT status FROM crm_vehicles WHERE tenant_id=? AND id=?`, "vsync", vehicleID).
		Scan(&status)
	if err == sql.ErrNoRows {
		t.Fatal("Bug 2: vehicle row missing from crm_vehicles — status sync failed (error was silently ignored)")
	}
	if err != nil {
		t.Fatalf("query crm_vehicles: %v (crm_vehicles table may not exist in schema)", err)
	}
	if status != "acquired" {
		t.Errorf("expected status=acquired, got %q", status)
	}
}
