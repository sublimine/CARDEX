package server_test

import (
	"context"
	"io"
	"net"
	"path/filepath"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	"cardex.eu/extraction/api/edgepb"
	"cardex.eu/extraction/internal/extractor/e12_edge/server"
	"cardex.eu/extraction/internal/pipeline"
)

// ─── Helpers ─────────────────────────────────────────────────────────────────

type mockStorage struct {
	persisted []*pipeline.VehicleRaw
}

func (m *mockStorage) PersistVehicles(_ context.Context, _ string, v []*pipeline.VehicleRaw) (int, error) {
	m.persisted = append(m.persisted, v...)
	return len(v), nil
}

type testEnv struct {
	client   edgepb.EdgePushClient
	store    *mockStorage
	dealerID string
	apiKey   string
	cleanup  func()
}

func setup(t *testing.T) *testEnv {
	t.Helper()

	db, err := server.NewDB(filepath.Join(t.TempDir(), "edge_test.db"))
	if err != nil {
		t.Fatalf("NewDB: %v", err)
	}

	dealerID, apiKey, err := db.RegisterDealer(context.Background(), "Test Dealer", "DE", "DE123456789", false)
	if err != nil {
		t.Fatalf("RegisterDealer: %v", err)
	}

	store := &mockStorage{}
	srv := server.New(db, store)

	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("net.Listen: %v", err)
	}
	gs := grpc.NewServer()
	edgepb.RegisterEdgePushServer(gs, srv)
	go gs.Serve(lis) //nolint:errcheck

	conn, err := grpc.NewClient(lis.Addr().String(),
		grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatalf("grpc.NewClient: %v", err)
	}

	return &testEnv{
		client:   edgepb.NewEdgePushClient(conn),
		store:    store,
		dealerID: dealerID,
		apiKey:   apiKey,
		cleanup: func() {
			conn.Close()
			gs.GracefulStop()
			db.Close()
		},
	}
}

// validListing returns a VehicleListing that passes all validation checks.
func validListing(vin string) *edgepb.VehicleListing {
	return &edgepb.VehicleListing{
		VIN:        vin,
		Make:       "BMW",
		Model:      "320d",
		Year:       2022,
		PriceCents: 2500000,
		Currency:   "EUR",
		MileageKm:  45000,
		FuelType:   "diesel",
		ImageURLs:  []string{"https://example.com/img1.jpg"},
		SourceURL:  "https://autohaus-berlin.de/fahrzeuge/1",
	}
}

// pushBatch is a helper that opens a stream, sends one batch, and closes it.
func pushBatch(t *testing.T, env *testEnv, listings []*edgepb.VehicleListing) (*edgepb.PushResponse, error) {
	t.Helper()
	stream, err := env.client.PushListings(context.Background())
	if err != nil {
		return nil, err
	}
	if err := stream.Send(&edgepb.ListingBatch{
		DealerID:      env.dealerID,
		APIKey:        env.apiKey,
		TimestampUnix: time.Now().Unix(),
		Listings:      listings,
	}); err != nil && err != io.EOF {
		return nil, err
	}
	return stream.CloseAndRecv()
}

// ─── Tests ────────────────────────────────────────────────────────────────────

// TestHeartbeat verifies the Heartbeat RPC returns a recent server timestamp.
func TestHeartbeat(t *testing.T) {
	env := setup(t)
	defer env.cleanup()

	before := time.Now().Unix()
	resp, err := env.client.Heartbeat(context.Background(), &edgepb.HeartbeatRequest{DealerID: env.dealerID})
	after := time.Now().Unix()

	if err != nil {
		t.Fatalf("Heartbeat: %v", err)
	}
	if resp.ServerTimeUnix < before || resp.ServerTimeUnix > after {
		t.Errorf("ServerTimeUnix %d outside [%d, %d]", resp.ServerTimeUnix, before, after)
	}
}

// TestPushListings_AcceptsValidBatch verifies valid listings are accepted,
// persisted to storage, and reflected in the PushResponse.
func TestPushListings_AcceptsValidBatch(t *testing.T) {
	env := setup(t)
	defer env.cleanup()

	resp, err := pushBatch(t, env, []*edgepb.VehicleListing{
		validListing("WVW12345678901234"),
		validListing("WVW12345678901235"),
	})
	if err != nil {
		t.Fatalf("PushListings: %v", err)
	}
	if resp.Accepted != 2 {
		t.Errorf("want accepted=2, got %d", resp.Accepted)
	}
	if resp.Rejected != 0 {
		t.Errorf("want rejected=0, got %d (rejections: %v)", resp.Rejected, resp.Rejections)
	}
	if len(env.store.persisted) != 2 {
		t.Errorf("want 2 persisted vehicles, got %d", len(env.store.persisted))
	}
}

// TestPushListings_RejectsShortVIN verifies listings with < 17-char VINs are
// rejected with a VIN-length reason in the PushResponse.
func TestPushListings_RejectsShortVIN(t *testing.T) {
	env := setup(t)
	defer env.cleanup()

	bad := validListing("SHORT") // 5 chars
	resp, err := pushBatch(t, env, []*edgepb.VehicleListing{bad})
	if err != nil {
		t.Fatalf("PushListings: %v", err)
	}
	if resp.Rejected != 1 {
		t.Errorf("want rejected=1, got %d", resp.Rejected)
	}
	if len(resp.Rejections) < 1 || resp.Rejections[0].Reason == "" {
		t.Error("want non-empty rejection reason for short VIN")
	}
}

// TestPushListings_RejectsInvalidAPIKey verifies a wrong api_key triggers a
// gRPC Unauthenticated error.
func TestPushListings_RejectsInvalidAPIKey(t *testing.T) {
	env := setup(t)
	defer env.cleanup()

	stream, err := env.client.PushListings(context.Background())
	if err != nil {
		t.Fatalf("PushListings open: %v", err)
	}
	_ = stream.Send(&edgepb.ListingBatch{
		DealerID:      env.dealerID,
		APIKey:        "totally-wrong-key",
		TimestampUnix: time.Now().Unix(),
		Listings:      []*edgepb.VehicleListing{validListing("WVW12345678901234")},
	})
	_, err = stream.CloseAndRecv()
	if err == nil {
		t.Fatal("want Unauthenticated error for bad api_key, got nil")
	}
}

// TestPushListings_MultiBatch verifies that multiple Send calls on the same
// stream accumulate and the final PushResponse totals are correct.
func TestPushListings_MultiBatch(t *testing.T) {
	env := setup(t)
	defer env.cleanup()

	stream, err := env.client.PushListings(context.Background())
	if err != nil {
		t.Fatalf("PushListings: %v", err)
	}
	vins := []string{"WVW12345678901234", "WVW12345678901235", "WVW12345678901236"}
	for i, vin := range vins {
		if err := stream.Send(&edgepb.ListingBatch{
			DealerID:      env.dealerID,
			APIKey:        env.apiKey,
			TimestampUnix: time.Now().Unix(),
			Listings:      []*edgepb.VehicleListing{validListing(vin)},
		}); err != nil && err != io.EOF {
			t.Fatalf("Send[%d]: %v", i, err)
		}
	}
	resp, err := stream.CloseAndRecv()
	if err != nil {
		t.Fatalf("CloseAndRecv: %v", err)
	}
	if resp.Accepted != 3 {
		t.Errorf("want accepted=3, got %d", resp.Accepted)
	}
	if len(env.store.persisted) != 3 {
		t.Errorf("want 3 persisted, got %d", len(env.store.persisted))
	}
}

// TestPushListings_ExtractionMethodTagged verifies that persisted vehicles
// carry AdditionalFields["extraction_method"] = "e12_edge_push".
func TestPushListings_ExtractionMethodTagged(t *testing.T) {
	env := setup(t)
	defer env.cleanup()

	_, err := pushBatch(t, env, []*edgepb.VehicleListing{validListing("WVW12345678901234")})
	if err != nil {
		t.Fatalf("PushListings: %v", err)
	}
	if len(env.store.persisted) == 0 {
		t.Fatal("no vehicles persisted")
	}
	v := env.store.persisted[0]
	method, ok := v.AdditionalFields["extraction_method"]
	if !ok {
		t.Fatal("AdditionalFields[extraction_method] not set")
	}
	if method != "e12_edge_push" {
		t.Errorf("want extraction_method=e12_edge_push, got %q", method)
	}
}

// TestDB_RegisterValidateRevoke covers dealer lifecycle in the DB layer.
func TestDB_RegisterValidateRevoke(t *testing.T) {
	db, err := server.NewDB(filepath.Join(t.TempDir(), "db.db"))
	if err != nil {
		t.Fatalf("NewDB: %v", err)
	}
	defer db.Close()

	id, key, err := db.RegisterDealer(context.Background(), "Auto GmbH", "DE", "DE123456789", true)
	if err != nil {
		t.Fatalf("RegisterDealer: %v", err)
	}
	if id == "" || key == "" {
		t.Fatal("empty dealer_id or api_key")
	}

	// Correct key: valid.
	ok, err := db.ValidateAPIKey(context.Background(), id, key)
	if err != nil || !ok {
		t.Errorf("want valid=true, got %v (err=%v)", ok, err)
	}

	// Wrong key: invalid.
	ok, _ = db.ValidateAPIKey(context.Background(), id, "wrong")
	if ok {
		t.Error("wrong key should return false")
	}

	// Revoke.
	if err := db.RevokeDealer(context.Background(), id); err != nil {
		t.Fatalf("RevokeDealer: %v", err)
	}

	// After revocation, even correct key is invalid.
	ok, _ = db.ValidateAPIKey(context.Background(), id, key)
	if ok {
		t.Error("revoked dealer should fail ValidateAPIKey")
	}

	// Double revoke: error.
	if err := db.RevokeDealer(context.Background(), id); err == nil {
		t.Error("want error on double-revoke")
	}
}
