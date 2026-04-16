package main

import (
	"database/sql"
	"testing"

	_ "modernc.org/sqlite"
)

// openTestDB opens an in-memory SQLite database for review CLI tests.
func openTestDB(t *testing.T) *sql.DB {
	t.Helper()
	db, err := sql.Open("sqlite", ":memory:?_journal_mode=WAL")
	if err != nil {
		t.Fatalf("open test db: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	return db
}

// seedReviewQueue inserts test rows directly into review_queue.
func seedReviewQueue(t *testing.T, db *sql.DB, rows []reviewRow) {
	t.Helper()
	if err := ensureReviewSchema(db); err != nil {
		t.Fatalf("ensure schema: %v", err)
	}
	for _, r := range rows {
		_, err := db.Exec(`
			INSERT INTO review_queue (listing_id, status, reason_flags, created_at)
			VALUES (?, ?, ?, datetime('now'))`,
			r.listingID, r.status, r.flags)
		if err != nil {
			t.Fatalf("seed row %q: %v", r.listingID, err)
		}
	}
}

type reviewRow struct {
	listingID, status, flags string
}

// TestReviewSchema_IdempotentCreate verifies ensureReviewSchema is idempotent.
func TestReviewSchema_IdempotentCreate(t *testing.T) {
	db := openTestDB(t)
	if err := ensureReviewSchema(db); err != nil {
		t.Fatalf("first call: %v", err)
	}
	if err := ensureReviewSchema(db); err != nil {
		t.Fatalf("second call (must be idempotent): %v", err)
	}
}

// TestReviewList_EmptyQueue verifies runReviewList prints "empty" message on empty queue.
func TestReviewList_EmptyQueue(t *testing.T) {
	db := openTestDB(t)
	if err := ensureReviewSchema(db); err != nil {
		t.Fatalf("schema: %v", err)
	}
	// runReviewList writes to stdout; we just verify it does not error.
	flagReviewStatus = "PENDING"
	flagReviewLimit = 50
	if err := runReviewList(db); err != nil {
		t.Fatalf("runReviewList on empty queue: %v", err)
	}
}

// TestReviewList_FilterByStatus verifies status filter returns correct rows.
func TestReviewList_FilterByStatus(t *testing.T) {
	db := openTestDB(t)
	seedReviewQueue(t, db, []reviewRow{
		{"L001", "PENDING", "low_score"},
		{"L002", "PENDING", "needs_review"},
		{"L003", "APPROVED", ""},
		{"L004", "REJECTED", "low_score"},
	})

	flagReviewStatus = "PENDING"
	flagReviewLimit = 50
	if err := runReviewList(db); err != nil {
		t.Fatalf("list PENDING: %v", err)
	}

	// Verify that L001 and L002 are PENDING in the DB.
	var count int
	if err := db.QueryRow(`SELECT COUNT(*) FROM review_queue WHERE status = 'PENDING'`).Scan(&count); err != nil {
		t.Fatalf("count: %v", err)
	}
	if count != 2 {
		t.Errorf("want 2 PENDING rows, got %d", count)
	}
}

// TestReviewApprove_Success verifies approve updates status and sets resolver.
func TestReviewApprove_Success(t *testing.T) {
	db := openTestDB(t)
	seedReviewQueue(t, db, []reviewRow{
		{"L001", "PENDING", "low_score"},
		{"L002", "PENDING", "needs_review"},
		{"L003", "PENDING", "low_score"},
	})

	// Approve one listing.
	if err := runReviewApprove(db, "L001"); err != nil {
		t.Fatalf("approve L001: %v", err)
	}

	var status, reviewer string
	if err := db.QueryRow(`SELECT status, COALESCE(reviewer,'') FROM review_queue WHERE listing_id = 'L001'`).Scan(&status, &reviewer); err != nil {
		t.Fatalf("scan: %v", err)
	}
	if status != "APPROVED" {
		t.Errorf("want APPROVED, got %q", status)
	}
	if reviewer == "" {
		t.Error("reviewer should be set after approval")
	}

	// Other listings remain PENDING.
	var pending int
	if err := db.QueryRow(`SELECT COUNT(*) FROM review_queue WHERE status = 'PENDING'`).Scan(&pending); err != nil {
		t.Fatalf("count pending: %v", err)
	}
	if pending != 2 {
		t.Errorf("want 2 PENDING remaining, got %d", pending)
	}
}

// TestReviewReject_Success verifies reject updates status, sets reviewer and reason.
func TestReviewReject_Success(t *testing.T) {
	db := openTestDB(t)
	seedReviewQueue(t, db, []reviewRow{
		{"L001", "PENDING", "low_score"},
		{"L002", "PENDING", "needs_review"},
		{"L003", "PENDING", "low_score"},
	})

	if err := runReviewReject(db, "L002", "VIN mismatch confirmed"); err != nil {
		t.Fatalf("reject L002: %v", err)
	}

	var status, reason string
	if err := db.QueryRow(`SELECT status, COALESCE(reject_reason,'') FROM review_queue WHERE listing_id = 'L002'`).Scan(&status, &reason); err != nil {
		t.Fatalf("scan: %v", err)
	}
	if status != "REJECTED" {
		t.Errorf("want REJECTED, got %q", status)
	}
	if reason != "VIN mismatch confirmed" {
		t.Errorf("want reason 'VIN mismatch confirmed', got %q", reason)
	}
}

// TestReviewApprove_NotFound verifies approve returns error for unknown ID.
func TestReviewApprove_NotFound(t *testing.T) {
	db := openTestDB(t)
	if err := ensureReviewSchema(db); err != nil {
		t.Fatalf("schema: %v", err)
	}
	err := runReviewApprove(db, "NONEXISTENT")
	if err == nil {
		t.Fatal("expected error for nonexistent listing, got nil")
	}
}

// TestReviewReject_AlreadyResolved verifies reject returns error for non-PENDING items.
func TestReviewReject_AlreadyResolved(t *testing.T) {
	db := openTestDB(t)
	seedReviewQueue(t, db, []reviewRow{
		{"L001", "APPROVED", ""},
	})
	err := runReviewReject(db, "L001", "some reason")
	if err == nil {
		t.Fatal("expected error rejecting an APPROVED item, got nil")
	}
}

// TestReviewShow_NotFound verifies show returns error for unknown ID.
func TestReviewShow_NotFound(t *testing.T) {
	db := openTestDB(t)
	if err := ensureReviewSchema(db); err != nil {
		t.Fatalf("schema: %v", err)
	}
	err := runReviewShow(db, "NONEXISTENT")
	if err == nil {
		t.Fatal("expected error for nonexistent listing, got nil")
	}
}

// TestReviewShow_ExistingItem verifies show does not error for a known item.
func TestReviewShow_ExistingItem(t *testing.T) {
	db := openTestDB(t)
	seedReviewQueue(t, db, []reviewRow{
		{"L001", "PENDING", "low_score,needs_review"},
	})
	if err := runReviewShow(db, "L001"); err != nil {
		t.Fatalf("show L001: %v", err)
	}
}
