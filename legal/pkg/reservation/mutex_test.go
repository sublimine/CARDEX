//go:build integration

package reservation

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
)

func newTestMutex(t *testing.T) *Mutex {
	t.Helper()
	rdb := redis.NewClient(&redis.Options{
		Addr: "localhost:6379",
	})
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := rdb.Ping(ctx).Err(); err != nil {
		t.Skipf("Redis not available at localhost:6379: %v", err)
	}
	return New(rdb)
}

func uniqueVehicleULID(prefix string) string {
	return fmt.Sprintf("%s%020d", prefix, time.Now().UnixNano())
}

func TestMutex_Reserve(t *testing.T) {
	m := newTestMutex(t)
	ctx := context.Background()
	ttl := 120 * time.Second

	tests := []struct {
		name string
		run  func(t *testing.T)
	}{
		{
			name: "reserve succeeds on free vehicle",
			run: func(t *testing.T) {
				vehicleULID := uniqueVehicleULID("veh_free_")
				got, err := m.Reserve(ctx, vehicleULID, "01HENTITY001", "quote_abc123", ttl)
				if err != nil {
					t.Fatalf("Reserve() error = %v", err)
				}
				if !got.Granted {
					t.Errorf("Reserve() Granted = false, want true")
				}
				if got.ReservationID == "" {
					t.Errorf("Reserve() ReservationID empty, want non-empty")
				}
				if got.ExpiresAt.IsZero() {
					t.Errorf("Reserve() ExpiresAt zero, want non-zero")
				}
			},
		},
		{
			name: "double reserve by same entity succeeds",
			run: func(t *testing.T) {
				vehicleULID := uniqueVehicleULID("veh_double_")
				entityULID := "01HENTITY002"
				_, err := m.Reserve(ctx, vehicleULID, entityULID, "quote_xyz", ttl)
				if err != nil {
					t.Fatalf("first Reserve() error = %v", err)
				}
				got, err := m.Reserve(ctx, vehicleULID, entityULID, "quote_xyz2", ttl)
				if err != nil {
					t.Fatalf("second Reserve() error = %v", err)
				}
				if !got.Granted {
					t.Errorf("Reserve() Granted = false, want true (same entity re-reserve)")
				}
			},
		},
		{
			name: "reserve by different entity fails",
			run: func(t *testing.T) {
				vehicleULID := uniqueVehicleULID("veh_diff_")
				_, err := m.Reserve(ctx, vehicleULID, "01HENTITYA", "quote_1", ttl)
				if err != nil {
					t.Fatalf("Reserve(entityA) error = %v", err)
				}
				got, err := m.Reserve(ctx, vehicleULID, "01HENTITYB", "quote_2", ttl)
				if err != nil {
					t.Fatalf("Reserve(entityB) error = %v", err)
				}
				if got.Granted {
					t.Errorf("Reserve() Granted = true, want false (different entity)")
				}
			},
		},
		{
			name: "release then re-reserve succeeds",
			run: func(t *testing.T) {
				vehicleULID := uniqueVehicleULID("veh_rere_")
				_, err := m.Reserve(ctx, vehicleULID, "01HENTITYA", "quote_a", ttl)
				if err != nil {
					t.Fatalf("Reserve(entityA) error = %v", err)
				}
				err = m.Release(ctx, vehicleULID, "01HENTITYA")
				if err != nil {
					t.Fatalf("Release(entityA) error = %v", err)
				}
				got, err := m.Reserve(ctx, vehicleULID, "01HENTITYB", "quote_b", ttl)
				if err != nil {
					t.Fatalf("Reserve(entityB) error = %v", err)
				}
				if !got.Granted {
					t.Errorf("Reserve() Granted = false, want true (after release)")
				}
			},
		},
		{
			name: "release by wrong entity fails",
			run: func(t *testing.T) {
				vehicleULID := uniqueVehicleULID("veh_wrong_")
				_, err := m.Reserve(ctx, vehicleULID, "01HENTITYA", "quote_a", ttl)
				if err != nil {
					t.Fatalf("Reserve(entityA) error = %v", err)
				}
				err = m.Release(ctx, vehicleULID, "01HENTITYB")
				if err == nil {
					t.Errorf("Release(entityB) expected error, got nil")
				}
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, tt.run)
	}
}
