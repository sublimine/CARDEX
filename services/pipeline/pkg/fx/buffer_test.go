//go:build integration

package fx

import (
	"context"
	"math"
	"strings"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
)

func newTestBuffer(t *testing.T) *Buffer {
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

func TestBuffer_ToEUR(t *testing.T) {
	buf := newTestBuffer(t)
	ctx := context.Background()

	tests := []struct {
		name     string
		amount   float64
		currency string
		want     float64
		wantErr  bool
		errSub   string
	}{
		{
			name:     "EUR returns same amount",
			amount:   100,
			currency: "EUR",
			want:     100,
			wantErr:  false,
		},
		{
			name:     "known currency converts",
			amount:   1000,
			currency: "GBP",
			want:     1170,
			wantErr:  false,
		},
		{
			name:     "unknown currency fails closed",
			amount:   100,
			currency: "XYZ",
			wantErr:  true,
			errSub:   "vehicle DESTROYED",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := buf.ToEUR(ctx, tt.amount, tt.currency)
			if tt.wantErr {
				if err == nil {
					t.Errorf("ToEUR() expected error, got nil")
					return
				}
				if tt.errSub != "" && !strings.Contains(err.Error(), tt.errSub) {
					t.Errorf("ToEUR() error = %v, want substring %q", err, tt.errSub)
				}
				return
			}
			if err != nil {
				t.Errorf("ToEUR() unexpected error: %v", err)
				return
			}
			if got != tt.want {
				t.Errorf("ToEUR() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestBuffer_Refresh(t *testing.T) {
	buf := newTestBuffer(t)
	ctx := context.Background()

	if err := buf.Refresh(ctx); err != nil {
		t.Fatalf("Refresh() error = %v", err)
	}

	got, err := buf.ToEUR(ctx, 100, "PLN")
	if err != nil {
		t.Errorf("ToEUR(100, PLN) after Refresh: %v", err)
		return
	}
	want := 23.2 // 100 * 0.232
	if math.Abs(got-want) > 0.0001 {
		t.Errorf("ToEUR(100, PLN) = %v, want %v", got, want)
	}
}
