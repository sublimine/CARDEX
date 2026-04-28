package syndication_test

// Track C — Bug-fix TDD tests for syndication.
// Each test is written to FAIL before the fix and PASS after.

import (
	"context"
	"database/sql"
	"io"
	"log/slog"
	"testing"
	"time"

	_ "modernc.org/sqlite"

	"cardex.eu/workspace/internal/syndication"
)

func discardLogger() *slog.Logger { return slog.New(slog.NewTextHandler(io.Discard, nil)) }

// ── Bug 3: withdrawn_at cleared on re-publish ─────────────────────────────────

// TestWithdrawnAt_PreservedOnRePublish verifies that re-publishing a previously
// withdrawn listing does NOT erase the historical withdrawn_at timestamp.
//
// Sequence: Publish → Withdraw → Re-publish
// Expected: withdrawn_at IS NOT NULL after re-publish.
//
// FAILS before fix: ON CONFLICT DO UPDATE sets `withdrawn_at = excluded.withdrawn_at`
//   which is NULL during a Publish operation, erasing the historical value.
// PASSES after fix: COALESCE(excluded.withdrawn_at, crm_syndication.withdrawn_at)
//   preserves the existing non-NULL value when the new value is NULL.
func TestWithdrawnAt_PreservedOnRePublish(t *testing.T) {
	db, err := sql.Open("sqlite", ":memory:")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer db.Close()

	mock := &mockSyndicationPlatform{name: "mobile_de"}
	platforms := map[string]syndication.Platform{mock.name: mock}

	eng, err := syndication.NewEngineWithPlatforms(db, discardLogger(), platforms)
	if err != nil {
		t.Fatalf("NewEngineWithPlatforms: %v", err)
	}

	ctx := context.Background()
	const vehicleID = "veh-reprob"
	listing := syndication.PlatformListing{VehicleID: vehicleID, Make: "BMW", Model: "3er"}

	// Step 1: Publish.
	if _, err := eng.PublishVehicle(ctx, vehicleID, listing, nil); err != nil {
		t.Fatalf("Publish: %v", err)
	}

	// Step 2: Withdraw — sets withdrawn_at.
	if err := eng.WithdrawVehicle(ctx, vehicleID); err != nil {
		t.Fatalf("Withdraw: %v", err)
	}

	// Verify withdrawn_at is set after withdrawal.
	var withdrawnBefore sql.NullString
	if err := db.QueryRowContext(ctx,
		`SELECT withdrawn_at FROM crm_syndication WHERE vehicle_id=? AND platform=?`,
		vehicleID, mock.name).Scan(&withdrawnBefore); err != nil {
		t.Fatalf("query after withdraw: %v", err)
	}
	if !withdrawnBefore.Valid || withdrawnBefore.String == "" {
		t.Fatal("precondition failed: withdrawn_at should be set after Withdraw; got NULL")
	}

	// Step 3: Re-publish.
	if _, err := eng.PublishVehicle(ctx, vehicleID, listing, nil); err != nil {
		t.Fatalf("Re-publish: %v", err)
	}
	// Give engine time to update.
	time.Sleep(10 * time.Millisecond)

	// Verify withdrawn_at is NOT cleared after re-publish.
	var withdrawnAfter sql.NullString
	if err := db.QueryRowContext(ctx,
		`SELECT withdrawn_at FROM crm_syndication WHERE vehicle_id=? AND platform=?`,
		vehicleID, mock.name).Scan(&withdrawnAfter); err != nil {
		t.Fatalf("query after re-publish: %v", err)
	}
	if !withdrawnAfter.Valid || withdrawnAfter.String == "" {
		t.Fatal("Bug 3: withdrawn_at was cleared by re-publish — COALESCE missing in ON CONFLICT DO UPDATE")
	}
}

// mockSyndicationPlatform satisfies the syndication.Platform interface for tests.
type mockSyndicationPlatform struct {
	name string
}

func (m *mockSyndicationPlatform) Name() string              { return m.name }
func (m *mockSyndicationPlatform) SupportedCountries() []string { return []string{"DE"} }
func (m *mockSyndicationPlatform) Publish(_ context.Context, l syndication.PlatformListing) (string, string, error) {
	return "ext-" + l.VehicleID, "https://example.com/" + l.VehicleID, nil
}
func (m *mockSyndicationPlatform) Update(_ context.Context, _ string, _ syndication.PlatformListing) error {
	return nil
}
func (m *mockSyndicationPlatform) Withdraw(_ context.Context, _ string) error { return nil }
func (m *mockSyndicationPlatform) Status(_ context.Context, extID string) (syndication.PlatformStatus, error) {
	return syndication.PlatformStatus{ExternalID: extID, State: "active"}, nil
}
func (m *mockSyndicationPlatform) ValidateListing(_ syndication.PlatformListing) []syndication.ValidationError {
	return nil
}
